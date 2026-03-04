# Visual Playwright Editor (可视化自动化流程编辑器)

这是一个基于 Python Playwright 和 Flask 的可视化自动化流程编辑器。用户可以通过图形化界面（Web UI）拖拽组件来构建自动化任务，支持 Excel 数据读取、网页操作、智能分类映射等功能。

## 📁 目录结构

```text
VisualPlaywrightEditor/
├── core/                   # 核心逻辑模块
│   ├── engine.py           # 自动化引擎实现 (Playwright 封装)
│   ├── utils.py            # 通用工具函数
│   └── steps/              # 具体步骤实现逻辑
├── flows/                  # 流程存储目录 (JSON 格式)
│   └── *.json              # 保存的自动化方案
├── static/                 # 前端静态资源
│   ├── index.html          # 编辑器主界面
│   ├── app.js              # 前端逻辑
│   └── style.css           # 样式表
├── logs/                   # 运行日志
├── to_be_recycled/         # 待回收文件 (旧测试脚本/日志/压缩包)
├── user_data/              # 用户数据 (浏览器缓存等)
├── launcher.py             # [入口] 启动器 (Tkinter GUI)
├── server.py               # 后端服务 (Flask API)
└── requirements.txt        # 项目依赖
```

## 🚀 快速开始

### 1. 环境准备

确保已安装 Python 3.8+，然后安装依赖：

```bash
pip install -r requirements.txt
playwright install  # 安装浏览器驱动
```

### 2. 启动应用

运行启动器脚本：

```bash
python launcher.py
```

这将打开一个桌面控制窗口。点击 **"启动服务"** 按钮，然后点击 **"打开编辑器界面"** 即可在浏览器中开始使用。

## ✨ 主要功能

*   **可视化编排**：通过点击左侧组件库添加步骤。
*   **组件支持**：
    *   **打开链接 (Open URL)**：支持自动登录回退功能。
    *   **点击 / 输入**：支持从浏览器实时拾取元素选择器 (Selector Picker)。
    *   **Excel 读取**：读取本地 Excel 文件数据作为输入源。
    *   **智能映射**：根据 Excel 列值进行逻辑判断和操作映射。
*   **方案管理**：支持保存、加载、搜索和删除多种自动化方案。
*   **实时调试**：支持单步运行和浏览器实时交互调试。

## 🛠️ 技术栈

*   **Backend**: Python, Flask, Playwright, Pandas
*   **Frontend**: HTML5, Vanilla JavaScript, TailwindCSS (CDN), FontAwesome
*   **GUI**: Tkinter (用于服务管理)

## 📝 注意事项

*   **文件路径**：Excel 读取和文件操作建议使用绝对路径。
*   **调试模式**：使用 "测试打开" 或 "拾取元素" 功能时，系统会启动一个调试用的浏览器窗口，请勿手动关闭该窗口，否则需要重启服务。
