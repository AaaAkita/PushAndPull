from flask import Flask, request, jsonify, send_from_directory
import os
import json
from core.engine import execute_flow, open_debug_browser, pick_debug_element

app = Flask(__name__, static_folder='static')

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/debug/open', methods=['POST'])
def debug_open():
    try:
        url = request.json.get('url')
        if not url: return jsonify({"status": "error", "message": "URL required"}), 400
        open_debug_browser(url)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/pick_selector', methods=['POST'])
def run_picker():
    try:
        data = request.json
        # url is optional now. If provided, it navigates. If not, picks from current page.
        url = data.get('url') # Can be None/Empty
        
        selector = pick_debug_element(url)
        if selector:
            return jsonify({"status": "success", "selector": selector})
        else:
            return jsonify({"status": "error", "message": "Selection timed out or failed"}), 408
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/browse_file', methods=['POST'])
def browse_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        # Create hidden root
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        file_path = filedialog.askopenfilename(
            title="选择 Excel 文件",
            filetypes=[("Excel files", "*.xlsx;*.xls")]
        )
        
        root.destroy()
        
        if file_path:
            return jsonify({"status": "success", "path": file_path})
        return jsonify({"status": "cancel", "message": "No file selected"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/get_excel_columns', methods=['POST'])
def get_excel_columns():
    try:
        import pandas as pd
        data = request.json
        file_path = data.get('path')
        
        if not file_path or not os.path.exists(file_path):
            return jsonify({"status": "error", "message": "File not found"}), 404
            
        df = pd.read_excel(file_path, nrows=0) # Read only headers
        columns = df.columns.tolist()
        
        return jsonify({"status": "success", "columns": columns})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/execution/start', methods=['POST'])
def start_execution():
    try:
        from core.engine import execute_flow_async
        data = request.json
        if not data: return jsonify({"status": "error", "message": "No data"}), 400
        
        mode = 'normal'
        if isinstance(data, dict):
            mode = data.get('mode', 'normal')
        
        execute_flow_async(data, mode=mode)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/execution/stop', methods=['POST'])
def stop_execution():
    try:
        from core.engine import stop_flow_execution
        stop_flow_execution()
        return jsonify({"status": "success"})
    except Exception as e:
         return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/execution/status', methods=['GET'])
def get_execution_status():
    try:
        from core.engine import get_flow_status
        status = get_flow_status()
        return jsonify({"status": "success", "data": status})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/run', methods=['POST'])
def run_flow():
    # Legacy synchronous run
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
        
        # Execute flow directly without external config merging
        mode = data.get('mode', 'normal')
        result = execute_flow(data, mode=mode)
        return jsonify({"status": "success", "result": result})
    except Exception as e:
        print(f"Error executing flow: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500



# Validates filename to prevent directory traversal
def _get_flow_path(filename):
    if not filename.endswith('.json'):
        filename += '.json'
    base = os.path.basename(filename) # Secure filename
    return os.path.join('flows', base)

# Ensure flows directory exists
if not os.path.exists('flows'):
    os.makedirs('flows')

@app.route('/api/flows', methods=['GET'])
def list_flows():
    try:
        files = [f for f in os.listdir('flows') if f.endswith('.json')]
        return jsonify({"status": "success", "flows": files})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/flows', methods=['POST'])
def save_flow_named():
    try:
        data = request.json
        name = data.get('name')
        steps = data.get('steps')
        
        if not name or steps is None:
            return jsonify({"status": "error", "message": "Name and steps required"}), 400
            
        path = _get_flow_path(name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"steps": steps}, f, indent=4, ensure_ascii=False)
            
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/flows/<name>', methods=['GET'])
def load_flow(name):
    try:
        path = _get_flow_path(name)
        if not os.path.exists(path):
            return jsonify({"status": "error", "message": "Flow not found"}), 404
            
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/flows/<name>', methods=['DELETE'])
def delete_flow(name):
    try:
        path = _get_flow_path(name)
        if os.path.exists(path):
            os.remove(path)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/flows/rename', methods=['POST'])
def rename_flow():
    try:
        data = request.json
        old_name = data.get('oldName')
        new_name = data.get('newName')
        
        if not old_name or not new_name:
             return jsonify({"status": "error", "message": "oldName and newName required"}), 400
             
        old_path = _get_flow_path(old_name)
        new_path = _get_flow_path(new_name)
        
        if not os.path.exists(old_path):
            return jsonify({"status": "error", "message": "Source flow not found"}), 404
            
        if os.path.exists(new_path):
             return jsonify({"status": "error", "message": "Destination flow already exists"}), 409
             
        os.rename(old_path, new_path)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Deprecated/Legacy direct save (overwrites default flow.json if no name)
@app.route('/api/save', methods=['POST'])
def save_flow():
    try:
        data = request.json
        # Check if it's the new format sent to old endpoint by mistake
        if 'steps' in data and 'name' in data:
            return save_flow_named()
            
        filename = data.get('filename', 'flow.json')
        # ... legacy logic ...
        if 'filename' in data:
            del data['filename']
            
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return jsonify({"status": "success", "message": "Flow saved successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def run_server():
    print("Starting server on http://localhost:6115")
    # Flush output immediately for launcher to catch it
    app.run(host='0.0.0.0', port=6115, debug=False, use_reloader=False)

if __name__ == '__main__':
    run_server()
