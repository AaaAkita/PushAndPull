import os
import sys
import shutil
import subprocess
import platform

def build():
    # 1. Cleaning up previous builds
    print("Cleaning up previous builds...")
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    if os.path.exists('build'):
        shutil.rmtree('build')

    # 2. Running PyInstaller
    print("Running PyInstaller...")
    
    # Define hidden imports
    hidden_imports = [
        'pandas',
        'playwright.sync_api',
        'playwright.async_api',
        'flask',
        'eventlet', # If used by flask-socketio or similar, though not seen in requirements
        'engineio',
    ]
    
    cmd = [
        'pyinstaller',
        'launcher.py',
        '--name', 'AutomaticScriptTool',
        '--onedir',
        '--noconfirm',
        '--clean',
        '--windowed', # GUI mode
        # Include data folders
        '--add-data', 'static;static',
        '--add-data', 'core;core', 
        '--add-data', 'flows;flows',
        # '--add-data', 'README.md;.', # User might want to read this
        # Exclude conflicting Qt bindings (we use Tkinter)
        '--exclude-module', 'PyQt5',
        '--exclude-module', 'PyQt6', 
        '--exclude-module', 'torch',
        '--exclude-module', 'scipy',
        '--exclude-module', 'sympy',
        '--exclude-module', 'matplotlib',
        '--exclude-module', 'IPython',
        '--exclude-module', 'notebook',
        '--exclude-module', 'tensorflow',
        '--exclude-module', 'keras',
        '--exclude-module', 'tensorboard',
    ]
    
    for imp in hidden_imports:
        cmd.extend(['--hidden-import', imp])
        
    subprocess.run(cmd, check=True)
    
    # 3. Copying Playwright Browsers
    print("Copying Playwright Browsers...")
    dist_dir = os.path.join('dist', 'AutomaticScriptTool')
    target_browsers_dir = os.path.join(dist_dir, 'browsers')
    
    # Locating local playwright browsers
    # Default is %LOCALAPPDATA%\ms-playwright on Windows
    local_app_data = os.environ.get('LOCALAPPDATA')
    if not local_app_data:
        print("Error: LOCALAPPDATA environment variable not found.")
        return
        
    source_browsers_dir = os.path.join(local_app_data, 'ms-playwright')
    
    if os.path.exists(source_browsers_dir):
        print(f"Found browsers at {source_browsers_dir}")
        # Only copy chromium/chrome related folders
        if not os.path.exists(target_browsers_dir):
            os.makedirs(target_browsers_dir)
            
        for item in os.listdir(source_browsers_dir):
            if 'chromium' in item.lower() or 'chrome' in item.lower() or 'ffmpeg' in item.lower():
                s = os.path.join(source_browsers_dir, item)
                d = os.path.join(target_browsers_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d)
                    print(f"Copied {item}")
        
        print("Selected browsers copied successfully.")
    else:
        print(f"Warning: Playwright browsers not found at {source_browsers_dir}")
        print("You may need to run 'playwright install' manually or copy the browsers folder yourself.")

    # 4. Create start script (optional, but good for one-click if user wants console)
    # But since we are --windowed, the exe is the entry point.
    
    print("Build complete. Output in dist/AutomaticScriptTool")

if __name__ == "__main__":
    build()
