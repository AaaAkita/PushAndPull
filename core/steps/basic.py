import time
from .base import BaseStep
from .registry import StepRegistry

class WaitStep(BaseStep):
    def execute(self):
        raw_time = self.config.get('time', 1000)
        wait_time = int(raw_time)
        
        # Interruptible sleep
        chunk = 0.5
        waited = 0
        while waited < (wait_time / 1000.0):
             if self.should_stop(): break
             time.sleep(chunk)
             waited += chunk
             
        self.log(f"已等待 {wait_time}ms")
        return True

class OpenUrlStep(BaseStep):
    def execute(self):
        config = self.config
        raw_url = config.get('url')
        url = None

        if raw_url:
            url = self.replace_vars(raw_url)
            self.context.page.goto(url)
            self.log(f"已打开: {url}")

        # Check for auto-login configuration
        if url and config.get('loginUserSelector') and config.get('loginPassSelector'):
            self._handle_auto_login(url)

        return True

    def _handle_auto_login(self, target_url):
        page = self.context.page
        config = self.config
        # Login flow may need more time than normal test-mode 2s; use a dedicated longer timeout.
        login_timeout = self.get_timeout(10000)

        try:
            self.log(f"[自动登录] 等待页面稳定 (目标: {target_url})")
            time.sleep(2)
            current_url = page.url
            current_url_base = current_url.split('?')[0]
            target_url_base = target_url.split('?')[0]
            self.log(f"[自动登录] 当前 URL: {current_url}")

            if current_url_base == target_url_base:
                self.log("[自动登录] 当前 URL 与目标一致，无需登录")
                return

            user_sel = config.get('loginUserSelector')
            resolved_user_sel = self.resolve_sel(self.replace_vars(user_sel))
            self.log(f"[自动登录] 检测账号输入框: {resolved_user_sel}")
            try:
                page.wait_for_selector(resolved_user_sel, state='visible', timeout=login_timeout)
            except Exception as wait_err:
                self.log(f"[自动登录] 未检测到登录表单，跳过: {wait_err}", "WARNING")
                return

            self.log("检测到登录页面，尝试自动登录...")

            user_val = self.replace_vars(str(config.get('loginUser')))
            self.log(f"[自动登录] 填充账号: {user_val}")
            page.fill(resolved_user_sel, user_val, timeout=login_timeout)

            pass_sel = config.get('loginPassSelector')
            if pass_sel:
                resolved_pass_sel = self.resolve_sel(self.replace_vars(pass_sel))
                pass_val = self.replace_vars(str(config.get('loginPass')))
                self.log(f"[自动登录] 填充密码")
                page.fill(resolved_pass_sel, pass_val, timeout=login_timeout)

            btn_sel = config.get('loginBtnSelector')
            if btn_sel:
                resolved_btn_sel = self.resolve_sel(self.replace_vars(btn_sel))
                self.log(f"[自动登录] 点击登录按钮: {resolved_btn_sel}")
                page.click(resolved_btn_sel, timeout=login_timeout)
            else:
                # No explicit login button: try submitting from password field.
                self.log("[自动登录] 未配置登录按钮，尝试回车提交")
                page.press(resolved_pass_sel if pass_sel else resolved_user_sel, 'Enter', timeout=login_timeout)

            self.log("[自动登录] 等待登录请求完成...")
            page.wait_for_load_state('networkidle', timeout=login_timeout)
            time.sleep(3)

            self.log(f"重新打开目标URL (登录后): {target_url}")
            page.goto(target_url)
            page.wait_for_load_state('domcontentloaded', timeout=login_timeout)
        except Exception as e:
            self.log(f"自动登录逻辑异常: {e}", "ERROR")

# Register
StepRegistry.register('wait', WaitStep)
StepRegistry.register('open_url', OpenUrlStep)
