from playwright.sync_api import sync_playwright
import time
import pandas as pd
import os
import threading
import queue
import shutil

# --- Helpers ---

from core.utils import resolve_selector as _resolve_selector
from core.utils import replace_variables as _replace_variables




# --- Worker ---

class PlaywrightWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.task_queue = queue.Queue()
        self.playwright = None
        self.context = None # Persistent Context
        self.page = None
        self.ready_event = threading.Event()
        self.user_data_dir = os.path.abspath("user_data")
        self.stop_flag = threading.Event()
        self.execution_logs = []
        self.is_execution_active = False
        
        # Setup Logging
        self.logs_dir = os.path.abspath("logs")
        if not os.path.exists(self.logs_dir):
            os.makedirs(self.logs_dir)
            
    def log(self, message, level="INFO"):
        """
        Thread-safe logging helper.
        1. Appends to self.execution_logs (for UI).
        2. Prints to stdout (safely encoding emojis).
        3. Appends to local log file.
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted_msg = f"[{timestamp}] [{level}] {message}"
        
        # 1. UI Log
        self.execution_logs.append(formatted_msg)
        
        # 2. Console Log (Safe)
        try:
            # On Windows, printing unicode can fail if console is cp1252/gbk.
            # We buffer write utf-8 or replace errors to avoid crash.
            print(formatted_msg.encode('utf-8', errors='replace').decode('utf-8'))
        except:
            # Ultima ratio: just print ascii ref
            print(formatted_msg.encode('ascii', errors='replace').decode('ascii'))
            
        # 3. File Log
        try:
            # File per day
            date_str = time.strftime("%Y-%m-%d")
            log_file = os.path.join(self.logs_dir, f"execution_{date_str}.log")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(formatted_msg + "\n")
        except Exception as e:
            print(f"写入日志文件失败: {e}")


    def _restart_browser(self):
        self.log("正在重启浏览器会话...", "WARNING")
        try:
            if self.context: self.context.close()
        except: pass
        try:
            if self.playwright: self.playwright.stop()
        except: pass
        
        # Re-init startup logic
        self.playwright = sync_playwright().start()
        self.context = self.playwright.chromium.launch_persistent_context(
                self.user_data_dir,
                headless=False,
                viewport=None
            )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self._setup_binding()

    def run(self):
        try:
            if not os.path.exists(self.user_data_dir):
                os.makedirs(self.user_data_dir)

            self.playwright = sync_playwright().start()
            
            self.context = self.playwright.chromium.launch_persistent_context(
                self.user_data_dir,
                headless=False,
                viewport=None
            )
            
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self._setup_binding()
            
            self.ready_event.set()
            
            while True:
                task = self.task_queue.get()
                if task is None: break 
                
                func_name, args, result_queue, kwargs = task
                
                # Retry Loop for Auto-Recovery
                max_retries = 1
                for attempt in range(max_retries + 1):
                    try:
                        if hasattr(self, func_name):
                            func = getattr(self, func_name)
                            result = func(*args, **kwargs)
                            # Only put result if queue provider expects it (queue not None)
                            if result_queue:
                                result_queue.put({"status": "success", "data": result})
                        else:
                            if result_queue:
                                result_queue.put({"status": "error", "error": f"Unknown method {func_name}"})
                        break # Success, exit retry loop
                    except Exception as e:
                        err_str = str(e)
                        # Check for browser closed error
                        if "Target page, context or browser has been closed" in err_str:
                            if attempt < max_retries:
                                self.log(f"检测到浏览器已关闭，正在重启... (错误: {err_str})", "WARNING")
                                try:
                                    self._restart_browser()
                                    # Retry same task in next iteration
                                    continue 
                                except Exception as restart_e:
                                    self.log(f"重启浏览器失败: {restart_e}", "ERROR")
                                    if result_queue:
                                        result_queue.put({"status": "error", "error": f"Browser closed and restart failed: {restart_e}"})
                                    break
                            else:
                                self.log(f"工作任务错误 (最终): {e}", "ERROR")
                                if result_queue:
                                    result_queue.put({"status": "error", "error": str(e)})
                        else:
                            # Other errors, just report
                            self.log(f"工作任务错误: {e}", "ERROR")
                            if result_queue:
                                result_queue.put({"status": "error", "error": str(e)})
                            break
                
                self.task_queue.task_done()
                    
        except Exception as e:
            # We can't log to self.execution_logs easily if we crashed, but we can try printing safely
            try:
                print(f"Playwright Worker Crashed: {e}".encode('utf-8', errors='replace').decode('utf-8'))
            except:
                pass
    
    def _setup_binding(self):
         try:
            self.context.expose_binding("elementClicked", self._on_picker_click)
         except:
            pass

    # --- Internal Actions ---

    def _ensure_page(self):
        if self.page.is_closed():
             self.page = self.context.new_page()
        self.page.bring_to_front()

    def _internal_open(self, url):
        self._ensure_page()
        if url:
            self.page.goto(url)
        return True

    def _perform_validation(self, config, row):
        """
        Universal validation logic.
        Returns: (success: bool, error_message: str)
        """
        # Check Stop Flag
        if self.stop_flag.is_set():
            msg = "⛔ 流程已由用户停止 (Stopped by User)"
            self.log(msg, "WARNING")
            return False, msg

        wait_after = config.get('waitAfter')
        validate_sel = config.get('validateSelector')
        
        # 1. Validation Mode
        if validate_sel:
            validate_sel = _resolve_selector(_replace_variables(validate_sel, row))
            # Timeout logic: use waitAfter as timeout if set, else 30s
            timeout = int(wait_after) if wait_after and int(wait_after) > 0 else 30000
            
            try:
                # Playwright's wait_for_selector polls automatically (scans every few ms)
                # It returns immediately if found, or throws if timeout
                self.page.wait_for_selector(validate_sel, state='visible', timeout=timeout)
                self.log(f"验证通过: 元素 '{validate_sel}' 在 {timeout}ms 内出现。")
                return True, ""
            except:
                err = f"验证失败: 元素 '{validate_sel}' 未在 {timeout}ms 内出现。"
                self.log(err, "ERROR")
                self.log("跳过此行的剩余步骤...", "WARNING")
                return False, err
        
        # 2. Fixed Wait Mode
        elif wait_after and int(wait_after) > 0:
            # Sleep in chunks to allow interruption
            sleep_time = int(wait_after) / 1000.0
            elapsed = 0
            while elapsed < sleep_time:
                if self.stop_flag.is_set():
                    msg = "⛔ 等待中被用户停止"
                    self.log(msg, "WARNING")
                    return False, msg
                time.sleep(0.5)
                elapsed += 0.5
            
            self.log(f"已等待 {wait_after}ms (固定)")
            return True, ""
            
        return True, "" # No validation config, Pass

    def _on_picker_click(self, source, selector):
        self.last_picked_selector = selector

    def _internal_pick(self, url=None):
        self._ensure_page()
        if url:
             self.page.goto(url)
        
        self.last_picked_selector = None
        
        self.page.evaluate("""
            (() => {
                let highlighted = null;
                
                window.cleanupPicker = () => {
                    if (highlighted) highlighted.style.outline = '';
                    document.removeEventListener('mouseover', window.pickerMouseOver);
                    document.removeEventListener('click', window.pickerClick, true);
                };
                
                window.pickerMouseOver = (e) => {
                    if (highlighted) {
                        highlighted.style.outline = '';
                    }
                    highlighted = e.target;
                    highlighted.style.outline = '2px solid red';
                };
                
                window.pickerClick = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const getSmartSelector = (elm) => {
                        // 1. ID (with dynamic ID detection)
                        if (elm.id) {
                            const id = elm.id;
                            // Filter out common dynamic ID patterns (e.g. ElementUI, Vue, React random hashes)
                            // 1. Contains 3+ consecutive digits (e.g. item-2938-name) covering distinct randomness
                            // 2. Starts with specific framework prefixes followed by numbers
                            const isDynamic = /\d{4,}/.test(id) ||                 // Long numbers (e.g. 4296)
                                              /el-autocomplete-\d+/.test(id) ||    // ElementUI Autocomplete
                                              /el-select-\d+/.test(id) ||          // ElementUI Select
                                              /^v-\d+/.test(id) ||                 // Vue scoped
                                              /^uid-\d+/.test(id);                 // Common unique ID
                            
                            if (!isDynamic) {
                                return '#' + CSS.escape(id);
                            }
                            // If dynamic, fall through to other strategies
                        }
                        
                        // 2. ElementUI Special Handling (Broad Support)
                        // List of common dropdown containers
                        const containers = [
                            '.el-autocomplete-suggestion',
                            '.el-select-dropdown',
                            '.el-cascader__dropdown',
                            '.el-cascader-menu',
                            '.el-dropdown-menu',
                            '.el-popover'
                        ];
                        
                        // Find if we are inside any known container
                        const container = containers.find(c => elm.closest(c));
                        
                        if (container) {
                            // Find the list item (often LI, sometimes generic div with class like el-select-dropdown__item)
                            const li = elm.closest('li') || elm.closest('.el-select-dropdown__item') || elm.closest('.el-cascader-node');
                            
                            if (li) {
                                // Get meaningful text
                                const text = li.innerText ? li.innerText.trim().split('\\n')[0] : ''; // Take first line if multiline
                                
                                // Construct robust selector
                                if (text) {
                                    // Use visible filter and text
                                    // Example: .el-select-dropdown li:visible >> text="Option 1"
                                    const tagName = li.tagName.toLowerCase();
                                    const containerClass = container.split('.')[1]; // get class name without dot
                                    
                                    // Special handle for cascader which might have multiple menus open
                                    // We want the visible one. 
                                    return container + ' ' + tagName + ':visible >> text="' + text + '"';
                                }
                            }
                        }

                        // 3. Text Content (Robust for buttons/links)

                        // 3. Text Content (Robust & Scoped)
                        const text = elm.innerText ? elm.innerText.trim() : '';
                        if (text && text.length > 0 && text.length < 30) {
                             // Limit to specific tags to avoid picking huge divs by text
                             if (['BUTTON', 'A', 'SPAN', 'LI', 'LABEL', 'H1', 'H2', 'H3', 'H4', 'H5', 'DIV'].includes(elm.tagName)) {
                                 const safeText = text.replace(/"/g, '\\"');
                                 
                                 // Helper: Count visible elements with exact text
                                 // Note: This is an approximation. Native text search is hard.
                                 // We filter by innerText equality + visibility.
                                 const getCountByText = (txt, tagName=null, root=document) => {
                                     const nodes = root.querySelectorAll(tagName || '*');
                                     let count = 0;
                                     for (let node of nodes) {
                                         // Check visibility (offsetParent is null if hidden)
                                         if (node.offsetParent !== null && node.innerText && node.innerText.trim() === txt) {
                                             count++;
                                         }
                                     }
                                     return count;
                                 };

                                 const totalMatches = getCountByText(text, null, document);
                                 
                                 if (totalMatches === 1) {
                                     // Unique text
                                     return `text="${safeText}"`;
                                 } else if (totalMatches > 1) {
                                     // Ambiguous: Try Scoping
                                     
                                     // Strategy A: Tag Name specific
                                     const tagMatches = getCountByText(text, elm.tagName, document);
                                     if (tagMatches === 1) {
                                         return `${elm.tagName.toLowerCase()} >> text="${safeText}"`;
                                     }
                                     
                                     // Strategy B: Parent Scoping (ID or Unique Class)
                                     let bucket = elm.parentElement;
                                     while (bucket && bucket !== document.body) {
                                         // 1. Parent ID (Static check)
                                         if (bucket.id && !/\d{4,}/.test(bucket.id)) {
                                              const pid = '#' + CSS.escape(bucket.id);
                                              return `${pid} >> text="${safeText}"`;
                                         }
                                         
                                         // 2. Parent Unique Class
                                         if (bucket.className && typeof bucket.className === 'string') {
                                             const classes = bucket.className.split(/\s+/).filter(c => c && !['row', 'col', 'container', 'wrapper', 'active', 'show', 'flex', 'box'].some(bad => c.includes(bad)));
                                             for (let cls of classes) {
                                                 if (document.querySelectorAll('.' + cls).length === 1) {
                                                     return `.${cls} >> text="${safeText}"`;
                                                 }
                                             }
                                         }
                                         bucket = bucket.parentElement;
                                     }
                                 }
                             }
                        }

                        // 4. Unique Class
                        if (elm.className && typeof elm.className === 'string') {
                             const classes = elm.className.split(/\s+/).filter(c => c && !['is-active', 'hover', 'focus', 'selected'].some(bad => c.includes(bad)));
                             if (classes.length > 0) {
                                 const selector = '.' + classes.join('.');
                                 // Verify uniqueness
                                 if (document.querySelectorAll(selector).length === 1) {
                                     return selector;
                                 }
                             }
                        }

                        // 5. Fallback: Absolute XPath (Original Logic)
                        const getXPath = (node) => {
                            if (node.id !== '') return '//*[@id="' + node.id + '"]';
                            if (node === document.body) return '/html/body';
                            if (!node.parentNode) return '';
                            
                            let ix = 0;
                            let siblings = node.parentNode.childNodes;
                            for (let i = 0; i < siblings.length; i++) {
                                let sibling = siblings[i];
                                if (sibling === node) return getXPath(node.parentNode) + '/' + node.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                                if (sibling.nodeType === 1 && sibling.tagName === node.tagName) ix++;
                            }
                            return '';
                        };
                        return getXPath(elm);
                    };
                    
                    const selector = getSmartSelector(e.target);
                    // Remove highlight
                    if (highlighted) highlighted.style.outline = '';
                    window.elementClicked(selector);
                };
                
                document.addEventListener('mouseover', window.pickerMouseOver);
                document.addEventListener('click', window.pickerClick, {capture: true});
            })();
        """)
        
        start_time = time.time()
        while self.last_picked_selector is None:
            if time.time() - start_time > 60:
                self._cleanup_picker()
                return None
            self.page.wait_for_timeout(200)
            
        self._cleanup_picker()
        return self.last_picked_selector

    def _cleanup_picker(self):
        try:
            self.page.evaluate("window.cleanupPicker && window.cleanupPicker()")
        except:
            pass

    def _internal_run_steps(self, flow_data, mode='normal'):
        """
        Executes steps using the new StepRegistry.
        """
        DEFAULT_TIMEOUT = 30000
        TEST_TIMEOUT = 2000
        
        current_timeout = TEST_TIMEOUT if mode == 'test' else DEFAULT_TIMEOUT
        self.page.set_default_timeout(current_timeout)
        
        # Reset State
        self.stop_flag.clear()
        self.is_execution_active = True
        self.execution_logs = []
        
        items = flow_data if isinstance(flow_data, list) else flow_data.get('steps', [])
        steps_config = items
        
        excel_path = None
        record_column = None
        
        # 1. First pass: scan for excel_read
        for step in steps_config:
            if step.get('type') == 'excel_read':
                cfg = step.get('config', {})
                if cfg.get('filePath'):
                    excel_path = cfg.get('filePath')
                if cfg.get('statusColumn'):
                    record_column = cfg.get('statusColumn')
            elif step.get('type') == 'record_excel':
                cfg = step.get('config', {})
                if cfg.get('columnName') and not record_column:
                    record_column = cfg.get('columnName')

        if excel_path and not record_column:
            record_column = '执行结果'

        data_rows = []
        results = self.execution_logs 

        if excel_path and os.path.exists(excel_path):
            try:
                df = pd.read_excel(excel_path)
                df = df.fillna("")
                data_rows = df.to_dict('records')
                # Test Mode: First row only
                if mode == 'test' and len(data_rows) > 0:
                     data_rows = data_rows[:1]
                     self.log(f"测试模式: 仅处理Excel数据的第一行。", "WARNING")
                self.log(f"已加载Excel: {excel_path}，共 {len(data_rows)} 行。")
            except Exception as e:
                self.log(f"加载Excel失败: {e}", "ERROR")
                data_rows = [{}]
        else:
            data_rows = [{}]

        self._ensure_page()
        
        # Import Registry and Context
        from core.steps.registry import StepRegistry
        from core.steps.base import StepContext
        # Ensure all steps are loaded
        import core.steps.basic
        import core.steps.interaction

        for i, row in enumerate(data_rows):
            # Periodic Reset (Every 100 rows)
            if i > 0 and i % 100 == 0:
                self.log(f"例行100行重置在第 {i+1} 行触发...", "WARNING")
                try:
                    self._restart_browser()
                except Exception as e:
                    self.log(f"重置失败: {e}", "ERROR")
            if self.stop_flag.is_set():
                self.log("⛔ (全局停止已触发)", "WARNING")
                break

            row_info = f"第 {i+1} 行" if excel_path else "单次运行"
            
            # Ensure page is alive before starting row
            try:
                self._ensure_page()
            except:
                self.log("页面检查失败，正在重启浏览器...", "WARNING")
                self._restart_browser()

            # Skip logic
            if record_column and mode != 'test':
                 val = row.get(record_column)
                 # Only skip if explicitly Success (case-insensitive) or 成功
                 val_str = str(val).strip().lower()
                 if val and (val_str == 'success' or val_str == '成功'):
                     self.log(f"跳过 {row_info}: 已处理 ({record_column}='{val}')")
                     continue

            self.log(f"--- 开始 {row_info} (模式: {mode}) ---")
            row_success = True 
            failure_reason = "" 

            for step_conf in steps_config:
                if self.stop_flag.is_set(): break
                    
                step_type = step_conf.get('type')
                if step_type == 'record_excel' or step_type == 'excel_read': continue

                try:
                    # Common Wait Before
                    config = step_conf.get('config', {})
                    wait_before = config.get('waitBefore')
                    if wait_before:
                         # Manual sleep with check
                        time.sleep(int(wait_before) / 1000.0)

                    # Create Context
                    ctx = StepContext(self.page, self.log, row, self.stop_flag, self.execution_logs)
                    
                    # Instantiate Step
                    step_instance = StepRegistry.create_step(step_type, config, ctx)
                    
                    if not step_instance:
                        self.log(f"Unknown step type: {step_type}", "ERROR")
                        row_success = False
                        continue
                        
                    # Execute
                    success = step_instance.execute()
                    if not success:
                        row_success = False
                        # Try to capture generic failure if specific reason wasn't logged? 
                        # Ideally steps should raise exceptions or we handle return values better.
                        # For now, let's assume if execute returns False, it logged an error.
                        failure_reason = f"失败: 步骤 '{step_conf.get('title', step_type)}' 返回失败"
                        break
                        
                    # Validation
                    val_success, val_msg = self._perform_validation(config, row)
                    if not val_success:
                        row_success = False
                        failure_reason = f"失败: {val_msg}"
                        break

                except Exception as step_e:
                    err_str = str(step_e)
                    err_msg = f"Error in step '{step_conf.get('title', step_type)}': {err_str}"
                    self.log(err_msg, "ERROR")

                    # Check for Critical Browser Crash
                    if "Target page, context or browser has been closed" in err_str or "Session closed" in err_str:
                        self.log("⚠️ 检测到浏览器崩溃/断开连接! 正在重启浏览器...", "WARNING")
                        try:
                            self._restart_browser()
                        except Exception as restart_e:
                            self.log(f"重启失败: {restart_e}", "ERROR")
                        
                        # Mark specifically as Crashed
                        row_success = False
                        failure_reason = "网页崩溃"
                        # Break to skip remaining steps for this row, will proceed to next row
                        break
                    
                    # Normal Failure
                    row_success = False
                    failure_reason = f"失败: {step_e}"
                    if mode == 'test':
                        self.is_execution_active = False
                        return {"logs": self.execution_logs, "success": False}
                    break
        
            # Record Result
            if record_column and excel_path and not self.stop_flag.is_set() and mode != 'test':
                 status_val = "成功" if row_success else (failure_reason if failure_reason else "失败")
                 if record_column not in df.columns: df[record_column] = ""
                 df.at[i, record_column] = status_val
                 try:
                     df.to_excel(excel_path, index=False)
                     self.log(f"已记录 '{status_val}' 到Excel的第 {i+1} 行")
                 except Exception as exc:
                     self.log(f"写入Excel失败: {exc}", "ERROR")

        self.is_execution_active = False
        return {"logs": results, "success": True}

    def _handle_auto_login(self, page, target_url, config, row, timeout):
        try:
            time.sleep(2)
            current_url_base = page.url.split('?')[0]
            target_url_base = target_url.split('?')[0]

            if current_url_base != target_url_base:
                user_sel = config.get('loginUserSelector')
                # Check visibility with short timeout
                try: 
                    page.wait_for_selector(user_sel, state='visible', timeout=2000) 
                except:
                    return # Login not found

                self.log("Detected login page, attempting auto-login...")
                
                page.fill(_resolve_selector(_replace_variables(user_sel, row)), _replace_variables(str(config.get('loginUser')), row), timeout=timeout)
                pass_sel = config.get('loginPassSelector')
                if pass_sel:
                        page.fill(_resolve_selector(_replace_variables(pass_sel, row)), _replace_variables(str(config.get('loginPass')), row), timeout=timeout)
                
                btn_sel = config.get('loginBtnSelector')
                if btn_sel:
                    page.click(_resolve_selector(_replace_variables(btn_sel, row)), timeout=timeout)
                
                page.wait_for_load_state('networkidle')
                time.sleep(3)
                
                self.log(f"重新打开目标URL (登录后): {target_url}")
                page.goto(target_url)
                page.wait_for_load_state('domcontentloaded')
        except Exception as e:
            self.log(f"自动登录逻辑警告: {e}", "WARNING")

    def _handle_upload(self, page, config, row, timeout):
        raw_selector = config.get('selector')
        raw_path = config.get('filePath')
        input_type = config.get('inputType', 'fixed')
        
        selector = _resolve_selector(_replace_variables(raw_selector, row))
        
        if input_type == 'excel':
            file_path = str(row.get(raw_path, ""))
        else:
            file_path = _replace_variables(raw_path, row)
        
        if not selector or not file_path:
            self.log("上传失败: 选择器或文件路径缺失", "ERROR")
            return
            
        try:
            page.wait_for_selector(selector, state="attached", timeout=timeout)
            handle = page.query_selector(selector)
            if not handle: raise Exception("Element not found")
            
            is_file_input = handle.evaluate("el => el.tagName === 'INPUT' && el.type === 'file'")
            
            if is_file_input:
                page.set_input_files(selector, file_path, timeout=timeout)
                self.log(f"已上传 {file_path}")
            else:
                with page.expect_file_chooser(timeout=timeout) as fc_info:
                    page.click(selector, force=True, timeout=timeout)
                file_chooser = fc_info.value
                file_chooser.set_files(file_path)
                self.log(f"已通过对话框上传 {file_path}")

                
        except Exception as e:
             # Re-raise to be caught by main loop
             raise e

# --- Bridge ---

class ThreadSafeDebugSession:
    def __init__(self):
        self.worker = PlaywrightWorker()
        self.worker.start()
        self.worker.ready_event.wait(timeout=20)

    def _submit(self, func_name, *args, **kwargs):
        result_queue = queue.Queue()
        self.worker.task_queue.put((func_name, args, result_queue, kwargs))
        
        res = result_queue.get()
        if res["status"] == "success":
            return res["data"]
        else:
            raise Exception(res["error"])

    def _submit_async(self, func_name, *args, **kwargs):
        """Submit a task but don't wait for result."""
        # We pass None as result_queue to indicate no return expected from worker logic
        self.worker.task_queue.put((func_name, args, None, kwargs))
        return True

    def open(self, url):
        return self._submit("_internal_open", url)

    def pick(self, url=None):
        return self._submit("_internal_pick", url)
    
    def run_flow(self, flow_data, mode='normal'):
        return self._submit("_internal_run_steps", flow_data, mode=mode)
    
    def run_flow_async(self, flow_data, mode='normal'):
        if self.worker.is_execution_active:
             raise Exception("A flow is already running.")
        return self._submit_async("_internal_run_steps", flow_data, mode=mode)

    def stop_flow(self):
        self.worker.stop_flag.set()
        return True

    def get_status(self):
        return {
            "is_running": self.worker.is_execution_active,
            "logs": list(self.worker.execution_logs) # Return copy
        }

# Initialize
_debug_session = ThreadSafeDebugSession()

# --- Exports for Server ---

def open_debug_browser(url):
    return _debug_session.open(url)

def pick_debug_element(url=None):
    return _debug_session.pick(url)

def execute_flow(flow_data, mode='normal'):
    """
    Called by server.py /api/run.
    Mode: 'normal' or 'test'.
    """
    return _debug_session.run_flow(flow_data, mode=mode)

def execute_flow_async(flow_data, mode='normal'):
    return _debug_session.run_flow_async(flow_data, mode=mode)

def stop_flow_execution():
    return _debug_session.stop_flow()

def get_flow_status():
    return _debug_session.get_status()
