from playwright.sync_api import sync_playwright
import time
import pandas as pd
import os
import threading
import queue
import shutil
import ctypes
from ctypes import wintypes

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


    def _minimize_browser_window(self):
        """
        Minimize the Chromium/Chrome window after launch so that uploads,
        refreshes or navigations do not steal foreground focus.
        """
        try:
            user32 = ctypes.windll.user32
            found = []

            def enum_callback(hwnd, extra):
                if user32.IsWindowVisible(hwnd):
                    text = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(hwnd, text, 256)
                    title = text.value
                    if title and ("Chromium" in title or "Chrome" in title):
                        found.append(hwnd)
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(
                wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
            )
            user32.EnumWindows(EnumWindowsProc(enum_callback), 0)

            for hwnd in found:
                user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        except Exception as e:
            self.log(f"最小化浏览器窗口失败: {e}", "WARNING")

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
        self._minimize_browser_window()

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
            self._minimize_browser_window()

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
            err_msg = f"Playwright Worker Crashed: {e}"
            # 1. Print safely
            try:
                print(err_msg.encode('utf-8', errors='replace').decode('utf-8'))
            except:
                pass
            # 2. Ensure the failure is also written to the log file, even if init failed early.
            try:
                self.log(err_msg, "ERROR")
            except:
                pass

    def _setup_binding(self):
         try:
            self.context.expose_binding("elementClicked", self._on_picker_click)
         except:
            pass

    # --- Internal Actions ---

    def _ensure_page(self, bring_to_front=True):
        if self.page.is_closed():
             self.page = self.context.new_page()
        # 仅在需要时将窗口拉到前台（如拾取选择器需用户手动点击）。
        # 流程执行无需前台，避免每行都对焦抢占焦点、打断用户其他工作。
        if bring_to_front:
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
        # Phase 1: accept both legacy string and new structured object
        # Store as-is (dict or string) for downstream compatibility
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

                // --- shared helpers ---
                const isVisible = (node) => node.offsetParent !== null;

                const isDynamicString = (s) => {
                    if (!s || typeof s !== 'string') return true;
                    return /\d{4,}/.test(s) ||                  // Long numbers (e.g. 4296)
                           /el-autocomplete-\d+/.test(s) ||     // ElementUI Autocomplete
                           /el-select-\d+/.test(s) ||           // ElementUI Select
                           /^v-\d+/.test(s) ||                  // Vue scoped
                           /^uid-\d+/.test(s) ||                // Common unique ID
                           /^[a-f0-9]{32}$/i.test(s) ||          // 32-char random hash
                           /\b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b/i.test(s) || // UUID
                           /react-root|root-\d+/.test(s);        // React random IDs
                };

                const escapeText = (text) => text.replace(/"/g, '\\\\"');

                const isFormControl = (tag) => ['INPUT', 'SELECT', 'TEXTAREA'].includes(tag);

                const testAttrs = ['data-testid', 'data-id', 'data-qa', 'data-automation-id'];

                const semanticAttrs = ['placeholder', 'name', 'aria-label', 'title', 'role'];

                const badClasses = ['is-active', 'hover', 'focus', 'selected', 'row', 'col', 'container', 'wrapper', 'active', 'show', 'flex', 'box'];

                const isBadClass = (cls) => badClasses.some(bad => cls.includes(bad));

                const getFilteredClasses = (elm, extraBad=[]) => {
                    if (!elm.className || typeof elm.className !== 'string') return [];
                    const allBad = badClasses.concat(extraBad);
                    return elm.className.split(/\s+/).filter(c => c && !allBad.some(bad => c.includes(bad)));
                };

                const countBySelector = (sel, root=document) => {
                    try { return root.querySelectorAll(sel).length; } catch (e) { return 0; }
                };

                const countVisibleBySelector = (sel, root=document) => {
                    try {
                        const nodes = root.querySelectorAll(sel);
                        let count = 0;
                        for (let node of nodes) {
                            if (isVisible(node)) count++;
                        }
                        return count;
                    } catch (e) { return 0; }
                };

                const countVisibleByText = (txt, tagName=null, root=document) => {
                    const nodes = root.querySelectorAll(tagName || '*');
                    let count = 0;
                    for (let node of nodes) {
                        if (isVisible(node) && node.innerText && node.innerText.trim() === txt) {
                            count++;
                        }
                    }
                    return count;
                };

                const findStableIdAncestor = (elm) => {
                    let node = elm.parentElement;
                    while (node) {
                        if (node.id && !isDynamicString(node.id)) {
                            return node;
                        }
                        if (node === document.body) break;
                        node = node.parentElement;
                    }
                    return null;
                };

                const findTestAttrAncestor = (elm) => {
                    let node = elm.parentElement;
                    while (node) {
                        for (let attr of testAttrs) {
                            if (node.hasAttribute(attr)) {
                                const val = node.getAttribute(attr);
                                if (val && !isDynamicString(val)) return { node, attr, val };
                            }
                        }
                        if (node === document.body) break;
                        node = node.parentElement;
                    }
                    return null;
                };

                const findUniqueClassAncestor = (elm) => {
                    let node = elm.parentElement;
                    while (node) {
                        const classes = getFilteredClasses(node);
                        for (let cls of classes) {
                            if (countBySelector('.' + cls) === 1) return { node, cls };
                        }
                        if (node === document.body) break;
                        node = node.parentElement;
                    }
                    return null;
                };

                // Playwright :has-text() is not valid in native querySelectorAll.
                // This helper manually counts descendants of `root` whose innerText contains `txt`
                // and which have exactly one descendant of `tagName` (the form control).
                const countHasTextTag = (root, txt, tagName) => {
                    if (!root || !root.querySelectorAll) return 0;
                    const roots = root.querySelectorAll('*');
                    let count = 0;
                    for (const candidate of roots) {
                        if (!isVisible(candidate)) continue;
                        if (!candidate.innerText || !candidate.innerText.trim().includes(txt)) continue;
                        const targets = candidate.querySelectorAll(tagName);
                        let visibleTargets = 0;
                        for (const t of targets) if (isVisible(t)) visibleTargets++;
                        if (visibleTargets === 1) count++;
                    }
                    return count;
                };

                // Count visible LABEL elements whose text contains `txt`.
                const countVisibleLabelsByText = (txt) => {
                    let count = 0;
                    for (const lbl of document.querySelectorAll('label')) {
                        if (!isVisible(lbl)) continue;
                        if (lbl.innerText && lbl.innerText.trim().includes(txt)) count++;
                    }
                    return count;
                };

                const getAnchor = (elm) => {
                    // 1. self or ancestor static id
                    if (elm.id && !isDynamicString(elm.id)) {
                        return { type: 'id', selector: '#' + CSS.escape(elm.id), node: elm };
                    }
                    const idAncestor = findStableIdAncestor(elm);
                    if (idAncestor) {
                        return { type: 'id', selector: '#' + CSS.escape(idAncestor.id), node: idAncestor };
                    }
                    // 2. self or ancestor test attr
                    for (let attr of testAttrs) {
                        if (elm.hasAttribute(attr)) {
                            const val = elm.getAttribute(attr);
                            if (val && !isDynamicString(val)) {
                                return { type: 'attr', selector: `[${attr}="${escapeText(val)}"]`, node: elm };
                            }
                        }
                    }
                    const testAncestor = findTestAttrAncestor(elm);
                    if (testAncestor) {
                        return { type: 'attr', selector: `[${testAncestor.attr}="${escapeText(testAncestor.val)}"]`, node: testAncestor.node };
                    }
                    // 3. self or ancestor unique class
                    const selfClasses = getFilteredClasses(elm);
                    for (let cls of selfClasses) {
                        if (countBySelector('.' + cls) === 1) {
                            return { type: 'class', selector: '.' + cls, node: elm };
                        }
                    }
                    const uniqueClassAncestor = findUniqueClassAncestor(elm);
                    if (uniqueClassAncestor) {
                        return { type: 'class', selector: '.' + uniqueClassAncestor.cls, node: uniqueClassAncestor.node };
                    }
                    return null;
                };

                const getAbsoluteXPath = (node) => {
                    if (node === document.body) return 'xpath=/html/body';
                    if (!node.parentNode) return '';
                    let ix = 0;
                    let siblings = node.parentNode.childNodes;
                    for (let i = 0; i < siblings.length; i++) {
                        let sibling = siblings[i];
                        if (sibling === node) return getAbsoluteXPath(node.parentNode) + '/' + node.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                        if (sibling.nodeType === 1 && sibling.tagName === node.tagName) ix++;
                    }
                    return '';
                };

                const getRelativeXPath = (elm) => {
                    const anchor = getAnchor(elm);
                    if (!anchor) return null;
                    // Build a path from anchor to elm.
                    // Playwright does NOT support "css >> xpath=./div[1]/..." with a leading dot,
                    // so we convert the path to a CSS child combinator chain instead.
                    const anchorNode = anchor.node;
                    const parts = [];
                    let node = elm;
                    while (node && node !== anchorNode && node !== document.body) {
                        let ix = 0;
                        let siblings = node.parentNode.childNodes;
                        for (let i = 0; i < siblings.length; i++) {
                            let sibling = siblings[i];
                            if (sibling === node) {
                                parts.unshift(`${node.tagName.toLowerCase()}:nth-of-type(${ix + 1})`);
                                break;
                            }
                            if (sibling.nodeType === 1 && sibling.tagName === node.tagName) ix++;
                        }
                        node = node.parentElement;
                    }
                    if (parts.length) {
                        return {
                            selector: `${anchor.selector} > ${parts.join(' > ')}`,
                            strategy: 'relative-css-path',
                            confidence: 'low',
                            warnings: ['相对路径依赖局部 DOM 结构']
                        };
                    }
                    return null;
                };

                const makeResult = (selector, strategy, confidence, warnings=[]) => ({
                    selector, strategy, confidence, warnings
                });

                window.getSmartSelector = (elm) => {
                    const tagName = elm.tagName;
                    const lowerTag = tagName.toLowerCase();

                    // P1: test attributes (self, then nearest ancestor)
                    for (let attr of testAttrs) {
                        if (elm.hasAttribute(attr)) {
                            const val = elm.getAttribute(attr);
                            if (val && !isDynamicString(val)) {
                                return makeResult(`[${attr}="${escapeText(val)}"]`, 'test-attribute', 'high');
                            }
                        }
                    }
                    const testAncestor = findTestAttrAncestor(elm);
                    if (testAncestor) {
                        return makeResult(`[${testAncestor.attr}="${escapeText(testAncestor.val)}"]`, 'test-attribute', 'high');
                    }

                    // P2: stable static ID
                    if (elm.id && !isDynamicString(elm.id)) {
                        return makeResult('#' + CSS.escape(elm.id), 'static-id', 'high');
                    }

                    // P3: parent id anchor (only when the tag is unique under the anchor)
                    const idAncestor = findStableIdAncestor(elm);
                    if (idAncestor) {
                        const anchorSel = '#' + CSS.escape(idAncestor.id);
                        const directCount = countBySelector(`${anchorSel} > ${lowerTag}`);
                        const descendantCount = countBySelector(`${anchorSel} ${lowerTag}`);
                        // 唯一性不够：必须确认命中元素就是 elm 自身。
                        // 否则会出现"#app 下只有一个直接子 div(.app-wrapper)"时返回
                        // #app > div，但用户点中的是深层嵌套的"视频"div，命中错位。
                        if (directCount === 1) {
                            const hit = document.querySelector(`${anchorSel} > ${lowerTag}`);
                            if (hit === elm) {
                                return makeResult(`${anchorSel} > ${lowerTag}`, 'parent-id-anchor', 'high');
                            }
                        }
                        if (directCount === 0 && descendantCount === 1) {
                            const hit = document.querySelector(`${anchorSel} ${lowerTag}`);
                            if (hit === elm) {
                                return makeResult(`${anchorSel} >> ${lowerTag}`, 'parent-id-anchor', 'high');
                            }
                        }
                        // If not unique or not hitting elm, anchor may still be used by later strategies
                    }

                    // P4: ElementUI framework text
                    const containers = [
                        '.el-autocomplete-suggestion',
                        '.el-select-dropdown',
                        '.el-cascader__dropdown',
                        '.el-cascader-menu',
                        '.el-dropdown-menu',
                        '.el-popover'
                    ];
                    const container = containers.find(c => elm.closest(c));
                    if (container) {
                        const li = elm.closest('li') || elm.closest('.el-select-dropdown__item') || elm.closest('.el-cascader-node');
                        if (li) {
                            const text = li.innerText ? li.innerText.trim().split('\\n')[0] : '';
                            if (text) {
                                const liTag = li.tagName.toLowerCase();
                                return makeResult(`${container} ${liTag}:visible >> text="${escapeText(text)}"`, 'elementui-text', 'medium');
                            }
                        }
                    }

                    // P5: semantic attributes
                    for (let attr of semanticAttrs) {
                        if (elm.hasAttribute(attr)) {
                            const val = elm.getAttribute(attr);
                            if (val && !isDynamicString(val)) {
                                const safeVal = escapeText(val);
                                // 1. globally unique
                                if (countBySelector(`[${attr}="${safeVal}"]`) === 1) {
                                    return makeResult(`[${attr}="${safeVal}"]`, 'semantic-attr', 'high');
                                }
                                // 2. tag scoped unique
                                if (countBySelector(`${lowerTag}[${attr}="${safeVal}"]`) === 1) {
                                    return makeResult(`${lowerTag}[${attr}="${safeVal}"]`, 'semantic-attr', 'high');
                                }
                                // 3. parent id anchor
                                const anc = idAncestor || findStableIdAncestor(elm);
                                if (anc) {
                                    const anchorSel = '#' + CSS.escape(anc.id);
                                    if (countBySelector(`${anchorSel} [${attr}="${safeVal}"]`) === 1) {
                                        return makeResult(`${anchorSel} >> [${attr}="${safeVal}"]`, 'semantic-attr', 'high');
                                    }
                                }
                                // 4. parent unique class
                                const uniqueClassAnc = findUniqueClassAncestor(elm);
                                if (uniqueClassAnc) {
                                    if (countBySelector(`.${uniqueClassAnc.cls} [${attr}="${safeVal}"]`) === 1) {
                                        return makeResult(`.${uniqueClassAnc.cls} >> [${attr}="${safeVal}"]`, 'semantic-attr', 'high');
                                    }
                                }
                            }
                        }
                    }

                    // P6: label association (for form controls)
                    if (isFormControl(tagName)) {
                        let labelText = null;
                        let labelMode = null; // 'implicit', 'explicit', 'adjacent'
                        let associatedFor = null; // for explicit label[for] fallback

                        // Implicit label: label wraps input
                        let implicitLabel = elm.closest('label');
                        if (implicitLabel) {
                            labelText = implicitLabel.innerText.trim();
                            labelMode = 'implicit';
                        }

                        // Explicit label: label[for=element.id]
                        if (!labelText && elm.id) {
                            const explicitLabel = document.querySelector(`label[for="${CSS.escape(elm.id)}"]`);
                            if (explicitLabel) {
                                labelText = explicitLabel.innerText.trim();
                                labelMode = 'explicit';
                                associatedFor = elm.id;
                            }
                        }

                        // ElementUI / horizontal form: label[for] and control share a form-item ancestor
                        if (!labelText) {
                            const labels = document.querySelectorAll('label[for]');
                            for (const lbl of labels) {
                                const forVal = lbl.getAttribute('for');
                                if (!forVal || isDynamicString(forVal)) continue;

                                // The label and the control must belong to the same form-item.
                                // Walk up from the label to find its nearest .el-form-item (or generic form item) container.
                                let formItem = lbl.closest('.el-form-item');
                                if (!formItem) {
                                    let node = lbl.parentElement;
                                    while (node && node !== document.body) {
                                        if (node.contains(elm)) { formItem = node; break; }
                                        node = node.parentElement;
                                    }
                                }
                                if (!formItem || !formItem.contains(elm)) continue;

                                labelText = lbl.innerText.trim();
                                labelMode = 'explicit';
                                associatedFor = forVal;
                                break;
                            }
                        }

                        // Adjacent label/span: previous sibling inside same parent
                        if (!labelText) {
                            const parent = elm.parentElement;
                            if (parent) {
                                const siblings = Array.from(parent.children);
                                const idx = siblings.indexOf(elm);
                                for (let i = idx - 1; i >= 0; i--) {
                                    const sib = siblings[i];
                                    if (['LABEL', 'SPAN'].includes(sib.tagName)) {
                                        const t = sib.innerText.trim();
                                        if (t) { labelText = t; labelMode = 'adjacent'; break; }
                                    }
                                }
                            }
                        }

                        if (labelText) {
                            const safeLabel = escapeText(labelText);

                            // Prefer human-readable selectors based on the label text.
                            // Playwright supports "label:has-text(...) ~ ..." style selectors.
                            if (labelMode === 'implicit') {
                                return makeResult(`label:has-text("${safeLabel}") >> ${lowerTag}`, 'label-association', 'high');
                            }

                            if (labelMode === 'explicit') {
                                if (countVisibleLabelsByText(labelText) === 1) {
                                    const eluiPattern = `label:has-text("${safeLabel}") ~ .el-form-item__content ${lowerTag}`;
                                    return makeResult(eluiPattern, 'label-text-association', 'high');
                                }
                            }

                            // Fallback to label[for] if the label text is not unique enough.
                            if (associatedFor) {
                                const safeFor = escapeText(associatedFor);
                                const siblingPattern = `label[for="${safeFor}"] ~ .el-form-item__content ${lowerTag}`;
                                if (countBySelector(siblingPattern) === 1) {
                                    return makeResult(siblingPattern, 'label-for-association', 'high');
                                }
                                const genericPattern = `label[for="${safeFor}"] ~ * ${lowerTag}`;
                                if (countBySelector(genericPattern) === 1) {
                                    return makeResult(genericPattern, 'label-for-association', 'high');
                                }
                            }

                            // For explicit/adjacent: use ancestor :has-text() disambiguation.
                            // Native querySelectorAll does not support :has-text(), so we count manually.
                            const anc = idAncestor || findStableIdAncestor(elm);
                            if (anc) {
                                const anchorSel = '#' + CSS.escape(anc.id);
                                if (countHasTextTag(anc, labelText, lowerTag) === 1) {
                                    return makeResult(`${anchorSel}:has-text("${safeLabel}") >> ${lowerTag}`, 'label-association', 'medium');
                                }
                            }
                            // Walk up tree to find any ancestor tag where :has-text(label) + tag is unique
                            let bucket = elm.parentElement;
                            while (bucket) {
                                const bucketTag = bucket.tagName.toLowerCase();
                                if (countHasTextTag(bucket, labelText, lowerTag) === 1) {
                                    return makeResult(`${bucketTag}:has-text("${safeLabel}") >> ${lowerTag}`, 'label-association', 'medium');
                                }
                                if (bucket === document.body) break;
                                bucket = bucket.parentElement;
                            }
                        }
                    }

                    // P7: visible text (excluding form controls)
                    if (!isFormControl(tagName)) {
                        const text = elm.innerText ? elm.innerText.trim() : '';
                        if (text && text.length > 0 && text.length <= 30) {
                            if (['BUTTON', 'A', 'SPAN', 'LI', 'LABEL', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'DIV'].includes(tagName)) {
                                const safeText = escapeText(text);
                                const totalMatches = countVisibleByText(text);
                                if (totalMatches === 1) {
                                    return makeResult(`text="${safeText}"`, 'visible-text', 'medium');
                                }
                                const tagMatches = countVisibleByText(text, tagName);
                                if (tagMatches === 1) {
                                    // 注意：判定用的是【可见】元素数，但选择器 `tag >> text=`
                                    // 执行时会匹配所有同标签元素（含不可见），Playwright 取首个
                                    // 若恰好不可见则超时。追加 >> visible=true 使执行语义与判定一致。
                                    return makeResult(`${lowerTag} >> text="${safeText}" >> visible=true`, 'visible-text', 'medium');
                                }
                                // parent id anchor
                                const anc = idAncestor || findStableIdAncestor(elm);
                                if (anc) {
                                    const anchorSel = '#' + CSS.escape(anc.id);
                                    if (countVisibleByText(text, null, anc) === 1) {
                                        return makeResult(`${anchorSel} >> text="${safeText}"`, 'visible-text', 'medium');
                                    }
                                }
                                // parent unique class
                                const uniqueClassAnc = findUniqueClassAncestor(elm);
                                if (uniqueClassAnc) {
                                    if (countVisibleByText(text, null, uniqueClassAnc.node) === 1) {
                                        return makeResult(`.${uniqueClassAnc.cls} >> text="${safeText}"`, 'visible-text', 'medium');
                                    }
                                }
                            }
                        }
                    }

                    // P8: unique class combination (count only visible elements)
                    if (elm.className && typeof elm.className === 'string') {
                        const classes = getFilteredClasses(elm);
                        if (classes.length > 0) {
                            // Try combinations from largest to smallest
                            for (let size = classes.length; size >= 1; size--) {
                                for (let i = 0; i <= classes.length - size; i++) {
                                    const combo = classes.slice(i, i + size);
                                    const selector = '.' + combo.join('.');
                                    if (countVisibleBySelector(selector) === 1) {
                                        return makeResult(selector, 'unique-class', 'medium');
                                    }
                                }
                            }
                        }
                    }

                    // P9: relative XPath if anchor exists
                    const rel = getRelativeXPath(elm);
                    if (rel) return rel;

                    // P10: absolute XPath fallback
                    return makeResult(getAbsoluteXPath(elm), 'absolute-xpath', 'low', ['绝对 XPath 较脆弱，建议手动优化']);
                };

                window.pickerClick = (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    const result = getSmartSelector(e.target);
                    // Remove highlight
                    if (highlighted) highlighted.style.outline = '';
                    window.elementClicked(result);
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

        self._ensure_page(bring_to_front=False)

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
                self._ensure_page(bring_to_front=False)
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
                 write_ok = False
                 for attempt in range(3):
                     try:
                         df.to_excel(excel_path, index=False)
                         write_ok = True
                         self.log(f"已记录 '{status_val}' 到Excel的第 {i+1} 行")
                         break
                     except PermissionError as exc:
                         if attempt < 2:
                             self.log(f"写入Excel被占用，第 {attempt + 1} 次重试...", "WARNING")
                             time.sleep(1)
                         else:
                             self.log(f"写入Excel失败(权限被拒绝): 第 {i+1} 行结果未持久化，请关闭Excel后重试。", "ERROR")
                     except Exception as exc:
                         self.log(f"写入Excel失败: {exc}", "ERROR")
                         break
                 if not write_ok:
                     # Fallback: write to backup file
                     try:
                         backup_dir = os.path.join(os.path.dirname(os.path.abspath(excel_path)), "backup")
                         if not os.path.exists(backup_dir):
                             os.makedirs(backup_dir)
                         base_name = os.path.splitext(os.path.basename(excel_path))[0]
                         backup_path = os.path.join(backup_dir, f"{base_name}_backup_{time.strftime('%Y%m%d_%H%M%S')}.xlsx")
                         df.to_excel(backup_path, index=False)
                         self.log(f"已写入备份文件: {backup_path}", "WARNING")
                     except Exception as backup_exc:
                         self.log(f"备份写入也失败: {backup_exc}", "ERROR")

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

    def _internal_highlight(self, selector):
        """
        在页面上高亮指定选择器匹配到的所有元素，2 秒后自动清除。
        返回 {"count": N}。
        """
        self._ensure_page(bring_to_front=False)
        if not selector:
            return {"count": 0, "error": "选择器为空"}

        try:
            loc = self.page.locator(selector)
            count = loc.count()
        except Exception as e:
            return {"count": 0, "error": f"选择器无效: {e}"}

        if count == 0:
            return {"count": 0}

        # 给所有匹配元素加红色 outline
        try:
            self.page.evaluate("""(sel) => {
                const els = document.querySelectorAll(sel);
                els.forEach(el => {
                    el.__orig_outline = el.style.outline;
                    el.style.outline = '2px solid red';
                });
            }""", selector)
        except Exception:
            # querySelectorAll 对 Playwright 引擎选择器（如 >> visible=true）可能不兼容，
            # 改用 locator 逐个标注
            for i in range(count):
                try:
                    loc.nth(i).evaluate("el => { el.__orig_outline = el.style.outline; el.style.outline = '2px solid red'; }")
                except Exception:
                    pass

        # 2 秒后清除
        self.page.wait_for_timeout(2000)
        try:
            self.page.evaluate("""(sel) => {
                const els = document.querySelectorAll(sel);
                els.forEach(el => {
                    el.style.outline = el.__orig_outline || '';
                    delete el.__orig_outline;
                });
            }""", selector)
        except Exception:
            for i in range(count):
                try:
                    loc.nth(i).evaluate("el => { el.style.outline = el.__orig_outline || ''; delete el.__orig_outline; }")
                except Exception:
                    pass

        return {"count": count}

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

    def highlight(self, selector):
        return self._submit("_internal_highlight", selector)

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

def highlight_selector(selector):
    return _debug_session.highlight(selector)

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
