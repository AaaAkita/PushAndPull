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
        
        if raw_url:
            url = self.replace_vars(raw_url)
            self.context.page.goto(url)
            self.log(f"已打开: {url}")
            
        # Check for auto-login configuration
        if config.get('loginUserSelector') and config.get('loginPassSelector'):
            self._handle_auto_login(url)
            
        return True

    def _handle_auto_login(self, target_url):
        page = self.context.page
        config = self.config
        
        try:
            time.sleep(2)
            current_url_base = page.url.split('?')[0]
            target_url_base = target_url.split('?')[0]

            if current_url_base != target_url_base:
                user_sel = config.get('loginUserSelector')
                try: 
                    page.wait_for_selector(self.resolve_sel(user_sel), state='visible', timeout=2000) 
                except:
                    return # Login not found

                self.log("检测到登录页面，尝试自动登录...")
                
                user_val = self.replace_vars(str(config.get('loginUser')))
                page.fill(self.resolve_sel(self.replace_vars(user_sel)), user_val)
                
                pass_sel = config.get('loginPassSelector')
                if pass_sel:
                    pass_val = self.replace_vars(str(config.get('loginPass')))
                    page.fill(self.resolve_sel(self.replace_vars(pass_sel)), pass_val)
                
                btn_sel = config.get('loginBtnSelector')
                if btn_sel:
                    page.click(self.resolve_sel(self.replace_vars(btn_sel)))
                
                page.wait_for_load_state('networkidle')
                time.sleep(3)
                
                self.log(f"重新打开目标URL (登录后): {target_url}")
                page.goto(target_url)
                page.wait_for_load_state('domcontentloaded')
        except Exception as e:
            self.log(f"自动登录逻辑警告: {e}", "WARNING")

# Register
StepRegistry.register('wait', WaitStep)
StepRegistry.register('open_url', OpenUrlStep)
