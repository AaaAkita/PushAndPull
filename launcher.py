import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import subprocess
import threading
import sys
import json
import os
import signal
import time

# Use the directory of the launcher script as the base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(BASE_DIR, "server.py")

class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Visual Playwright 编辑器 - 启动器")
        self.root.geometry("600x450")
        
        self.server_process = None
        self.is_running = False
        
        self.create_widgets()

    def create_widgets(self):
        # Control Frame
        control_frame = ttk.LabelFrame(self.root, text="服务控制 (Service Control)", padding="10")
        control_frame.pack(fill="x", padx=10, pady=5)

        self.start_btn = ttk.Button(control_frame, text="启动服务", command=self.start_service)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = ttk.Button(control_frame, text="停止服务", command=self.stop_service, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        self.restart_btn = ttk.Button(control_frame, text="重启服务", command=self.restart_service, state="disabled")
        self.restart_btn.pack(side="left", padx=5)
        
        ttk.Button(control_frame, text="打开编辑器界面", command=self.open_ui).pack(side="right", padx=5)

        # Log Frame
        log_frame = ttk.LabelFrame(self.root, text="运行日志 (Logs)", padding="10")
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_area = scrolledtext.ScrolledText(log_frame, state='disabled', height=15)
        self.log_area.pack(fill="both", expand=True)
        # Configure tag for red text
        self.log_area.tag_config("error", foreground="red")

        # Status Bar
        self.status_var = tk.StringVar(value="状态: 已停止")
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        self.status_bar.pack(side="bottom", fill="x")

    def log_message(self, msg, is_error=False):
        self.log_area.config(state='normal')
        tag = "error" if is_error else None
        self.log_area.insert(tk.END, msg + "\n", tag)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def cleanup_port(self, port):
        """Check and kill process occupying the port."""
        try:
            # Prevent console window popping up
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            # Find PID
            proc = subprocess.run(f"netstat -ano | findstr :{port}", shell=True, capture_output=True, text=True, startupinfo=startupinfo)
            if proc.returncode != 0:
                return # Port not in use directly or no output

            lines = proc.stdout.strip().split('\n')
            pids = set()
            for line in lines:
                parts = line.strip().split()
                # Check if local address matches port
                if len(parts) >= 5 and f":{port}" in parts[1]:
                    pids.add(parts[-1])
            
            for pid in pids:
                if pid == "0": continue
                self.log_message(f"端口 {port} 被占用 (PID: {pid})，正在清理...", True)
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True, startupinfo=startupinfo)
                self.log_message(f"已结束进程 {pid}。")
                
        except Exception as e:
            self.log_message(f"清理端口失败: {e}", True)

    def start_service(self):
        if self.is_running:
            return
        
        self.cleanup_port(6115)
        
        self.log_message("正在启动服务器...")
        try:
            # Run using python in unbuffered mode equivalent (-u) env var or direct call
            # Using same python executable
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            
            if getattr(sys, 'frozen', False):
                 # Packaged mode: run self with --server argument
                 cmd = [sys.executable, "--server"]
                 cwd = os.path.dirname(sys.executable) # Exec in exe dir
                 
                 # Set PLAYWRIGHT_BROWSERS_PATH to the 'browsers' directory next to the executable
                 browsers_path = os.path.join(cwd, 'browsers')
                 if os.path.exists(browsers_path):
                     self.log_message(f"使用内置浏览器路径: {browsers_path}")
                     env["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
            else:
                 # Script mode
                 cmd = [sys.executable, SERVER_SCRIPT]
                 cwd = BASE_DIR

            self.server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
                cwd=cwd
            )
            self.is_running = True
            
            # Start threads to read output
            threading.Thread(target=self.read_output, args=(self.server_process.stdout, False), daemon=True).start()
            threading.Thread(target=self.read_output, args=(self.server_process.stderr, True), daemon=True).start()
            
            self.update_ui_state(running=True)
            self.status_var.set("状态: 运行中 (http://localhost:6115)")
            
        except Exception as e:
            self.log_message(f"启动失败: {e}", True)

    # ... (other methods unchanged) ...

    def read_output(self, pipe, is_error):
        try:
            for line in iter(pipe.readline, ''):
                if line:
                    self.root.after(0, self.log_message, line.strip(), is_error)
        except Exception:
            pass
        finally:
            if pipe: pipe.close()
            # If process ended unexpectedly
            if self.is_running and self.server_process and self.server_process.poll() is not None:
                self.root.after(0, self.handle_unexpected_stop)

    def handle_unexpected_stop(self):
        if self.is_running:
            self.log_message("服务器异常停止。", True)
            self.is_running = False
            self.update_ui_state(running=False)
            self.status_var.set("状态: 已停止 (异常)")

    def stop_service(self):
        if not self.is_running or not self.server_process:
            return
        
        self.log_message("正在停止服务器...")
        try:
            self.server_process.terminate()
            # Wait a bit
            try:
                self.server_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            
            self.is_running = False
            self.update_ui_state(running=False)
            self.status_var.set("状态: 已停止")
            self.log_message("服务器已停止。")
        except Exception as e:
            self.log_message(f"停止服务出错: {e}", True)

    def restart_service(self):
        self.stop_service()
        # Give it a moment to release ports etc
        self.root.after(1000, self.start_service)

    def update_ui_state(self, running):
        state_normal = "normal" if not running else "disabled"
        state_running = "normal" if running else "disabled"
        
        self.start_btn.config(state=state_normal)
        self.stop_btn.config(state=state_running)
        self.restart_btn.config(state=state_running)
        
    def open_ui(self):
        import webbrowser
        webbrowser.open("http://localhost:6115")

    def on_close(self):
        if self.is_running:
            if messagebox.askokcancel("退出", "服务器正在运行，确定要停止服务并退出吗？"):
                self.stop_service()
                self.root.destroy()
        else:
            self.root.destroy()

if __name__ == "__main__":
    if "--server" in sys.argv:
        # Running as server backend
        from server import run_server
        run_server()
    else:
        # Running as launcher GUI
        root = tk.Tk()
        app = LauncherApp(root)
        root.protocol("WM_DELETE_WINDOW", app.on_close)
        root.mainloop()
