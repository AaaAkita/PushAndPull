from .base import BaseStep, FatalStepError
from .registry import StepRegistry
import time
import os
import re

class ClickStep(BaseStep):
    def execute(self):
        raw_selector = self.config.get('selector')
        selector = self.resolve_sel(self.replace_vars(raw_selector))
        
        if selector:
            page = self.context.page
            try:
                # Smart Selector Logic: Fix ambiguity by preferring visible elements
                # Check immediately if multiple elements exist
                loc = page.locator(selector)
                if loc.count() > 1:
                    # Try refining to visible only
                    vis_conf = f"({selector}) >> visible=true"
                    vis_count = page.locator(vis_conf).count()
                    
                    if vis_count > 0:
                        # If we have visible candidates, use them instead of the potentially hidden first match
                        self.log(f"检测到歧义 ({loc.count()} 个匹配). 自动优化为 {vis_count} 个可见元素.")
                        selector = vis_conf
            except Exception as e:
                # If checking count fails (e.g. invalid selector), ignore and let click() handle it
                pass

            # We don't have current_timeout passed in context yet, defaulting to 30s or page default
            # Ideally context should have timeout config
            timeout = self.get_timeout()
            self.context.page.click(selector, timeout=timeout) 
            self.log(f"已点击: {selector}")
        return True

class InputTextStep(BaseStep):
    def execute(self):
        config = self.config
        raw_selector = config.get('selector')
        input_type = config.get('inputType', 'fixed')
        raw_value = config.get('value', '')

        selector = self.resolve_sel(self.replace_vars(raw_selector))

        if input_type == 'excel':
            # Excel column mode: raw_value is the column name.
            # Guard against stale/invalid column names so we fail loudly
            # instead of silently filling an empty string into the page.
            if raw_value not in self.context.row:
                msg = (f"输入失败: Excel 中找不到列 '{raw_value}'"
                       f"（可用列: {list(self.context.row.keys())}）")
                self.log(msg, "ERROR")
                raise FatalStepError(msg)
            value = str(self.context.row.get(raw_value, ""))
        else:
            value = self.replace_vars(str(raw_value))

        if selector:
            page = self.context.page
            handle = page.query_selector(selector)
            if handle:
                is_editable = handle.evaluate("el => !el.readOnly && !el.disabled")
                if not is_editable:
                    self.log("输入失败: 目标元素为只读或禁用状态", "ERROR")
                    return False
            page.fill(selector, value, timeout=self.get_timeout())
            # 关键修复：fill() 不会触发 Vue/ElementUI 的事件监听（keyup/input），
            # 导致依赖输入联想的组件（如 el-autocomplete）不会弹出建议项。
            # 主动派发 input 事件，让框架感知到值变化。
            # 优先用已取得的 handle（兼容 Playwright 引擎选择器），回退用 querySelector。
            try:
                if handle:
                    handle.evaluate("el => { el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }")
                else:
                    page.evaluate("""(sel) => {
                        const el = document.querySelector(sel);
                        if (el) { el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }
                    }""", selector)
            except Exception:
                pass
            self.log(f"已输入 '{value}' 到 {selector}")

        return True

class LabelInputStep(BaseStep):
    def execute(self):
        config = self.config
        page = self.context.page
        
        raw_selector = config.get('selector')
        input_type = config.get('inputType', 'fixed')
        raw_value = config.get('value', '')
        
        selector = self.resolve_sel(self.replace_vars(raw_selector))

        if input_type == 'excel':
            if raw_value not in self.context.row:
                msg = (f"标签输入失败: Excel 中找不到列 '{raw_value}'"
                       f"（可用列: {list(self.context.row.keys())}）")
                self.log(msg, "ERROR")
                raise FatalStepError(msg)
            value = str(self.context.row.get(raw_value, ""))
        else:
            value = self.replace_vars(str(raw_value))
            
        if not selector:
            self.log("标签输入失败: 选择器缺失", "ERROR")
            return False

        # 1. Fill Text
        page.fill(selector, value, timeout=self.get_timeout())
        self.log(f"标签输入: 已输入 '{value}'")
        
        # 2. Press Enter to confirm/save
        page.press(selector, "Enter", timeout=self.get_timeout())
        
        # 3. Short wait for UI reaction
        time.sleep(0.5)
        
        # 4. Clear Input (Select All + Backspace usually safer than fill('') if logic requires triggering events)
        # But fill("") is standard Playwright way.
        # 4. Clear Input (Select All + Backspace usually safer than fill('') if logic requires triggering events)
        # But fill("") is standard Playwright way.
        page.fill(selector, "", timeout=self.get_timeout())
        self.log(f"标签输入: 已清空字段")
        
        return True

class UploadFileStep(BaseStep):
    def execute(self):
        config = self.config
        page = self.context.page
        
        raw_selector = config.get('selector')
        raw_path = config.get('filePath')
        input_type = config.get('inputType', 'fixed')
        
        selector = self.resolve_sel(self.replace_vars(raw_selector))
        
        if input_type == 'excel':
            if raw_path not in self.context.row:
                msg = (f"上传失败: Excel 中找不到列 '{raw_path}'"
                       f"（可用列: {list(self.context.row.keys())}）")
                self.log(msg, "ERROR")
                raise FatalStepError(msg)
            file_path = str(self.context.row.get(raw_path, ""))
        else:
            file_path = self.replace_vars(raw_path)
        
        # Normalize path: strip whitespace, fix mixed slashes, prevent double-concatenation
        file_path = file_path.strip()
        file_path = os.path.normpath(file_path)

        if not os.path.exists(file_path):
            self.log(f"上传失败: 文件不存在 '{file_path}'", "ERROR")
            return False

        if not selector or not file_path:
            self.log("上传失败: 选择器或文件路径缺失", "ERROR")
            return False

        try:
            # We should probably handle timeout better here
            timeout = self.get_timeout()
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
            return True

        except Exception as e:
             raise e

class DropdownSelectStep(BaseStep):
    # 已知的下拉面板 popper 容器（ElementUI / Ant / vue-treeselect / 通用）。
    # 点击 trigger 后，选项通常被 teleport 到 body 下的某个 popper 节点里。
    # 通用 optionSelector（如 'li'）若在全页面搜索，会误命中侧边栏导航菜单的 li，
    # 因此必须先把搜索范围限定到「真正的下拉面板容器」内。
    _PANEL_SELECTORS = [
        # ElementUI 自动补全联想面板（实测：trigger [role="region"] 即此容器，
        # li 文本为目标值，面板有离场动画类时 is_visible()=False 但 li 仍可点）
        '.el-autocomplete-suggestion',
        '.el-select-dropdown',
        '.el-cascader-panel',
        '.el-cascader-menu',
        '.el-cascader__dropdown',
        '.el-dropdown-menu',
        '.el-popover',
        '.el-popper',
        '.el-tree-select__popper',
        '.vue-treeselect__menu-container',
        '.ant-select-dropdown',
        '.ant-cascader-menu',
        '.ant-tree',
        '.ant-popover',
    ]
    # 侧边栏导航区域：通用 optionSelector 全页面兜底搜索时需排除，
    # 否则会把「首页 / 用户 / 机构」这类菜单项当成下拉选项。
    _NAV_SELECTORS = ['.el-menu', '.el-aside', 'aside', 'nav', '.sidebar', '.ant-menu']

    @staticmethod
    def _normalize(s):
        return re.sub(r'\s+', '', s or '')

    @staticmethod
    def _safe_is_visible(handle):
        """is_visible() 在某些 teleport 元素上会抛异常，统一兜底。"""
        try:
            return handle.is_visible()
        except Exception:
            return False

    @staticmethod
    def _trigger_looks_like_panel(trigger_sel):
        """
        判断 trigger 选择器是否本身就是「下拉/联想面板容器」。
        实测：流程里 trigger='[role="region"]' 实为 .el-autocomplete-suggestion 面板，
        点击它会收起面板而非展开。识别后应跳过点击。
        """
        if not trigger_sel:
            return False
        s = trigger_sel.lower()
        # role=region 是 ElementUI autocomplete suggestion 的默认 role
        if 'role="region"' in s or "role='region'" in s:
            return True
        # 直接选中已知面板类名
        panel_markers = [
            'el-autocomplete-suggestion', 'el-select-dropdown', 'el-cascader',
            'el-dropdown-menu', 'el-popover', 'el-popper', 'el-tree-select__popper',
            'vue-treeselect__menu-container', 'ant-select-dropdown', 'ant-cascader',
            'ant-popover', 'el-cascader-panel', 'el-cascader-menu',
        ]
        return any(m in s for m in panel_markers)

    def _locate_panel(self, page, option_sel, target_val=None):
        """
        定位「真正的下拉面板容器」。

        实测（详见 logs + Playwright 探测）：
        - trigger `[role="region"]` 实为 ElementUI `.el-autocomplete-suggestion` 联想面板。
        - 面板有离场动画类(el-zoom-in-top-leave)时 is_visible()=False，但内部 li 仍可点击。
        - 通用 optionSelector='li' 全页面搜索会命中侧边栏导航 99 个 li，淹没目标值。
        - 页面可能同时存在多个面板（如企业分类 select-dropdown 与账号 autocomplete），
          必须优先选「含目标值」的那个，否则会误选无关下拉。

        策略：
          1. 在已知 popper 容器选择器里找「含 option_sel 元素」的容器。
             不强制 is_visible()（autocomplete 面板动画态会误判不可见）。
             优先级：含目标值文本 > 含非空文本项 > 选项数多。
          2. 兜底：用 evaluate 在页面内找含 option_sel 的 popper 节点。
          3. 最后兜底：全页面搜 option_sel，但排除侧边栏导航区域内的元素。

        返回: (panel_desc: str, options: list[ElementHandle])
        """
        target_norm = self._normalize(target_val) if target_val else ''

        def _opts_match_target(opts):
            """容器内是否有 li 文本包含/等于目标值。"""
            if not target_norm:
                return False
            for o in opts[:50]:
                try:
                    t = self._normalize(o.inner_text())
                except Exception:
                    continue
                if not t:
                    continue
                if t == target_norm or target_norm in t or t in target_norm:
                    return True
            return False

        # --- 策略 1: 已知容器选择器（不强制可见，优先含目标值/非空文本项）---
        candidates = []  # [(sel, opts, has_target, has_nonempty)]
        for sel in self._PANEL_SELECTORS:
            try:
                containers = page.query_selector_all(sel)
            except Exception:
                continue
            for c in containers:
                try:
                    opts = c.query_selector_all(option_sel)
                except Exception:
                    continue
                if not opts:
                    continue
                has_target = _opts_match_target(opts)
                # 检测是否有非空文本项（排除 loading 占位空 li）
                has_nonempty = False
                for o in opts[:20]:
                    try:
                        if o.inner_text().strip():
                            has_nonempty = True
                            break
                    except Exception:
                        pass
                candidates.append((sel, opts, has_target, has_nonempty))
        if candidates:
            # 优先级：含目标值 > 含非空文本 > 选项数多
            candidates.sort(key=lambda x: (x[2], x[3], len(x[1])), reverse=True)
            sel, opts, has_target, has_nonempty = candidates[0]
            self.log(f"[下拉诊断] 命中面板容器 '{sel}'，含 {len(opts)} 个 '{option_sel}'，含目标值={has_target} 非空={has_nonempty}")
            return sel, opts

        # --- 策略 2: 页面内动态发现含 option_sel 的 popper 节点（不强制可见）---
        try:
            discovered = page.evaluate("""(optSel) => {
                const hasSize = (n) => {
                    if (!n) return false;
                    const r = n.getBoundingClientRect();
                    if (r.width === 0 && r.height === 0) return false;
                    const st = getComputedStyle(n);
                    if (st.display === 'none') return false;
                    return true;
                };
                const popperHints = ['popper','dropdown','menu','tree','listbox','cascader','select','suggestion','autocomplete'];
                const nodes = [];
                document.querySelectorAll('*').forEach(el => {
                    if (!hasSize(el)) return;
                    const cls = (el.className && typeof el.className === 'string') ? el.className.toLowerCase() : '';
                    const role = (el.getAttribute('role') || '').toLowerCase();
                    const tag = el.tagName.toLowerCase();
                    const hit = popperHints.some(h => cls.includes(h) || role.includes(h));
                    if (!hit) return;
                    let count = 0, nonempty = 0;
                    try {
                        const lis = el.querySelectorAll(optSel);
                        count = lis.length;
                        for (const li of lis) {
                            const t = (li.innerText || '').trim();
                            if (t) nonempty++;
                        }
                    } catch (e) { count = 0; }
                    if (count > 0) {
                        const marker = '__panel_' + nodes.length;
                        nodes.push({tag: tag, cls: cls.slice(0,80), role: role, count: count, nonempty: nonempty, marker: marker});
                        el.setAttribute('__panel_marker', marker);
                    }
                });
                return nodes;
            }""", option_sel)
            if discovered:
                self.log(f"[下拉诊断] 动态发现 {len(discovered)} 个候选 popper 容器: " +
                         ", ".join(f"{n['tag']}#{n.get('marker')}(共{n['count']}/非空{n['nonempty']})" for n in discovered[:5]))
                # 优先含非空文本项的容器
                discovered.sort(key=lambda n: (n.get('nonempty',0), n['count']), reverse=True)
                best = discovered[0]
                marker = best['marker']
                try:
                    container = page.query_selector(f"[__panel_marker='{marker}']")
                    if container:
                        opts = container.query_selector_all(option_sel)
                        if opts:
                            try: page.evaluate("document.querySelectorAll('[__panel_marker]').forEach(e=>e.removeAttribute('__panel_marker'))")
                            except Exception: pass
                            self.log(f"[下拉诊断] 选中动态容器 {best['tag']}.{best['cls'][:40]}，含 {len(opts)} 个选项(非空{best['nonempty']})")
                            return f"dynamic({best['tag']})", opts
                except Exception as e:
                    self.log(f"[下拉诊断] 动态容器定位异常: {e}", "WARNING")
                try: page.evaluate("document.querySelectorAll('[__panel_marker]').forEach(e=>e.removeAttribute('__panel_marker'))")
                except Exception: pass
        except Exception as e:
            self.log(f"[下拉诊断] 动态发现 popper 失败: {e}", "WARNING")

        # --- 策略 3: 全页面兜底，但排除侧边栏导航 ---
        self.log(f"[下拉诊断] 未定位到独立面板容器，回退全页面搜索并排除导航区域", "WARNING")
        all_opts = page.query_selector_all(option_sel)
        excluded = 0
        filtered = []
        for o in all_opts:
            in_nav = False
            try:
                in_nav = o.evaluate("""(el, navSels) => navSels.some(s => el.closest(s))""", self._NAV_SELECTORS)
            except Exception:
                pass
            if in_nav:
                excluded += 1
            else:
                filtered.append(o)
        self.log(f"[下拉诊断] 全页面 '{option_sel}' 共 {len(all_opts)} 个，排除导航 {excluded} 个，剩余 {len(filtered)} 个")
        return "global-no-nav", filtered

    def execute(self):
        config = self.config
        page = self.context.page
        row = self.context.row
        
        trigger_sel = self.resolve_sel(self.replace_vars(config.get('selector')))
        option_sel = config.get('optionSelector', 'li') 
        
        input_type = config.get('inputType', 'fixed')
        raw_val = config.get('value', '')
        
        if input_type == 'excel':
            if raw_val not in row:
                msg = (f"下拉选择失败: Excel 中找不到列 '{raw_val}'"
                       f"（可用列: {list(row.keys())}）")
                self.log(msg, "ERROR")
                raise FatalStepError(msg)
            target_val = str(row.get(raw_val, ""))
        else:
            target_val = self.replace_vars(raw_val)

        if not trigger_sel: 
            self.log("下拉选择失败: 触发选择器缺失", "ERROR")
            return False
        elif not target_val:
            self.log("下拉选择警告: 目标值为空", "WARNING")
            return True # Not a hard failure?

        # 1. Click Trigger
        # 关键修复：若 trigger 选择器本身就是「下拉/联想面板容器」（如 [role="region"]
        # 实测为 .el-autocomplete-suggestion），点击它会收起面板而非展开——
        # 这种情况下不应点击 trigger，面板通常已由上一步输入触发打开。
        trigger_is_panel = self._trigger_looks_like_panel(trigger_sel)
        if trigger_is_panel:
            self.log(f"[下拉诊断] trigger '{trigger_sel}' 疑似面板容器自身，跳过点击（避免收起面板）")
        else:
            try:
                page.click(trigger_sel, timeout=self.get_timeout())
                self.log(f"已点击触发: {trigger_sel}")
            except Exception as e:
                self.log(f"点击触发失败: {e}，尝试继续定位面板", "WARNING")

        # 等待下拉面板动画展开
        page.wait_for_timeout(500)

        target_norm = self._normalize(target_val)
        self.log(f"[下拉诊断] 目标值='{target_val}' (normalized='{target_norm}'), optionSelector='{option_sel}'")

        # 等待选项出现（在全页面层面等待，避免容器尚未挂载时容器内等待立即超时）
        try:
            page.wait_for_selector(option_sel, state='visible', timeout=5000)
        except:
            self.log(f"Warning: Option selector '{option_sel}' 5s 内未出现", "WARNING")

        # 关键修复：把选项搜索范围限定到「下拉面板容器」内。
        # 之前用 page.query_selector_all('li') 全页面搜索，会误命中侧边栏导航菜单的 li
        # （首页/用户/机构...），导致目标值（机构名）永远匹配不到。
        panel_desc, options = self._locate_panel(page, option_sel, target_val)

        visible_options = [o for o in options if self._safe_is_visible(o)]
        self.log(f"[下拉诊断] 面板 '{panel_desc}' 内 '{option_sel}' 共 {len(options)} 个，可见 {len(visible_options)} 个")

        # 打印前 30 个可见选项的文本（截断到 40 字符），用于排查是否选错了 DOM 范围
        sample_texts = []
        for o in visible_options[:30]:
            try:
                t = o.inner_text().strip().replace('\n', '\\n')[:40]
                sample_texts.append(f"'{t}'")
            except:
                sample_texts.append("'<读取失败>'")
        if sample_texts:
            self.log(f"[下拉诊断] 可见选项样本: {', '.join(sample_texts)}")

        # ===== 完整值优先匹配 =====
        # 不限制 is_visible()：Element/Ant 等组件常用 teleport 把选项挂到 body，
        # 但因弹窗遮罩/z-index 导致 Playwright is_visible() 返回 False，
        # 实际上它们在屏幕上是可见可点击的。
        full_match = None
        full_match_text = ""
        for opt in options:
            try:
                text = opt.inner_text().strip()
            except:
                continue
            if not text:
                continue
            text_norm = self._normalize(text)
            # 精确 / normalized 相等 / target 是选项子串
            if text == target_val or text_norm == target_norm or (target_norm and target_norm in text_norm):
                full_match = opt
                full_match_text = text
                self.log(f"[下拉诊断] 完整值命中: '{text}'", "INFO")
                break

        if full_match:
            try:
                full_match.scroll_into_view_if_needed()
            except:
                pass
            try:
                full_match.click(force=True)
                page.wait_for_timeout(100)
                self.log(f"Selected Target: '{full_match_text}'")
                return True
            except Exception as click_e:
                # 选项不可点击（如面板未真正展开、元素被遮挡），不直接抛异常中断流程，
                # 降级到级联匹配；若级联也失败再返回 False。
                self.log(f"[下拉诊断] 完整值命中但点击失败: {click_e}，降级级联匹配", "WARNING")

        # 完整值未命中（或命中但点击失败），尝试级联拆分
        if not full_match:
            self.log(f"[下拉诊断] 完整值未命中，尝试级联拆分", "WARNING")

        # ===== 级联路径匹配 =====
        path_parts = []
        if '/' in target_val: path_parts = target_val.split('/')
        elif '-' in target_val: path_parts = target_val.split('-')
        elif '>' in target_val: path_parts = target_val.split('>')
        else: path_parts = [target_val]

        path_parts = [p.strip() for p in path_parts if p.strip()]
        self.log(f"[下拉诊断] 级联拆分: {path_parts}")
        
        for idx, part in enumerate(path_parts):
            if self.should_stop(): break

            # 2. Wait for options
            try:
                if idx > 0: page.wait_for_timeout(500)
                page.wait_for_selector(option_sel, state='visible', timeout=5000)
            except:
                self.log(f"Warning: Option selector '{option_sel}' not found for level {idx+1}", "WARNING")
                if idx == 0: return False # Fail if first level missing

            # 3. Find and Click —— 复用面板定位逻辑，避免再次误命中侧边栏导航 li
            _, candidate_options = self._locate_panel(page, option_sel, target_val)
            found = False
            best_match = None
            match_text = ""

            part_normalized = self._normalize(part)
            is_last = (idx == len(path_parts) - 1)

            self.log(f"[下拉诊断] Level {idx+1}: 搜索 '{part}' (normalized='{part_normalized}'), "
                     f"候选选项 {len(candidate_options)} 个, is_last={is_last}")

            for opt in candidate_options:
                try:
                    text = opt.inner_text().strip()
                except:
                    continue
                text_normalized = self._normalize(text)

                # Strategy 1: Exact Match
                if text == part:
                    best_match = opt
                    match_text = text
                    self.log(f"[下拉诊断] Level {idx+1} 精确命中: '{text}'")
                    break

                # Strategy 2: Start-With Match
                if not best_match and text.startswith(part):
                    best_match = opt
                    match_text = text
                    self.log(f"[下拉诊断] Level {idx+1} startswith 命中: '{text}' (for '{part}')")
                    break

                # Strategy 3: Substring Match
                if not best_match and part in text:
                    best_match = opt
                    match_text = text
                    self.log(f"[下拉诊断] Level {idx+1} 子串命中: '{text}' (for '{part}')")
                    break

                # Strategy 4: Normalized Substring Match
                if not best_match and part_normalized in text_normalized:
                    best_match = opt
                    match_text = text
                    self.log(f"[下拉诊断] Level {idx+1} normalized 命中: '{text}'")
                    break

            if best_match:
                opt = best_match
                try:
                    opt.scroll_into_view_if_needed()
                except Exception:
                    pass

                # 关键修复：如果匹配到的选项文本等于完整 target_val，说明是叶子节点被误拆，
                # 直接选中返回，不继续当父节点展开
                best_norm = self._normalize(match_text)
                if best_norm == target_norm:
                    self.log(f"[下拉诊断] 命中选项等于完整目标值，识别为叶子节点，直接选中")
                    try:
                        opt.click(force=True)
                        page.wait_for_timeout(100)
                        self.log(f"Selected Target: '{match_text}'")
                        return True
                    except Exception as click_e:
                        self.log(f"[下拉诊断] 叶子节点点击失败: {click_e}", "WARNING")
                        return False

                if is_last:
                    try:
                        opt.click(force=True)
                        page.wait_for_timeout(100)
                        # Conditional Enter: Press only if it's a multi-level path (Cascader often needs confirmation)
                        if len(path_parts) > 1:
                            page.keyboard.press("Enter")
                        self.log(f"Selected Target: '{match_text}'")
                    except Exception as click_e:
                        self.log(f"[下拉诊断] 末级选项点击失败: {click_e}", "WARNING")
                        return False
                else:
                    expand_method = config.get('expandMethod', 'hover')
                    try:
                        if expand_method == 'click':
                            opt.click(force=True)
                            self.log(f"Clicked Parent: '{match_text}'")
                        else:
                            opt.hover(force=True)
                            self.log(f"Hovered Parent: '{match_text}'")
                    except Exception as click_e:
                        self.log(f"[下拉诊断] 父级展开失败: {click_e}", "WARNING")
                        return False

                page.wait_for_timeout(500)
                found = True

            if not found:
                # 调试输出：列出所有候选选项文本，方便用户排查
                available_texts = []
                for o in candidate_options[:20]:
                    try:
                        t = o.inner_text().strip().replace('\n', '\\n')[:40]
                        available_texts.append(f"'{t}'")
                    except:
                        available_texts.append("'<读取失败>'")
                self.log(f"Dropdown Option '{part}' not found. "
                        f"Candidate options ({len(candidate_options)}): {', '.join(available_texts)}", "WARNING")
                return False

        # Optional extra Enter after entire dropdown operation
        extra = config.get('extraEnter')
        should_extra_enter = False
        try:
            # Treat 1/true/'1' as enabled, ignore 0/false/''
            if isinstance(extra, bool):
                should_extra_enter = extra
            elif isinstance(extra, (int, float)):
                should_extra_enter = extra != 0
            elif isinstance(extra, str):
                should_extra_enter = extra.strip().lower() not in ("", "0", "false", "no", "off")
        except Exception:
            should_extra_enter = False

        if should_extra_enter:
            try:
                page.keyboard.press("Enter")
                self.log("额外执行一次回车以确认下拉选择")
            except Exception as e:
                self.log(f'额外回车失败: {e}', 'WARNING')

        return True

# Register
class KeyboardStep(BaseStep):
    def execute(self):
        config = self.config
        page = self.context.page
        
        raw_key = config.get('key', '')
        count = int(config.get('count', 1))
        raw_selector = config.get('selector')
        
        # 1. Optional Focus
        if raw_selector:
            selector = self.resolve_sel(self.replace_vars(raw_selector))
            if selector:
                try:
                    # Click is generally the best way to ensure focus for typing
                    page.click(selector, timeout=self.get_timeout())
                    self.log(f"Focused (Clicked): {selector}")
                    # Short wait to ensure focus effects (like cursor appearance)
                    time.sleep(0.2)
                except Exception as e:
                    self.log(f"Focus click warning: {e}", "WARNING")
                    # We continue even if click fails, trying to press key anyway
        
        # Resolve vars
        key = self.replace_vars(raw_key)
        
        if not key:
            self.log("Keyboard step skipped: No key specified", "WARNING")
            return True
            
        self.log(f"Pressing '{key}' {count} times...")
        
        for i in range(count):
            if self.should_stop(): break
            
            try:
                page.keyboard.press(key)
                if count > 1: time.sleep(0.1) 
            except Exception as e:
                self.log(f"Keyboard press failed: {e}", "ERROR")
                return False
                
        return True

# Register
StepRegistry.register('click', ClickStep)
StepRegistry.register('input_text', InputTextStep)
StepRegistry.register('label_input', LabelInputStep)
StepRegistry.register('upload_file', UploadFileStep)
StepRegistry.register('dropdown_select', DropdownSelectStep)
StepRegistry.register('keyboard', KeyboardStep)
