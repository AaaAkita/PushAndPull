import os
import sys
import shutil
import subprocess
import platform

from playwright.sync_api import sync_playwright


def get_required_chromium_revision():
    """Return the chromium revision directory expected by the current playwright (e.g. 'chromium-1124')."""
    with sync_playwright() as p:
        exe = p.chromium.executable_path
    # exe is like ...\ms-playwright\chromium-1124\chrome-win\chrome.exe
    chromium_dir = os.path.basename(os.path.dirname(os.path.dirname(exe)))
    return chromium_dir


def build():
    # 1. Cleaning up previous builds
    print("Cleaning up previous builds...")
    dist_dir = os.path.join('dist', 'AutomaticScriptTool')
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    build_dir = os.path.join('build')
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

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
        if not os.path.exists(target_browsers_dir):
            os.makedirs(target_browsers_dir)

        required_revision = get_required_chromium_revision()
        print(f"当前 Playwright 需要的 Chromium 版本目录: {required_revision}")

        # Always copy the exact revision required by the playwright version used for packaging.
        required_source = os.path.join(source_browsers_dir, required_revision)
        if os.path.isdir(required_source):
            required_target = os.path.join(target_browsers_dir, required_revision)
            if os.path.exists(required_target):
                shutil.rmtree(required_target)
            shutil.copytree(required_source, required_target)
            print(f"Copied {required_revision}")
        else:
            print(f"Error: 未在 {source_browsers_dir} 找到 {required_revision}。请运行 'playwright install chromium'。")
            return

        # Also copy ffmpeg if present (optional helper binary).
        ffmpeg_dir = None
        for item in os.listdir(source_browsers_dir):
            if item.lower().startswith('ffmpeg') and os.path.isdir(os.path.join(source_browsers_dir, item)):
                ffmpeg_dir = item
                break
        if ffmpeg_dir:
            s = os.path.join(source_browsers_dir, ffmpeg_dir)
            d = os.path.join(target_browsers_dir, ffmpeg_dir)
            if os.path.exists(d):
                shutil.rmtree(d)
            shutil.copytree(s, d)
            print(f"Copied {ffmpeg_dir}")

        print("Selected browsers copied successfully.")
    else:
        print(f"Warning: Playwright browsers not found at {source_browsers_dir}")
        print("You may need to run 'playwright install' manually or copy the browsers folder yourself.")

    # 4. Create start script (optional, but good for one-click if user wants console)
    # But since we are --windowed, the exe is the entry point.
    
    print("Build complete. Output in dist/AutomaticScriptTool")

if __name__ == "__main__":
    build()
