# 设计：点击步骤标题自动命名 + 选择器即时高亮

日期：2026-06-25

## 背景

用户调试中反复出现"步骤标题都是泛名（点击元素/输入文本），分不清是哪一步"以及"拾取器生成的选择器匹配错/超时，却要靠跑测试才能发现"的问题。本设计实现两点改进：
1. 点击类步骤拾取选择器后，标题自动带上提取到的文本（如"点击 编辑"）
2. 选择器输入框旁加高亮按钮，点击即在页面标红匹配元素，2 秒自动清除

## 功能 1：点击步骤标题自动命名

### 触发时机
`pickSelector` 拾取成功后。

### 规则
- 仅对 `click` 类型步骤生效（先只应用到点击元素上）
- 从拾取到的 selector 中提取文本内容（匹配 `text="..."` 段，取第一个）
  - `text="编辑"` → "编辑"
  - `.el-table__fixed-right >> text="编辑"` → "编辑"
  - `span >> text="保存" >> visible=true` → "保存"
- 生成标题：`点击 {文本}`，如 `点击 编辑`、`点击 保存`
- 提取不到文本（XPath/纯 class/id 等无 text= 段）→ 标题保持不变，不强行命名

### 用户手动改过的标题不被覆盖
- 用 `step.config._titleAuto` 标记位区分：
  - 拾取自动生成时设为 `true`
  - 用户在"步骤名称"输入框编辑时（updateConfig 改 title）清为 `false`
  - 下次拾取只覆盖 `_titleAuto === true` 或未设置的标题
- `_titleAuto` 不入持久化的必要字段，但随 config 存 json 无害（前端忽略即可）

### summary 显示
`renderCanvas` 中 click 步骤的 summary 行显示标题（已含"点击 编辑"），无需额外处理。

## 功能 2：选择器即时高亮

### 位置
`createSelectorInput` 渲染的选择器输入框旁（现有 🎯 拾取按钮旁），加一个 🔍 高亮按钮。

### 交互
- 点击 → 前端调 `/api/highlight_selector`，传当前 selector
- 后端在 Playwright 页面执行 JS：
  - 用 `page.locator(selector).all()` 拿到所有匹配元素
  - 给每个元素加红色 outline（2px solid red）
  - 2 秒后自动移除 outline
  - 返回匹配数量
- 前端 alert 反馈：`高亮 N 个元素（2秒后自动清除）` 或 `未匹配到元素` 或 `选择器无效`

### 后端实现
- `core/engine.py` 新增 `_internal_highlight(selector)` 方法
  - 调用 `self.page.locator(selector).all()` 取元素
  - 对每个元素 `evaluate` 注入红色 outline
  - `self.page.wait_for_timeout(2000)` 后清除
  - 返回 `{"count": N}`
- 导出 `highlight_selector(selector)` 供 server 调用

### 前端实现
- `static/js/modules/api.js` 新增 `highlightSelectorAPI(selector)` → POST `/api/highlight_selector`
- `static/js/main.js` 新增 `highlightSelector(configKey)` 函数：取当前 step 的 selector，调 API，alert 结果
- `static/js/modules/ui.js` 的 `createSelectorInput` 在 🎯 按钮后加 🔍 按钮，onclick 调 `highlightSelector('{pureKey}')`

### 复用
高亮按钮对所有带 `createSelectorInput` 的步骤都生效（click/input_text/open_url 登录字段等），不止 click。按钮是通用的，放在选择器输入框旁统一出现。

## 涉及文件

| 文件 | 改动 |
|------|------|
| `core/engine.py` | 新增 `_internal_highlight(selector)` 方法 + 导出 `highlight_selector` |
| `server.py` | 新增 `/api/highlight_selector` 路由 |
| `static/js/modules/api.js` | 新增 `highlightSelectorAPI(selector)` |
| `static/js/main.js` | `pickSelector` 拾取成功后自动命名 click 步骤 + 清 `_titleAuto`；新增 `highlightSelector` 函数 |
| `static/js/modules/ui.js` | `createSelectorInput` 加 🔍 高亮按钮 |

## 边界情况
- `text="编辑"` → "编辑" ✓
- `.el-table__fixed-right >> text="编辑"` → "编辑" ✓
- `xpath=//*[@id="x"]` → 无 text= → 不改名 ✗
- `#app > div` → 无 text= → 不改名 ✗
- 高亮时选择器无效 → 后端 try/except，返回 count=0 + 错误信息
- 高亮时页面已关闭 → 复用现有错误处理
