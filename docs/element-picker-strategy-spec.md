# 元素拾取策略规范 v1.4（Element Picker Strategy Spec）

## 1. 目标

规范智能元素拾取器生成选择器的优先级与判定规则，降低对绝对 XPath 的依赖，提高生成选择器的稳定性与可维护性。

## 2. 设计原则

1. **语义优先**：优先使用带有业务语义或测试意图的属性/文本。
2. **稳定性优先**：优先选择不易随页面结构调整而变化的定位方式。
3. **框架感知**：针对 ElementUI 等常用组件库做专门优化。
4. **可见性优先**：生成的选择器应尽量指向用户可见的元素，避免命中隐藏/占位节点。
5. **可解释性**：生成的选择器应便于用户理解其指向的内容。

## 3. 策略优先级（从高到低）

| 优先级 | 策略 | 说明 |
|-------|------|------|
| P1 | 测试属性（data-testid / data-id / data-qa / data-automation-id） | 专为自动化测试预留的属性，语义最明确 |
| P2 | 稳定静态 ID | 非动态生成的 `id` 属性 |
| P3 | 父级 ID 锚定 | 元素自身无静态 ID 时，向上查找最近带静态 ID 的祖先 |
| P4 | ElementUI / 框架专用文本选择器 | 结合框架类名与可见文本 |
| P5 | 语义属性 | placeholder、name、aria-label、title、role 等 |
| P6 | Label 关联定位 | 通过 label 文本定位表单控件 |
| P7 | 可见文本 + 限定 | 文本在限定范围内唯一 |
| P8 | 唯一类组合 | 类名组合在页面内唯一 |
| P9 | 相对 XPath | 基于附近可识别父级的 XPath |
| P10 | 绝对 XPath | 完整 DOM 路径，最后兜底 |

## 4. 各策略判定规则

### 4.1 测试属性（P1）

**候选属性**：
- `data-testid`
- `data-id`
- `data-qa`
- `data-automation-id`

**生成规则**：
```css
[data-testid="submit-order"]
[data-id="user-name-input"]
```

**判定条件**：
- 元素本身或最近可定位的父级存在上述属性之一。
- 属性值非空，且不包含明显动态内容（如 4 位以上连续数字、随机 hash）。

**优先级理由**：
- 这类属性是开发者专门为测试/自动化预留的，变更成本高。
- 不依赖页面结构、文本内容或样式类名。

---

### 4.2 稳定静态 ID（P2）

**生成规则**：
```css
#username
#login-form
```

**动态 ID 过滤规则**：
以下情况视为动态 ID，不采用：
- 包含 4 位以上连续数字（如 `id-4296-name`）
- 匹配 ElementUI 模式：`el-autocomplete-\d+`、`el-select-\d+`
- 匹配 Vue scoped：`^v-\d+`
- 匹配通用随机 ID：`^uid-\d+`

**ID 选择器转义**：
- 使用 `CSS.escape(id)` 处理包含特殊字符的 ID，再生成 `#` 选择器。

**判定条件**：
- 元素本身存在非动态 ID。

**优先级理由**：
- ID 在标准 HTML 中应该是唯一的，命中效率高。
- 但部分前端框架会生成动态 ID，需过滤后使用。

---

### 4.3 父级 ID 锚定（P3）

**适用场景**：
元素自身没有稳定 ID，但其祖先元素存在稳定 ID。

**生成规则**：
```css
#user-info-card >> input
#order-form >> button
#order-form >> button >> text="提交"
```

**判定条件**：
- 元素自身无稳定 ID（P2 未命中）。
- 向上遍历 DOM，找到最近的带稳定 ID 的祖先。
- 以该 ID 为锚点，结合元素标签名生成选择器。
- 若锚点下同类元素有多个，先尝试通过相邻 label 文本限定；若仍无法唯一，降级到 P9。

**与 P9 的边界**：
P3 只负责「锚点下标签名即唯一」的简单情况。若同类元素 ≥ 2 个，先尝试 label 文本限定；若仍无法唯一，降级到 P9 使用相对 XPath 精确定位。`nth-of-type` 等结构索引属于相对 XPath 范畴，不归入 P3。

**优先级理由**：
- 表单控件（input/select/textarea）通常自身没有语义 ID，但常位于有 ID 的卡片/表单项内。
- 相比绝对 XPath，只依赖局部结构，抗结构性调整能力更强。

---

### 4.4 ElementUI / 框架专用文本选择器（P4）

**适用场景**：
元素位于以下 ElementUI 容器内：
- `.el-autocomplete-suggestion`
- `.el-select-dropdown`
- `.el-cascader__dropdown`
- `.el-cascader-menu`
- `.el-dropdown-menu`
- `.el-popover`

**生成规则**：
```css
.el-select-dropdown li:visible >> text="选项A"
.el-cascader__dropdown .el-cascader-node:visible >> text="北京市"
```

**判定条件**：
- 元素位于已知的框架容器内。
- 能提取到非空的可见文本。

**优先级理由**：
- 当前工具大量操作 ElementUI 后台系统，这是高命中场景。
- `:visible` 过滤能避免命中隐藏的下拉项。

---

### 4.5 语义属性（P5）

**候选属性**：
- `placeholder`
- `name`
- `aria-label`
- `title`
- `role`

**生成规则**：
```css
input[placeholder="请输入用户名"]
[name="email"]
[aria-label="搜索"]
```

**判定条件**：
- 属性值非空，且不包含明显动态内容。

**歧义消解递进流程**：
当属性值在页面上不唯一时，按以下顺序扩大限定范围：

1. **全页唯一**：
   ```css
   [name="email"]
   ```

2. **标签名限定**：
   ```css
   input[name="email"]
   ```

3. **父级 ID 锚定**：
   ```css
   #register-form >> [name="email"]
   ```

4. **父级唯一类**：
   ```css
   .register-panel >> [name="email"]
   ```

5. 仍无法唯一：降级到 P9 相对 XPath；若 P9 也找不到可用锚点，直接跳到 P10 绝对 XPath。

**优先级理由**：
- 属性通常由后端模板或开发者显式设定，变更频率低于可见文本。
- 对表单元素尤其有效，比文本更不容易受国际化 / 产品文案调整影响。

---

### 4.6 Label 关联定位（P6）

**适用场景**：
目标元素为表单控件：`INPUT`、`SELECT`、`TEXTAREA`。

**重要前提：Playwright `>>` 链是后代选择器**

`text="邮箱" >> input` 的语义是：在文本为"邮箱"的元素的**后代**中找 `input`。因此：
- 仅在 input 是 label 的后代（隐式 label）时，`label:has-text("...") >> input` 才成立。
- 显式 label 和相邻 label/span 与 input 是兄弟关系，`text="..." >> input` **不会命中**。

Playwright 不原生支持 CSS 兄弟选择器（`+`、`~`）。若必须用 label 文本定位兄弟 input，只能通过：
1. 公共祖先 + input 标签名/索引；
2. 相对 XPath；
3. `:has-text()` 匹配包含 label 文本的公共祖先，再 `>> input` 找后代。

**关联模式（按优先级）**：

1. **隐式 label**：`<label>手机号：<input></label>`
   - input 是 label 的后代，可直接使用 `>>`。
   - 生成示例：`label:has-text("手机号：") >> input`

2. **显式 label**：`<label for="email">邮箱</label><input id="email">`
   - label 与 input 是兄弟。P3 已先于 P6 执行：
     - 若公共父容器有稳定 ID 且该容器下只有一个同类控件，P3 会生成 `#form-section >> input`，流程不会进入 P6。
     - P6 处理的是 P3 未命中（父容器下有多个同类控件）的场景：用 `:has-text()` 匹配包含该 label 文本的祖先容器，再定位到目标 input。例如：`div:has-text("邮箱") >> input`
     - 仍无法唯一：降级到 P9 相对 XPath
   - **不生成** `text="邮箱" >> input` 这种错误选择器。

3. **相邻 label / span**：`<div><span>姓名</span><input></div>`
   - span 与 input 是兄弟。处理方式同显式 label：
     - 公共父容器有稳定 ID 且单控件场景已由 P3 覆盖。
     - P6 处理多控件场景：`:has-text()` 匹配公共祖先：`div:has-text("姓名") >> input`
     - 仍无法唯一：降级到 P9 相对 XPath

**非唯一文本消歧递进**：
当关联 label 文本在页面上不唯一时：

1. **公共父级有稳定 ID 且该容器下仅有一个同类控件**：
   - 该情况已由 P3 父级 ID 锚定覆盖（例如 `#shipping-section >> input`），不会进入 P6。

2. **P6 使用 `:has-text()` 匹配包含 label 文本的公共祖先**：
   ```css
   div:has-text("姓名") >> input
   ```

3. **仍歧义**：降级到 P9 相对 XPath；若 P9 也找不到可用锚点，直接跳到 P10 绝对 XPath。

**动态 ID 边界警告**：
> ⚠️ 即使控件 ID 被 P2 判定为动态 ID 而过滤，仍可通过 `label[for="<动态id>"]` 查找到关联 label，但**仅提取 label 文本作为锚点**生成选择器，切勿将动态 `for` 属性值写入最终选择器。

**判定条件**：
- 目标元素标签为 `INPUT`、`SELECT`、`TEXTAREA`。
- 能提取到非空的关联 label 文本，或存在可定位的公共祖先容器。
- 最终生成的选择器在 Playwright `>>` 后代语义下能真正命中目标元素。

**优先级理由**：
- 表单控件自身 `innerText` 通常为空，无法直接用可见文本策略。
- Label 文本是用户直接看到的语义标识，稳定且可读。

---

### 4.7 可见文本 + 限定（P7）

**生成规则（按优先级递进）**：

1. 全页唯一文本：
   ```css
   text="提交订单"
   ```

2. 按标签名限定：
   ```css
   button >> text="提交"
   ```

3. 按父级 ID 限定：
   ```css
   #order-form >> text="提交"
   ```

4. 按父级唯一类限定：
   ```css
   .order-form >> text="提交"
   ```

**判定条件**：
- 文本长度在 1~30 个字符之间。
- 目标元素标签属于可点击/可输入语义标签：
  `BUTTON`、`A`、`SPAN`、`LI`、`LABEL`、`H1~H6`、`DIV`。
- **表单控件（`INPUT` / `SELECT` / `TEXTAREA`）不在 P7 处理范围内**，由 P6 Label 关联策略专门覆盖；P6 失败后由 P9/P10 兜底。
- 在限定范围内可见且唯一。

**优先级理由**：
- 文本是用户直接看到的内容，业务语义强。
- 在 P5/P6 之后作为通用回退，避免与更稳定的语义属性/label 冲突。

---

### 4.8 唯一类组合（P8）

**生成规则**：
```css
.login-panel .submit-btn.primary
```

**判定条件**：
- 过滤掉状态类、布局类、通用类：
  `is-active`、`hover`、`focus`、`selected`、`row`、`col`、`container`、`wrapper`、`active`、`show`、`flex`、`box`
- 组合后的类选择器在页面内唯一。
- 类组合唯一性判断时，仅统计可见元素。

**优先级理由**：
- 类名重构频率高于 ID 和属性，但仍比结构定位稳定。

---

### 4.9 相对 XPath（P9）

**生成规则**：
```css
#order-form >> xpath=.//input[1]
#user-info-card >> xpath=.//button[contains(text(),"提交")]
```

**判定条件**：
- 元素附近存在可用的 ID、测试属性或唯一类作为锚点。
- 从锚点出发的相对 XPath 在限定范围内唯一。
- 向上遍历祖先寻找锚点（不仅限于直接父级）。

**与 P5/P6 的衔接**：
当 P5 或 P6 消歧失败、降级到 P9 时，若页面中找不到任何可用锚点（无稳定 ID、无测试属性、无唯一类），则跳过 P9，直接使用 P10 绝对 XPath。

**优先级理由**：
- 相比绝对 XPath，只依赖局部结构，抗结构性调整能力更强。

---

### 4.10 绝对 XPath（P10）

**生成规则**：
```css
xpath=/html/body/div[1]/div[2]/main/div[3]/input[1]
```

**使用条件**：
- 以上所有策略均无法生成有效选择器。

**注意事项**：
- 生成的绝对 XPath 应标记为"脆弱"，建议用户在 UI 中可以看到风险提示。
- 可考虑在 UI 中提示"建议手动优化选择器"。

## 5. 通用过滤规则

### 5.1 动态内容过滤

以下特征视为动态内容，相关值不用于生成选择器：
- 4 位以上连续数字
- 32 位随机 hash（如 Vue scoped style 的 `data-v-7a7a37b9`）
- React 随机 ID：`id="root"` 之外的随机字符串
- 时间戳、UUID

### 5.2 可见性要求

- 文本匹配时，目标元素必须可见（`offsetParent !== null` 或 Playwright `:visible`）。
- 类组合唯一性判断时，仅统计可见元素。

### 5.3 歧义处理

- 当某策略在限定范围内匹配到多个元素时，应尝试扩大限定范围（向上追溯父级），而不是降级到下一策略。
- 向上遍历祖先时不应止于直接父级，应持续查找到 `document.body`。
- 若仍然歧义，再尝试下一优先级的策略。
- 降级到 P9 时，若页面无可用锚点，跳过 P9 直接使用 P10。

### 5.4 类名过滤列表

生成唯一类组合时需过滤的类名：

```
is-active, hover, focus, selected,
row, col, container, wrapper,
active, show, flex, box
```

状态类（`is-active`、`hover`、`focus`、`selected`）必须过滤，避免选择器随交互状态变化而失效。

## 6. 输出格式与兼容迁移

### 6.1 推荐输出格式

拾取器内部应返回结构化对象，便于前端展示选择器质量：

```json
{
  "selector": "[data-testid=\"submit-btn\"]",
  "strategy": "test-attribute",
  "confidence": "high",
  "warnings": []
}
```

兜底情况：

```json
{
  "selector": "xpath=/html/body/div[1]/div[2]/input[1]",
  "strategy": "absolute-xpath",
  "confidence": "low",
  "warnings": ["绝对 XPath 较脆弱，建议手动优化"]
}
```

### 6.2 confidence 等级定义

| 策略 | confidence | 理由 |
|------|-----------|------|
| P1 测试属性 | high | 开发者专为测试预留，变更需跨团队协调 |
| P2 静态 ID | high | ID 在 HTML 规范中应唯一 |
| P3 父级 ID 锚定 | high | 锚点 ID 稳定，子级用标签名限定 |
| P4 ElementUI 文本 | medium | 框架类名可能随组件库升级变化 |
| P5 语义属性 | high | placeholder / name 由开发者显式设定 |
| P6 Label 关联 | high | label 文本是业务语义标识，与 ID/属性同源 |

> **P6 内部路径说明**：隐式 label（`label:has-text("...") >> input`）属于稳定的 DOM 父子关系，confidence 为 `high`；显式/相邻 label 在 P3 未命中后使用 `:has-text()` 匹配公共祖先（`div:has-text("...") >> input`），其稳定性取决于祖先标签稳定且文本在该祖先范围内唯一，实际 confidence 应为 `medium`。实现时应在 JS 内部根据实际采用的子路径动态设定 confidence，规范层面保留 P6 整体为 `high` 的默认映射，但需在展示或记录时体现该差异。| P7 可见文本 | medium | 文本可能因产品需求 / 国际化频繁调整 |
| P8 唯一类组合 | medium | 类名重构频率高于 ID 和属性 |
| P9 相对 XPath | low | 依赖局部 DOM 结构 |
| P10 绝对 XPath | low | 最脆弱，页面任何结构调整都可能破坏 |

### 6.3 strategy key 标准化

为便于前后端对接，策略使用统一的英文标识符：

| 策略 | strategy key |
|------|-------------|
| P1 测试属性 | `test-attribute` |
| P2 静态 ID | `static-id` |
| P3 父级 ID 锚定 | `parent-id-anchor` |
| P4 ElementUI 文本 | `elementui-text` |
| P5 语义属性 | `semantic-attr` |
| P6 Label 关联 | `label-association` |
| P7 可见文本 | `visible-text` |
| P8 唯一类组合 | `unique-class` |
| P9 相对 XPath | `relative-xpath` |
| P10 绝对 XPath | `absolute-xpath` |

### 6.4 兼容迁移方案

当前调用链为纯字符串传递：

```
JS getSmartSelector() → string
  → window.elementClicked(selector)
    → Python _on_picker_click(selector: str)
      → pick_debug_element() → string
        → server.py /api/pick_selector → {status, selector: string}
          → frontend: data.selector 直接当字符串用
```

为避免一次性破坏整条链，迁移分阶段进行：

**Phase 1：内部结构化**
- JS `getSmartSelector()` 返回对象 `{selector, strategy, confidence, warnings}`。
- Python `_on_picker_click` 接收对象，但只把 `selector` 字符串放入队列。
- 代码改动示例：
  ```python
  def _on_picker_click(self, source, selector):
      # Phase 1: 同时兼容字符串（旧）和对象（新）
      if isinstance(selector, dict):
          selector = selector.get("selector", "")
      self.last_picked_selector = selector
  ```
- API 返回保持 `{status, selector: string}`。

**Phase 2：API 扩展字段**
- `/api/pick_selector` 返回新增字段：
  ```json
  {
    "status": "success",
    "selector": "...",
    "strategy": "parent-id-anchor",
    "confidence": "high",
    "warnings": []
  }
  ```
- `selector` 字段**始终为字符串**，前端现有逻辑继续可用。

**Phase 3：前端消费元数据**
- 前端在属性面板显示 `strategy` / `confidence` / `warnings`。
- 对 `confidence: low` 的选择器给出视觉提示。

**向后兼容保证**：
- 已保存流程中的选择器继续以字符串存储，不受影响。
- 新增字段为可选，前端未消费时不会报错。

## 7. 配置项建议（可选扩展）

在拾取器或全局配置中，可增加：

- `preferredTestAttributes`: 自定义测试属性列表，如 `["data-testid", "data-qa"]`
- `enableFrameworkDetection`: 是否启用 ElementUI 等框架专用策略
- `maxTextLength`: 文本选择器的最大文本长度限制
- `strictVisibility`: 是否强制要求元素可见

## 8. 实施步骤

1. 修改 `core/engine.py` 中 `_internal_pick()` 注入的 JS：
   - 按本规范重新组织策略顺序。
   - 新增 P1 测试属性检测、P3 父级 ID 锚定、P5 语义属性检测、P6 Label 关联检测、P9 相对 XPath 检测。
   - 修正 P8 唯一类组合：尝试多个类的组合，而非仅取单个类。
   - 修正类名过滤列表，补全 `is-active`、`hover`、`focus`、`selected`。
   - 修正父级查找逻辑：向上遍历到 `document.body`，而非仅直接父级。
   - **注意 P6 选择器语义**：显式 label / 相邻 label 不能直接用 `text="..." >> input`，必须借助公共父级 ID 或 `:has-text()` 祖先定位。
2. 调整 `_on_picker_click` 与 `pick_debug_element()` 支持对象传递（Phase 1）。
3. 更新 `server.py /api/pick_selector` 返回新增字段（Phase 2）。
4. 前端属性面板展示 strategy / confidence / warnings（Phase 3）。
5. 对绝对 XPath 等低 confidence 选择器在前端给出风险提示。

**实施前建议**：根据附录 B 的差异对照表，将以上步骤拆分为具体的代码改动任务清单，每项对应一个策略或一个修复点。

## 9. 向后兼容

- `resolve_selector()` 对现有字符串选择器的处理逻辑保持不变。
- 已保存流程中的选择器继续使用，不受影响。
- 新增策略仅影响新拾取操作生成的选择器。

---

## 附录 A：审查意见处理记录（v1.0 → v1.1）

| 编号 | 意见 | 状态 | 处理方式 |
|------|------|------|---------|
| A.1 | 父级 ID 权重不足，Label 关联策略缺失 | 已采纳 | 新增 P3 父级 ID 锚定、P6 Label 关联定位 |
| A.2 | P4 标签白名单排除 INPUT/SELECT | 已采纳 | 白名单保留 INPUT/SELECT，明确其文本来自 Label 关联策略 |
| A.3 | P5 语义属性优先级偏低 | 已采纳 | 语义属性（P5）前移至可见文本（P7）之前 |
| A.4 | 输出格式变更需兼容方案 | 已采纳 | 第 6 节补充 Phase 1/2/3 渐进迁移方案 |
| A.5 | 类过滤列表差异 | 已采纳 | 第 5.4 节统一为完整过滤列表 |
| A.6 | 规范与实现差异汇总 | 已记录 | 见附录 B |
| A.7 | 做得好的方面 | 保留 | 动态 ID 过滤、ElementUI 容器、兜底机制等继续沿用 |
| A.8 | 建议修订优先级总览 | 已纳入 | 按优先级更新主规范 |

---

## 附录 B：当前实现差异对照表

| 规范要求 | 当前实现状态（`core/engine.py` `_internal_pick`） | 后续行动 |
|----------|----------------------------------------------|---------|
| P1 测试属性 | 未实现 | 需新增 |
| P2 稳定静态 ID + `CSS.escape` | 已实现 | 规范已补录 `CSS.escape` 说明 |
| P3 父级 ID 锚定 | 未实现 | 需新增 |
| P4 ElementUI 框架文本 | 已实现 | 继续沿用 |
| P5 语义属性 | 未实现 | 需新增 |
| P6 Label 关联定位 | 未实现 | 需新增 |
| P7 可见文本 + 限定 | 部分实现（表单控件已移出 P7 范围，父级查找仅限直接 parent） | 需完善：父级改为向上遍历到 body |
| P8 唯一类组合 | 部分实现（只用单个类，未做组合） | 需完善 |
| P9 相对 XPath | 未实现 | 需新增 |
| P10 绝对 XPath | 已实现 | 继续沿用 |
| 类过滤列表 | 缺少 `is-active`、`hover`、`focus`、`selected` | 需补齐 |
| 父级查找范围 | 仅直接父级 | 需改为向上遍历到 body |

---

## 附录 C：v1.1 补充审查意见

*审查日期：2025-07-02，基于 v1.1 初稿。*

### C.1 P5 语义属性缺少歧义消解递进流程

P7（可见文本）有完整的 4 级递进消解流程，但 P5 只写了：

> 同一属性值在页面内唯一或可通过标签限定变得唯一。

"标签限定"之后怎么办？如果 `name="email"` 在注册 + 登录两个 form 里各出现一次，应通过父级 ID 锚定消歧。

### C.2 P6 Label 关联：非唯一文本的歧义处理缺失

同一页面有两个"姓名"输入框（收货人姓名 + 开票人姓名），label 文本相同。规范没有说明是降级到 P7 还是尝试父级锚定。

### C.3 P6 显式 label + 动态 ID 的边界情况

控件上的 `id` 可能是动态 ID（如 `el-input-2938`），P2 已过滤。此时仍可通过 `label[for="<动态id>"]` 查找到 label 并提取文本，但实施时容易误把动态 `for` 值写入选择器。

### C.4 缺少 confidence 等级定义

Section 6 使用了 `"high"` / `"low"`，但未定义各策略对应哪个等级，也未明确是否只有两档。

### C.5 策略标识符未标准化

示例中 strategy 值混用中文策略名和英文 key，前后端对接会混乱。

### C.6 P3 与 P9 边界模糊

P3 说"通过相邻 label 文本或 nth-of-type 限定"，实际上越界到了 P9 领域。

### C.7 Phase 1 迁移缺少代码层面改动说明

当前 `_on_picker_click` 直接接收字符串，如果传入对象会破坏下游。

---

## 附录 D：审查意见处理记录（v1.1 → v1.2）

| 编号 | 意见 | 状态 | 处理方式 |
|------|------|------|---------|
| C.1 | P5 语义属性缺少歧义消解递进流程 | 已采纳 | 第 4.5 节补充 4 级递进消歧流程 |
| C.2 | P6 Label 关联非唯一文本消歧缺失 | 已采纳 | 第 4.6 节补充 3 级递进消歧流程 |
| C.3 | P6 显式 label + 动态 ID 边界情况 | 已采纳 | 第 4.6 节追加动态 ID 边界警告 |
| C.4 | 缺少 confidence 等级定义 | 已采纳 | 第 6.2 节新增 confidence 映射表 |
| C.5 | 策略标识符未标准化 | 已采纳 | 第 6.3 节新增 strategy key 标准化映射表 |
| C.6 | P3 与 P9 边界模糊 | 已采纳 | 第 4.3 节新增 P3/P9 边界说明 |
| C.7 | Phase 1 缺少代码改动示例 | 已采纳 | 第 6.4 节 Phase 1 补充 `_on_picker_click` 代码示例 |

---

## 附录 E：v1.2 审查意见

*审查日期：2025-07-02，基于 v1.2。*

### E.1 P6 选择器链语义错误：`>>` 要求父子关系，但显式/相邻 label 是兄弟节点

Playwright 的 `>>` 链是后代选择器。`text="邮箱" >> input` 只在 input 是 label 后代时成立；显式 label 和相邻 label/span 与 input 是兄弟，原示例不会命中目标。

### E.2 P5/P6 降级到 P9 但 P9 可能无可用锚点

P5/P6 消歧最后一步降级到 P9，但 P9 需要锚点。若 P5/P6 已说明父级 ID/唯一类都不可用，P9 大概率也失败。

### E.3 P7 标签白名单中的 INPUT/SELECT 定位不清晰

P6 已专门处理表单控件，P7 再列入 INPUT/SELECT 会造成逻辑重叠。建议明确 P6 失败后由 P9/P10 兜底，P7 移除 INPUT/SELECT。

### E.4 P7 全页唯一文本与 P6 全页唯一 label 文本可能冲突

极端情况下 label 的 `for` 指向隐藏 input，P6 会指向隐藏元素，而 P7 的 `text="邮箱"` 指向可见 label。当前优先级排序可接受，仅作记录。

### E.5 Section 8 实施步骤可操作性

实施步骤较概括，建议实施前根据附录 B 拆分为具体任务清单。

---

## 附录 F：审查意见处理记录（v1.2 → v1.3）

| 编号 | 意见 | 状态 | 处理方式 |
|------|------|------|---------|
| E.1 | P6 选择器链语义错误 | 已采纳 | 第 4.6 节重写，区分隐式/显式/相邻 label 的生成方式；显式/相邻 label 改用公共父级 ID 或 `:has-text()` 祖先定位；补充 Playwright `>>` 后代语义说明 |
| E.2 | P5/P6 降级到 P9 但 P9 可能无锚点 | 已采纳 | 第 4.5、4.6、4.9、5.3 节补充：P9 无锚点时跳过 P9 直接使用 P10 |
| E.3 | P7 白名单 INPUT/SELECT 定位不清晰 | 已采纳 | 第 4.7 节明确表单控件由 P6 覆盖，从 P7 白名单中移除 INPUT/SELECT |
| E.4 | P6 与 P7 全页唯一文本可能冲突 | 已记录 | 附录 E 保留说明，当前优先级排序可接受 |
| E.5 | 实施步骤可操作性 | 已采纳 | 第 8 节末尾补充实施前拆分为具体任务清单的建议 |

---

## 附录 H：审查意见处理记录（v1.3 → v1.4）

| 编号 | 意见 | 状态 | 处理方式 |
|------|------|------|---------|
| G.1 | P6「交给 P3」措辞可能暗示循环依赖 | 已采纳 | 第 4.6 节重写：显式/相邻 label 场景改为说明 P3 已处理单控件简单情况，P6 处理 P3 未命中（多控件）场景，避免暗示反向调用 P3 |
| G.3 | P3 判定条件中 `nth-of-type` 与 P3/P9 边界说明冲突 | 已采纳 | 第 4.3 节判定条件移除 `nth-of-type`，明确 `nth-of-type` 等结构索引属于 P9 相对 XPath 范畴 |
| G.4 | P6 `:has-text()` 子路径 confidence 偏高 | 已采纳 | 第 6.2 节追加 P6 内部路径说明，显式/相邻 label 使用 `:has-text()` 时实际 confidence 为 `medium`，实现时应动态判定 |

**版本**: 1.4  
**状态**: 待实现

---

## 附录 G：v1.3 审查意见

*审查日期：2025-07-02，基于 v1.3。*

### G.1 🟡 P6 显式 label「交给 P3」措辞可能造成循环依赖的误解

P6 显式 label 关联模式写道：

> 若 label 和 input 处于有稳定 ID 的公共父容器内，**交给 P3 父级 ID 锚定**：`#form-section >> input`

实际上 P3 在策略链中先于 P6 运行。当执行流到达 P6 时，P3 已经尝试过了。两种实际情况：
- **P3 已命中**：公共父级有 ID 且该 ID 下只有一个 input → P3 返回 `#parent-id >> input`，不会走到 P6。
- **P3 未命中**：公共父级有 ID 但该 ID 下有多个同类控件 → P3 无法唯一确定，流程继续走到 P6。

P6 的 `#form-section >> input` 在第二种情况下同样无法唯一确定（仍然多个 input），所以这里的真正有效路径是 `div:has-text("邮箱") >> input`。

**建议**：修正措辞，避免暗示 P6 "反向调用"已执行的 P3：

> 若 label 和 input 处于有稳定 ID 的公共父容器内，且该容器下仅有此一个同类控件，则 P3 已生成 `#parent-id >> input`，P6 无需处理此情况。P6 处理的是 P3 未命中（同类控件多个）的场景：利用 `:has-text()` 进一步限定到包含特定 label 文本的祖先容器。

---

### G.2 🟡 附录 B P7 行信息过时

v1.3 已将 INPUT/SELECT/TEXTAREA 从 P7 标签白名单中移除，但附录 B 的 P7 行仍为：

> 部分实现（缺少 INPUT/SELECT、父级仅查直接 parent）

缺少 INPUT/SELECT 现在是**预期行为**而非待修复项。应更新为：

> 部分实现（父级查找仅限直接 parent，需改为向上遍历到 body）

---

### G.3 🟢 P3 判定条件中 `nth-of-type` 与 P3/P9 边界说明不一致

P3 判定条件：

> 若锚点下同类元素有多个，可进一步通过相邻 label 文本或 `nth-of-type` 限定。

但同节的「与 P9 的边界」又明确：

> P3 只负责「锚点下标签名即唯一」的简单情况。若同类元素 ≥ 2 个，先尝试 label 文本限定；若仍无法唯一，降级到 P9。

`nth-of-type` 本质上就是相对 XPath，应归入 P9 领域。P3 判定条件中应去掉 `nth-of-type`，或改为"尝试 label 文本限定；若仍多个，降级到 P9"。

---

### G.4 🟢 P6 `:has-text()` 路径的 confidence 应区分场景

P6 整体 confidence 为 `high`。但 P6 内部有两条质量不同的路径：

| P6 子路径 | 实际稳定性 | 当前 confidence |
|----------|-----------|----------------|
| P3 锚点 + 单控件（已被 P3 覆盖） | high | high ✅ |
| 隐式 label：`label:has-text("...") >> input` | high（label 包裹是稳定的 DOM 关系） | high ✅ |
| 显式/相邻 label：`div:has-text("...") >> input` | medium（依赖文本在祖先容器中唯一、祖先标签稳定） | high → 应为 medium |

实施时建议：JS 内部根据实际采用的子路径动态设定 confidence，而非对整个 P6 策略用固定值。规范层面可在 confidence 表中加一个脚注说明。当前不影响实施，仅作记录。

---

### G.5 v1.3 审查总结

| 编号 | 事项 | 严重度 | 建议 |
|------|------|--------|------|
| G.1 | P6「交给 P3」措辞可能暗示循环依赖 | 🟡 | 改为说明 P3 已处理简单情况，P6 处理 P3 未命中的复杂场景 |
| G.2 | 附录 B P7 行信息过时 | 🟡 | 移除"缺少 INPUT/SELECT"，更新为仅剩父级遍历问题 |
| G.3 | P3 `nth-of-type` 与边界说明冲突 | 🟢 | 从 P3 判定条件中移除 `nth-of-type` |
| G.4 | P6 `:has-text()` 子路径 confidence 偏高 | 🟢 | 记录为实施细节，JS 实现时动态判定 |
| G.5 | 整体评价 | — | v1.3 已达到可实施状态，规范层面无结构性问题 |

### G.6 三轮审查趋势

经过 v1.0 → v1.1 → v1.2 → v1.3 四版迭代：

- **🔴 级别问题**：从 2 个（父级 ID 缺失 + Label 策略缺失）→ 1 个（选择器链语义错误）→ **0 个**
- **🟡 级别问题**：从 4 个 → 5 个 → 3 个 → **2 个**（措辞精化 + 附录过时）
- **🟢 级别问题**：从 2 个 → 2 个 → 2 个 → **2 个**（均为实施细节）

规范已收敛到可放心进入实施阶段。
