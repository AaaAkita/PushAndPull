import { state } from './state.js';
import { getTitleByType, getStepSummary, escapeAttribute } from './utils.js';

// DOM Elements
const canvasContainer = document.getElementById('canvas-container');
const propertiesContent = document.getElementById('properties-content');

export function renderCanvas() {
    // Clear current content (except empty state which we toggle)
    canvasContainer.innerHTML = '';

    if (state.steps.length === 0) {
        canvasContainer.innerHTML = `
            <div id="empty-state" class="empty-z select-none fade-in">
                <div class="empty-z-brand">
                    <i class="fa-solid fa-layer-group text-brand"></i>
                    <span>Visual Playwright</span>
                </div>
                <div class="empty-z-help">
                    <a href="https://github.com/AnxForever/stylekit" target="_blank" class="text-sm text-tertiary hover:text-primary">
                        <i class="fa-solid fa-circle-question"></i> 使用帮助
                    </a>
                </div>
                <div class="empty-z-center">
                    <h1>开始搭建你的自动化流程</h1>
                    <p>从左侧组件库选择步骤，拖拽排序，右侧配置属性</p>
                    <button class="btn-apple" onclick="addStep('open_url')">
                        <i class="fa-solid fa-plus"></i> 添加第一个步骤
                    </button>
                </div>
                <div class="empty-z-trust">
                    <i class="fa-solid fa-shield-halved text-success"></i> 本地执行，数据安全
                </div>
                <div class="empty-z-secondary">
                    <button class="btn btn-ghost btn-sm" onclick="handleSchemeNav()">
                        <i class="fa-solid fa-folder-open"></i> 打开已有方案
                    </button>
                </div>
            </div>`;
        return;
    }


    // Module level variable to track dragging item
    let draggingIndex = null;

    state.steps.forEach((step, index) => {
        const isActive = index === state.activeStepIndex;
        const card = document.createElement('div');
        card.className = `step-card-v2 ${isActive ? 'active' : ''}`;
        card.draggable = true;

        // Selection
        card.onclick = () => window.selectStep(index);

        // Drag & Drop Handlers
        card.ondragstart = (e) => {
            draggingIndex = index;
            e.dataTransfer.setData('text/plain', index);
            e.dataTransfer.effectAllowed = 'move';
            card.style.opacity = '0.5';
            card.style.transform = 'scale(0.98)';
            card.style.transition = 'all 0.15s';
        };

        card.ondragend = () => {
            draggingIndex = null;
            card.style.opacity = '1';
            card.style.transform = 'scale(1)';
        };

        card.ondragover = (e) => {
            e.preventDefault();
            if (draggingIndex === index) return; // Ignore self
            e.dataTransfer.dropEffect = 'move';
            card.classList.add('drag-target-active');
        };

        card.ondragleave = (e) => {
            if (!card.contains(e.relatedTarget)) {
                card.classList.remove('drag-target-active');
            }
        };

        card.ondrop = (e) => {
            e.preventDefault();
            card.classList.remove('drag-target-active');
            const fromIndex = parseInt(e.dataTransfer.getData('text/plain'), 10);
            const toIndex = index;
            if (fromIndex !== toIndex) {
                window.moveStep(fromIndex, toIndex);
            }
        };

        // Header
        const header = document.createElement('div');
        header.className = 'flex justify-between items-center mb-2';

        // Action Toolbar
        const actions = `
            <div class="step-actions flex items-center gap-2 opacity-70 hover:opacity-100 transition-opacity">
                 <button class="btn-icon-action run" onclick="testStep(event, ${index})" title="测试运行">
                    <i class="fa-solid fa-play"></i>
                </button>
                <button class="btn-icon-action duplicate" onclick="duplicateStep(event, ${index})" title="复制步骤">
                    <i class="fa-solid fa-copy"></i>
                </button>
                <button class="btn-icon-action delete" onclick="removeStep(event, ${index})" title="删除步骤">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </div>
        `;

        header.innerHTML = `
            <span class="step-title flex items-center gap-2">
                <span class="step-index">${index + 1}</span>
                ${step.title || getTitleByType(step.type)}
            </span>
            ${actions}
        `;

        // Summary Line
        const summary = document.createElement('div');
        summary.className = 'step-summary';
        summary.innerHTML = getStepSummary(step);

        card.appendChild(header);
        card.appendChild(summary);
        canvasContainer.appendChild(card);
    });
}

function createInput(label, keyPath, value, type = 'text') {
    const isConfig = keyPath.startsWith('config.');
    const key = isConfig ? keyPath.split('.')[1] : keyPath;
    const changeFn = isConfig ? `updateConfig('${key}', this.value, '${type}')` : `updateRoot('${key}', this.value)`;

    return `
        <div class="form-group mb-3">
            <label class="input-label">${label}</label>
            <input type="${type}"
                   value="${escapeAttribute(value)}"
                   oninput="${changeFn}"
                   class="input-v2 w-full">
        </div>
    `;
}

function createSelectorInput(label, configKey, value, step=null) {
    const pureKey = configKey.startsWith('config.') ? configKey.split('.')[1] : configKey;

    let metaHtml = '';
    if (step && pureKey === 'selector' && step.config._pickerMeta) {
        const meta = step.config._pickerMeta;
        const strategyLabels = {
            'test-attribute': '测试属性',
            'static-id': '静态 ID',
            'parent-id-anchor': '父级 ID 锚定',
            'elementui-text': 'ElementUI 文本',
            'semantic-attr': '语义属性',
            'label-association': 'Label 关联',
            'visible-text': '可见文本',
            'unique-class': '唯一类组合',
            'relative-xpath': '相对 XPath',
            'absolute-xpath': '绝对 XPath',
            'unknown': '未知策略'
        };
        const confidenceColors = {
            'high': 'text-success',
            'medium': 'text-warning',
            'low': 'text-danger'
        };
        const confidenceLabels = {
            'high': '高',
            'medium': '中',
            'low': '低'
        };
        const strategyName = strategyLabels[meta.strategy] || meta.strategy;
        const confClass = confidenceColors[meta.confidence] || 'text-tertiary';
        const confName = confidenceLabels[meta.confidence] || meta.confidence;
        const warnings = (meta.warnings || []).map(w => `<li class="text-danger">⚠️ ${w}</li>`).join('');
        metaHtml = `
            <div class="mt-1 text-xs space-y-1">
                <div class="flex gap-2">
                    <span class="text-tertiary">策略: <span class="text-info">${strategyName}</span></span>
                    <span class="text-tertiary">置信度: <span class="${confClass}">${confName}</span></span>
                </div>
                ${warnings ? `<ul class="list-disc pl-4">${warnings}</ul>` : ''}
            </div>
        `;
    }

    return `
        <div class="form-group mb-3">
            <label class="input-label">${label}</label>
            <div class="flex gap-2 items-start">
                <textarea
                       oninput="updateConfig('${pureKey}', this.value)"
                       class="input-v2 flex-1 font-mono text-xs"
                       rows="3"
                       placeholder="#id or //xpath"
                       id="input-${pureKey}">${value || ''}</textarea>
                <button class="btn-icon h-8" onclick="pickSelector('${pureKey}')" title="Pick from Browser">🎯</button>
            </div>
            ${metaHtml}
        </div>
    `;
}

function createValidationBlock(step) {
    return `
        <div class="prop-section">
            <div class="prop-section-title">执行后验证</div>

            ${createInput('超时时间 / 等待时间 (ms)', 'config.waitAfter', step.config.waitAfter || '0', 'number')}

            <div class="prop-hint mb-3">
                若设置了“验证元素”，此时间为<b>最长等待时间（超时判定）</b>；<br>
                若未设置，则为<b>固定等待时间</b>。
            </div>

            ${createSelectorInput('验证元素出现', 'config.validateSelector', step.config.validateSelector, step)}
            <div class="prop-hint">
                <i class="fa-solid fa-triangle-exclamation"></i>
                如果不为空，将在操作后持续检测该元素。<br>
                若在超时时间内<b>出现</b>，则验证通过并立即执行下一步（不会死等）；<br>
                若<b>超时未出现</b>，则判定<b>任务失败</b>并记录，跳过后续步骤。
            </div>
        </div>
    `;
}

/**
 * 渲染"选择 Excel 列"下拉框。
 *
 * 关键修复：当 step.config[valueKey] 不在当前 columns 中时（典型场景：从另一份
 * flow 复制本步骤，旧列名残留，或换了 Excel 文件后表头变了），浏览器对 <select>
 * 会默认显示第一个非 disabled 的 option 但【不触发 change 事件】，导致
 * "UI 显示 resource_id、内存仍是 旧列名" 的脱节，测试时发出旧值。
 *
 * 这里在渲染时主动把内存值同步为 select 的实际首选项，保证所见即所发。
 * 直接写 state.steps 并标记 dirty，不走 updateConfig（避免触发 renderProperties 递归）。
 *
 * @param {object} step          当前步骤对象（引用，会被原地修正）
 * @param {string} valueKey      存列名的 config 字段名（'value' 或 'filePath'）
 * @param {string} label          下拉框 label 文案
 * @param {string} placeholder   无列可选时的占位文案
 */
function renderExcelColumnSelect(step, valueKey, label, placeholder = '-- 请选择列名 --') {
    const excelStep = state.steps.find(s => s.type === 'excel_read');
    const columns = (excelStep && excelStep.config.columns) ? excelStep.config.columns : [];

    if (columns.length === 0) {
        const warning = !excelStep
            ? '未找到 Excel 读取步骤'
            : 'Excel 文件未读取到表头';
        return createInput('Excel 列名 (手动输入)', `config.${valueKey}`, step.config[valueKey]) +
            `<p class="prop-hint"><i class="fa-solid fa-triangle-exclamation text-warning"></i> ${warning}</p>`;
    }

    // 同步修正：当前值无效时，回退为第一列，保证 UI 与内存一致。
    const current = step.config[valueKey];
    const synced = columns.includes(current) ? current : columns[0];
    if (synced !== current) {
        step.config[valueKey] = synced;
        state.isDirty = true; // step 是 state.steps 内的同一引用，已原地改值；只标记未保存。
    }

    return `
        <div class="form-group mb-4">
            <label class="input-label">${label}</label>
            <select onchange="updateConfig('${valueKey}', this.value)" class="input-v2">
                <option value="" disabled ${!synced ? 'selected' : ''}>${placeholder}</option>
                ${columns.map(col => `<option value="${col}" ${synced === col ? 'selected' : ''}>${col}</option>`).join('')}
            </select>
        </div>
    `;
}

export function renderProperties() {
    if (state.activeStepIndex === null || !state.steps[state.activeStepIndex]) {
        propertiesContent.innerHTML = '<p class="text-tertiary text-center mt-10">请选择一个步骤以设置属性</p>';
        return;
    }

    const step = state.steps[state.activeStepIndex];
    let html = '';

    // Base settings
    html += `
        <div class="prop-section">
            <div class="prop-section-title">基础设置</div>
            ${createInput('步骤名称', 'title', step.title)}
            ${createInput('执行前等待 (ms)', 'config.waitBefore', step.config.waitBefore, 'number')}
        </div>
    `;

    if (['click', 'input_text', 'upload_file', 'keyboard_map'].includes(step.type)) {
        html += `
            <div class="prop-section">
                <div class="prop-section-title">前置等待</div>
                ${createSelectorInput('等待元素出现', 'waitForSelector', step.config.waitForSelector, step)}
            </div>
        `;
    }

    if (step.type === 'open_url') {
        html += `
            <div class="prop-section">
                <div class="prop-section-title">目标地址</div>
                ${createInput('URL 地址', 'config.url', step.config.url)}
                <button class="btn-apple w-full mt-2" onclick="testOpenUrl()">
                    <i class="fa-solid fa-globe"></i> 测试打开 (Launch)
                </button>
            </div>
        `;

        html += `
            <div class="prop-section">
                <div class="prop-section-title">自动登录回退</div>
                <p class="prop-hint mb-3">如果跳转到登录页，尝试自动登录。</p>
                <div id="login-fallback-${state.activeStepIndex}" class="space-y-2">
                    ${createSelectorInput('账号输入框', 'config.loginUserSelector', step.config.loginUserSelector, step)}
                    ${createInput('账号', 'config.loginUser', step.config.loginUser)}
                    ${createSelectorInput('密码输入框', 'config.loginPassSelector', step.config.loginPassSelector, step)}
                    ${createInput('密码 - 明文存储', 'config.loginPass', step.config.loginPass)}
                    ${createSelectorInput('登录按钮', 'config.loginBtnSelector', step.config.loginBtnSelector, step)}
                </div>
            </div>
        `;
        html += createValidationBlock(step);
    }
    else if (step.type === 'input_text' || step.type === 'label_input') {
        html += `
            <div class="prop-section">
                <div class="prop-section-title">元素定位</div>
                ${createSelectorInput('目标元素定位', 'config.selector', step.config.selector, step)}
            </div>
        `;

        html += `
            <div class="prop-section">
                <div class="prop-section-title">输入内容</div>
                <div class="form-group mb-4">
                    <label class="input-label">输入内容来源</label>
                    <select onchange="updateConfig('inputType', this.value)" class="input-v2">
                        <option value="fixed" ${step.config.inputType === 'fixed' ? 'selected' : ''}>固定文本</option>
                        <option value="excel" ${step.config.inputType === 'excel' ? 'selected' : ''}>Excel 列数据</option>
                    </select>
                </div>

                ${step.config.inputType === 'fixed'
                    ? createInput('输入内容', 'config.value', step.config.value)
                    : renderExcelColumnSelect(step, 'value', '选择 Excel 列')
                }

                ${step.type === 'label_input'
                    ? `<div class="prop-hint">
                        <i class="fa-solid fa-info-circle text-info"></i> 标签输入逻辑：先输入文本，再按 Enter 保存，最后清空输入框。
                       </div>`
                    : ''}
            </div>
        `;

        if (step.type === 'input_text') {
            html += createValidationBlock(step);
        }
    }
    else if (step.type === 'click') {
        html += `
            <div class="prop-section">
                <div class="prop-section-title">元素定位</div>
                ${createSelectorInput('元素定位', 'config.selector', step.config.selector, step)}
            </div>
        `;
        html += createValidationBlock(step);
    }
    else if (step.type === 'wait') {
        html += `
            <div class="prop-section">
                <div class="prop-section-title">等待时长</div>
                ${createInput('等待时间 (ms)', 'config.time', step.config.time, 'number')}
            </div>
        `;
    }
    else if (step.type === 'keyboard') {
        html += `
            <div class="prop-section">
                <div class="prop-section-title">元素聚焦</div>
                ${createSelectorInput('先点击/聚焦元素', 'config.selector', step.config.selector, step)}
                <p class="prop-hint">若指定，会先点击该元素获取焦点，再发送按键。</p>
            </div>
        `;

        html += `
            <div class="prop-section">
                <div class="prop-section-title">按键内容</div>
                ${createInput('按键内容', 'config.key', step.config.key)}
                <p class="prop-hint">
                    支持单键 (Enter, Tab, Escape, A) 或组合键 (Control+C, Shift+Tab)。
                    <a href="https://playwright.dev/python/docs/api/class-keyboard" target="_blank" class="text-link hover:underline">查看文档</a>
                </p>
                ${createInput('重复次数', 'config.count', step.config.count || '1', 'number')}
            </div>
        `;
        html += createValidationBlock(step);
    }
    else if (step.type === 'excel_read') {
        html += `
            <div class="prop-section">
                <div class="prop-section-title">Excel 文件</div>
                <div class="form-group mb-4">
                    <label class="input-label">Excel 文件路径 (绝对路径)</label>
                    <div class="flex gap-2">
                        <input type="text" value="${step.config.filePath || ''}"
                               onchange="updateConfig('filePath', this.value); reloadExcelColumns(this.value)"
                               class="input-v2 flex-1">
                        <button class="btn-icon" onclick="browseExcel()">📂</button>
                    </div>
                </div>

                <div class="form-group mb-4">
                    <label class="input-label">结果记录列名</label>
                    <input type="text" value="${step.config.statusColumn || '执行结果'}"
                           oninput="updateConfig('statusColumn', this.value)"
                           class="input-v2" placeholder="例如: 执行结果">
                    <p class="prop-hint">系统将自动在此列记录 Success 或 Failed。</p>
                </div>

                ${step.config.columns && step.config.columns.length > 0
                    ? `
                        <div class="form-group mb-4">
                            <label class="input-label">读取到的表头</label>
                            <div class="flex flex-wrap gap-2">
                                ${step.config.columns.map(col => `<span class="bg-brand-light text-brand px-2 py-1 rounded text-xs border border-brand-light">${col}</span>`).join('')}
                            </div>
                        </div>
                    `
                    : ''
                }
            </div>
        `;
    }
    else if (step.type === 'upload_file') {
        html += `
            <div class="prop-section">
                <div class="prop-section-title">元素定位</div>
                ${createSelectorInput('上传按钮/输入框', 'config.selector', step.config.selector, step)}
            </div>
        `;

        html += `
            <div class="prop-section">
                <div class="prop-section-title">文件来源</div>
                <div class="form-group mb-4">
                    <label class="input-label">文件路径来源</label>
                    <select onchange="updateConfig('inputType', this.value)" class="input-v2">
                        <option value="fixed" ${(!step.config.inputType || step.config.inputType === 'fixed') ? 'selected' : ''}>固定路径</option>
                        <option value="excel" ${step.config.inputType === 'excel' ? 'selected' : ''}>Excel 列数据</option>
                    </select>
                </div>

                ${step.config.inputType === 'excel'
                    ? renderExcelColumnSelect(step, 'filePath', '选择包含文件路径的列')
                    : `
                        <div class="form-group mb-4">
                            <label class="input-label">本地文件路径</label>
                            <div class="flex gap-2">
                                 <input type="text" value="${step.config.filePath || ''}"
                                        onchange="updateConfig('filePath', this.value)"
                                        class="input-v2 flex-1">
                                 <button class="btn-icon" onclick="alert('TODO: Browse local file for upload (use path manually for now)')">📂</button>
                            </div>
                        </div>
                    `
                }
            </div>
        `;

        html += createValidationBlock(step);
    }
    else if (step.type === 'dropdown_select') {
        html += `
            <div class="prop-section">
                <div class="prop-section-title">下拉元素</div>
                ${createSelectorInput('触发下拉框', 'config.selector', step.config.selector, step)}
                ${createSelectorInput('选项元素', 'config.optionSelector', step.config.optionSelector || 'li', step)}
                <p class="prop-hint">
                    <i class="fa-solid fa-lightbulb text-warning"></i>
                    请手动展开下拉框后拾取任意一个选项。确保选择器通用（如 "li" 或 ".el-select-dropdown__item"），不要使用特定 ID。
                </p>

                <div class="form-group mb-4">
                    <label class="input-label">展开方式</label>
                    <select onchange="updateConfig('expandMethod', this.value)" class="input-v2">
                        <option value="hover" ${(!step.config.expandMethod || step.config.expandMethod === 'hover') ? 'selected' : ''}>悬停展开 - 默认</option>
                        <option value="click" ${step.config.expandMethod === 'click' ? 'selected' : ''}>点击展开</option>
                    </select>
                    <p class="prop-hint">若悬停无法展开子菜单，请尝试改为点击。</p>
                </div>
            </div>
        `;

        html += `
            <div class="prop-section">
                <div class="prop-section-title">目标文本</div>
                <div class="form-group mb-4">
                    <label class="input-label">目标文本来源</label>
                    <select onchange="updateConfig('inputType', this.value)" class="input-v2">
                        <option value="fixed" ${(!step.config.inputType || step.config.inputType === 'fixed') ? 'selected' : ''}>固定文本</option>
                        <option value="excel" ${step.config.inputType === 'excel' ? 'selected' : ''}>Excel 列数据</option>
                    </select>
                </div>

                ${step.config.inputType === 'excel'
                    ? renderExcelColumnSelect(step, 'value', '选择 Excel 列')
                    : createInput('目标文本', 'config.value', step.config.value)
                }
            </div>
        `;

        html += `
            <div class="prop-section">
                <div class="prop-section-title">额外选项</div>
                <div class="form-group mb-4">
                    <label class="input-label flex items-center gap-2 cursor-pointer">
                        <input type="checkbox"
                               ${step.config.extraEnter ? 'checked' : ''}
                               onchange="updateConfig('extraEnter', this.checked)"
                               class="checkbox-dark">
                        是否执行额外回车？
                    </label>
                    <p class="prop-hint">勾选后，在选择完成后会额外执行一次回车键以确认选择。</p>
                </div>
            </div>
        `;

        html += createValidationBlock(step);
    }

    propertiesContent.innerHTML = html;
}
