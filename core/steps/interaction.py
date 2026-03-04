from .base import BaseStep
from .registry import StepRegistry
import time

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
            value = str(self.context.row.get(raw_value, ""))
        else:
            value = self.replace_vars(str(raw_value))
        
        if selector:
            self.context.page.fill(selector, value, timeout=self.get_timeout())
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
            file_path = str(self.context.row.get(raw_path, ""))
        else:
            file_path = self.replace_vars(raw_path)
        
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
    def execute(self):
        config = self.config
        page = self.context.page
        row = self.context.row
        
        trigger_sel = self.resolve_sel(self.replace_vars(config.get('selector')))
        option_sel = config.get('optionSelector', 'li') 
        
        input_type = config.get('inputType', 'fixed')
        raw_val = config.get('value', '')
        
        if input_type == 'excel':
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
        page.click(trigger_sel, timeout=self.get_timeout())
        self.log(f"已点击触发: {trigger_sel}")
        
        # Normalize path
        path_parts = []
        if '/' in target_val: path_parts = target_val.split('/')
        elif '-' in target_val: path_parts = target_val.split('-')
        elif '>' in target_val: path_parts = target_val.split('>')
        else: path_parts = [target_val]
        
        path_parts = [p.strip() for p in path_parts if p.strip()]
        
        for idx, part in enumerate(path_parts):
            if self.should_stop(): break

            # 2. Wait for options
            try:
                if idx > 0: page.wait_for_timeout(500)
                page.wait_for_selector(option_sel, state='visible', timeout=5000)
            except:
                self.log(f"Warning: Option selector '{option_sel}' not found for level {idx+1}", "WARNING")
                if idx == 0: return False # Fail if first level missing

            # 3. Find and Click
            # 3. Find and Click
            options = page.query_selector_all(option_sel)
            found = False
            best_match = None
            match_text = ""

            # Filter visible options to avoid repeated calls
            visible_options = []
            for opt in options:
                if opt.is_visible():
                    visible_options.append(opt)

            # Strategy 1: Exact Match (High Priority)
            for opt in visible_options:
                text = opt.inner_text().strip()
                if text == part:
                    best_match = opt
                    match_text = text
                    self.log(f"Found Exact Match: '{text}'")
                    break
            
            # Strategy 2: Partial Match (Fallback)
            if not best_match:
                for opt in visible_options:
                    text = opt.inner_text().strip()
                    if part in text:
                        best_match = opt
                        match_text = text
                        self.log(f"Found Partial Match: '{text}' (for '{part}')")
                        break
            
            if best_match:
                opt = best_match
                opt.scroll_into_view_if_needed()
                is_last = (idx == len(path_parts) - 1)
                
                if is_last:
                    opt.click(force=True)
                    page.wait_for_timeout(100)
                    # Conditional Enter: Press only if it's a multi-level path (Cascader often needs confirmation)
                    if len(path_parts) > 1:
                        page.keyboard.press("Enter")
                    self.log(f"Selected Target: '{match_text}'")
                else:
                    expand_method = config.get('expandMethod', 'hover')
                    if expand_method == 'click':
                        opt.click(force=True)
                        self.log(f"Clicked Parent: '{match_text}'")
                    else:
                        opt.hover(force=True)
                        self.log(f"Hovered Parent: '{match_text}'")
                
                page.wait_for_timeout(500) 
                found = True
            
            if not found:
                self.log(f"Dropdown Option '{part}' not found", "WARNING")
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
