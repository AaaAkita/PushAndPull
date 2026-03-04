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
            <div id="empty-state" class="text-center text-gray-500 mt-20 border-2 border-dashed border-gray-700 p-10 rounded-lg select-none">
                点击左侧组件开始搭建流程
            </div>`;
        return;
    }


    // Module level variable to track dragging item
    let draggingIndex = null;

    state.steps.forEach((step, index) => {
        const isActive = index === state.activeStepIndex;
        const card = document.createElement('div');
        card.className = `step-card ${isActive ? 'active' : ''}`;
        card.draggable = true;

        // Selection
        card.onclick = () => window.selectStep(index);

        // Drag & Drop Handlers
        card.ondragstart = (e) => {
            draggingIndex = index;
            e.dataTransfer.setData('text/plain', index);
            e.dataTransfer.effectAllowed = 'move';
            // card.style.opacity = '0.5'; 
        };

        card.ondragend = () => {
            draggingIndex = null;
            // card.style.opacity = '1';
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
                // ... existing logic
                window.moveStep(fromIndex, toIndex);
            }
        };

        // Header
        const header = document.createElement('div');
        header.className = 'flex justify-between items-center mb-2';

        // Action Toolbar
        const actions = `
            <div class="step-actions flex items-center gap-3 opacity-80 hover:opacity-100 transition-opacity">
                 <button class="btn-icon-action text-blue-400 hover:bg-blue-900/30 p-2" onclick="testStep(event, ${index})" title="测试运行">
                    <i class="fa-solid fa-play text-lg"></i>
                </button>
                <button class="btn-icon-action text-yellow-400 hover:bg-yellow-900/30 p-2" onclick="duplicateStep(event, ${index})" title="复制步骤">
                    <i class="fa-solid fa-copy text-lg"></i>
                </button>
                <button class="btn-icon-action text-red-400 hover:bg-red-900/30 p-2" onclick="removeStep(event, ${index})" title="删除步骤">
                    <i class="fa-solid fa-trash-can text-lg"></i>
                </button>
            </div>

        `;

        header.innerHTML = `
            <span class="font-bold text-sm text-purple-400 flex items-center gap-2">
                <span class="bg-gray-800 text-gray-500 text-xs px-1.5 py-0.5 rounded font-mono">${index + 1}</span>
                ${step.title || getTitleByType(step.type)}
            </span>
            ${actions}
        `;

        // Summary Line
        const summary = document.createElement('div');
        summary.className = 'text-xs text-gray-400 truncate';
        summary.innerHTML = getStepSummary(step);

        card.appendChild(header);
        card.appendChild(summary);
        canvasContainer.appendChild(card);
    });
}

function createInput(label, keyPath, value, type = 'text') {
    // keyPath support: 'title' or 'config.url'
    const isConfig = keyPath.startsWith('config.');
    const key = isConfig ? keyPath.split('.')[1] : keyPath;
    const changeFn = isConfig ? `updateConfig('${key}', this.value, '${type}')` : `updateRoot('${key}', this.value)`;

    return `
        <div class="form-group mb-4">
            <label class="label">${label}</label>
            <input type="${type}" 
                   value="${escapeAttribute(value)}" 
                   oninput="${changeFn}" 
                   class="input-dark w-full">
        </div>
    `;
}

function createSelectorInput(label, configKey, value) {
    // Strip 'config.' prefix if present for updateConfig
    const pureKey = configKey.startsWith('config.') ? configKey.split('.')[1] : configKey;

    return `
        <div class="form-group mb-4">
            <label class="label">${label}</label>
            <div class="flex gap-2 items-start">
                <textarea 
                       oninput="updateConfig('${pureKey}', this.value)" 
                       class="input-dark flex-1 font-mono text-xs" 
                       rows="3"
                       placeholder="#id or //xpath"
                       id="input-${pureKey}">${value || ''}</textarea>
                <button class="btn-icon h-8" onclick="pickSelector('${pureKey}')" title="Pick from Browser">🎯</button>
            </div>
        </div>
    `;
}

function createValidationBlock(step) {
    return `
        <div class="mt-4 border-t border-gray-700 pt-4">
            <label class="block text-gray-400 text-xs font-bold mb-2">执行后验证</label>
            
            ${createInput('超时时间 / 等待时间 (ms)', 'config.waitAfter', step.config.waitAfter || '0', 'number', '如: 5000')}
            
            <div class="mt-2 text-xs text-gray-500 mb-2">
                若设置了"验证元素"，此时间为<b>最长等待时间(超时判定)</b>；<br>
                若未设置，则为<b>固定等待时间</b>。
            </div>

            ${createSelectorInput('验证元素出现', 'config.validateSelector', step.config.validateSelector)}
            <div class="mt-2 text-xs text-gray-500">
                <i class="fa-solid fa-triangle-exclamation text-yellow-600"></i>
                如果不为空，将在操作后持续检测该元素。<br>
                若在超时时间内<b>出现</b>，则验证通过并立即执行下一步（不会死等）；<br>
                若<b>超时未出现</b>，则判定<b>任务失败</b>并记录，跳过后续步骤。
            </div>
        </div>
    `;
}

export function renderProperties() {
    if (state.activeStepIndex === null || !state.steps[state.activeStepIndex]) {
        propertiesContent.innerHTML = '<p class="text-gray-500 text-center mt-10">请选择一个步骤以设置属性</p>';
        return;
    }

    const step = state.steps[state.activeStepIndex];
    let html = '';

    // Common Fields
    // Use oninput for immediate title update in list
    html += createInput('步骤名称', 'title', step.title);
    html += createInput('执行前等待 (ms)', 'config.waitBefore', step.config.waitBefore, 'number');

    // Selector Wait (Common for interaction steps)
    if (['click', 'input_text', 'upload_file', 'keyboard_map'].includes(step.type)) {
        html += createSelectorInput('等待元素出现', 'waitForSelector', step.config.waitForSelector);
        html += '<hr class="border-gray-700 my-4">';
    }

    // Type Specific Fields
    if (step.type === 'open_url') {
        html += createInput('URL 地址', 'config.url', step.config.url);
        html += `<button class="btn w-full bg-gray-700 hover:bg-gray-600 text-white mt-2 mb-4" onclick="testOpenUrl()">
                    <i class="fa-solid fa-globe"></i> 测试打开 (Launch)
                 </button>`;

        html += `
            <div class="mt-4 pt-4 border-t border-gray-700">
                <div class="mb-2">
                    <label class="label text-purple-400">🛡️ 自动登录回退</label>
                </div>
                <div id="login-fallback-${state.activeStepIndex}" class="space-y-2">
                    <p class="text-xs text-gray-500 mb-2">如果跳转到登录页，尝试自动登录。</p>
                    ${createSelectorInput('账号输入框', 'config.loginUserSelector', step.config.loginUserSelector)}
                    ${createInput('账号', 'config.loginUser', step.config.loginUser)}
                    ${createSelectorInput('密码输入框', 'config.loginPassSelector', step.config.loginPassSelector)}
                    ${createInput('密码 - 明文存储', 'config.loginPass', step.config.loginPass)}
                    ${createSelectorInput('登录按钮', 'config.loginBtnSelector', step.config.loginBtnSelector)}
                </div>
            </div>
        `;
        html += createValidationBlock(step);
    }
    else if (step.type === 'input_text' || step.type === 'label_input') {
        html += createSelectorInput('目标元素定位', 'config.selector', step.config.selector);

        html += `
            <div class="form-group mb-4">
                <label class="label">输入内容来源</label>
                <select onchange="updateConfig('inputType', this.value)" class="input-dark">
                    <option value="fixed" ${step.config.inputType === 'fixed' ? 'selected' : ''}>固定文本</option>
                    <option value="excel" ${step.config.inputType === 'excel' ? 'selected' : ''}>Excel 列数据</option>
                </select>
            </div>
        `;

        if (step.config.inputType === 'fixed') {
            html += createInput('输入内容', 'config.value', step.config.value);
        } else {
            const excelStep = state.steps.find(s => s.type === 'excel_read');
            let columns = [];
            if (excelStep && excelStep.config.columns) {
                columns = excelStep.config.columns;
            }

            if (columns.length > 0) {
                html += `
                    <div class="form-group mb-4">
                        <label class="label">选择 Excel 列</label>
                        <select onchange="updateConfig('value', this.value)" class="input-dark">
                            <option value="" disabled ${!step.config.value ? 'selected' : ''}>-- 请选择列名 --</option>
                            ${columns.map(col => `<option value="${col}" ${step.config.value === col ? 'selected' : ''}>${col}</option>`).join('')}
                        </select>
                    </div>
                 `;
            } else {
                html += createInput('Excel 列名 (手动输入)', 'config.value', step.config.value);
                if (!excelStep) html += `<p class="text-xs text-yellow-500 mt-1">⚠️ 未找到 Excel 读取步骤</p>`;
                else html += `<p class="text-xs text-yellow-500 mt-1">⚠️ Excel 文件未读取到表头</p>`;
            }
        }

        if (step.type === 'label_input') {
            html += `<div class="bg-blue-900/20 text-blue-200 text-xs p-2 rounded mt-2 border border-blue-500/30">
                        <i class="fa-solid fa-info-circle"></i> 标签输入逻辑：<br>
                        1. 输入文本<br>
                        2. 回车保存 (Enter)<br>
                        3. 清空输入框
                      </div>`;
        }

        if (step.type === 'input_text') {
            html += createValidationBlock(step);
        }
    }
    else if (step.type === 'click') {
        html += createSelectorInput('元素定位', 'config.selector', step.config.selector);
        html += createValidationBlock(step);
    }
    else if (step.type === 'wait') {
        html += createInput('等待时间 (ms)', 'config.time', step.config.time, 'number');
    }
    else if (step.type === 'keyboard') {
        html += createSelectorInput('先点击/聚焦元素', 'config.selector', step.config.selector);
        html += `
            <div class="text-xs text-gray-400 mt-1 mb-4 pl-1">
                <i class="fa-solid fa-lightbulb text-yellow-500"></i> 若指定，会先点击该元素获取焦点，再发送按键。
            </div>
        `;
        html += createInput('按键内容', 'config.key', step.config.key);
        html += `
            <div class="text-xs text-gray-400 mt-1 mb-4 pl-1">
                支持单键 (Enter, Tab, Escape, A) 或组合键 (Control+C, Shift+Tab)。
                <a href="https://playwright.dev/python/docs/api/class-keyboard" target="_blank" class="text-blue-400 hover:text-blue-300">查看文档</a>
            </div>
        `;
        html += createInput('重复次数', 'config.count', step.config.count || '1', 'number');
        html += createValidationBlock(step);
    }
    else if (step.type === 'excel_read') {
        html += `
             <div class="form-group mb-4">
                <label class="label">Excel 文件路径 (绝对路径)</label>
                <div class="flex gap-2">
                    <input type="text" value="${step.config.filePath || ''}" 
                           onchange="updateConfig('filePath', this.value); reloadExcelColumns(this.value)" 
                           class="input-dark flex-1">
                    <button class="btn-icon" onclick="browseExcel()">📂</button>
                </div>
             </div>
             
             <div class="form-group mb-4">
                <label class="label">结果记录列名</label>
                <input type="text" value="${step.config.statusColumn || '执行结果'}" 
                       oninput="updateConfig('statusColumn', this.value)" 
                       class="input-dark" placeholder="例如: 执行结果">
                <p class="text-xs text-gray-500 mt-1">系统将自动在此列记录 Success 或 Failed。</p>
             </div>
        `;

        if (step.config.columns && step.config.columns.length > 0) {
            html += `
                <div class="form-group mb-4">
                    <label class="label">读取到的表头</label>
                    <div class="flex flex-wrap gap-2">
                        ${step.config.columns.map(col => `<span class="bg-purple-900/40 text-purple-300 px-2 py-1 rounded text-xs border border-purple-500/30">${col}</span>`).join('')}
                    </div>
                </div>
            `;
        }
    }
    else if (step.type === 'upload_file') {
        html += createSelectorInput('上传按钮/输入框', 'config.selector', step.config.selector);

        html += `
            <div class="form-group mb-4">
                <label class="label">文件路径来源</label>
                <select onchange="updateConfig('inputType', this.value)" class="input-dark">
                    <option value="fixed" ${(!step.config.inputType || step.config.inputType === 'fixed') ? 'selected' : ''}>固定路径</option>
                    <option value="excel" ${step.config.inputType === 'excel' ? 'selected' : ''}>Excel 列数据</option>
                </select>
            </div>
        `;

        if (step.config.inputType === 'excel') {
            const excelStep = state.steps.find(s => s.type === 'excel_read');
            let columns = [];
            if (excelStep && excelStep.config.columns) {
                columns = excelStep.config.columns;
            }

            if (columns.length > 0) {
                html += `
                    <div class="form-group mb-4">
                        <label class="label">选择包含文件路径的列</label>
                        <select onchange="updateConfig('filePath', this.value)" class="input-dark">
                            <option value="" disabled ${!step.config.filePath ? 'selected' : ''}>-- 请选择列名 --</option>
                            ${columns.map(col => `<option value="${col}" ${step.config.filePath === col ? 'selected' : ''}>${col}</option>`).join('')}
                        </select>
                    </div>
                 `;
            } else {
                html += createInput('Excel 列名 (手动输入)', 'config.filePath', step.config.filePath);
                if (!excelStep) html += `<p class="text-xs text-yellow-500 mt-1">⚠️ 未找到 Excel 读取步骤</p>`;
                else html += `<p class="text-xs text-yellow-500 mt-1">⚠️ Excel 文件未读取到表头</p>`;
            }
        } else {
            html += `
                <div class="form-group mb-4">
                    <label class="label">本地文件路径</label>
                    <div class="flex gap-2">
                         <input type="text" value="${step.config.filePath || ''}" 
                                onchange="updateConfig('filePath', this.value)" 
                                class="input-dark flex-1">
                         <button class="btn-icon" onclick="alert('TODO: Browse local file for upload (use path manually for now)')">📂</button>
                    </div>
                </div>
            `;
        }

        html += createValidationBlock(step);
    }
    else if (step.type === 'dropdown_select') {
        html += createSelectorInput('触发下拉框', 'config.selector', step.config.selector);
        html += createSelectorInput('选项元素', 'config.optionSelector', step.config.optionSelector || 'li');
        html += `
            <div class="text-xs text-gray-400 mt-1 mb-4 pl-1">
                <i class="fa-solid fa-lightbulb text-yellow-500"></i> 
                提示：请手动展开下拉框后拾取任意一个选项。确保选择器通用（如 "li" 或 ".el-select-dropdown__item"），不要使用特定 ID。
            </div>

            <div class="form-group mb-4">
                <label class="label">展开方式</label>
                <select onchange="updateConfig('expandMethod', this.value)" class="input-dark">
                    <option value="hover" ${(!step.config.expandMethod || step.config.expandMethod === 'hover') ? 'selected' : ''}>悬停展开 - 默认</option>
                    <option value="click" ${step.config.expandMethod === 'click' ? 'selected' : ''}>点击展开</option>
                </select>
                <p class="text-xs text-gray-500 mt-1">若悬停无法展开子菜单，请尝试改为点击。</p>
            </div>
        `;

        html += `
            <div class="form-group mb-4">
                <label class="label">目标文本来源</label>
                <select onchange="updateConfig('inputType', this.value)" class="input-dark">
                    <option value="fixed" ${(!step.config.inputType || step.config.inputType === 'fixed') ? 'selected' : ''}>固定文本</option>
                    <option value="excel" ${step.config.inputType === 'excel' ? 'selected' : ''}>Excel 列数据</option>
                </select>
            </div>
        `;

        if (step.config.inputType === 'excel') {
            // ... (reuse excel logic or simple input) ...
            // Simplified for dropdown: just need column support
            const excelStep = state.steps.find(s => s.type === 'excel_read');
            let columns = excelStep && excelStep.config.columns ? excelStep.config.columns : [];

            if (columns.length > 0) {
                html += `
                    <div class="form-group mb-4">
                        <label class="label">选择 Excel 列 (Select Column)</label>
                        <select onchange="updateConfig('value', this.value)" class="input-dark">
                            <option value="" disabled ${!step.config.value ? 'selected' : ''}>-- 请选择列名 --</option>
                            ${columns.map(col => `<option value="${col}" ${step.config.value === col ? 'selected' : ''}>${col}</option>`).join('')}
                        </select>
                    </div>
                `;
            } else {
                html += createInput('Excel 列名', 'config.value', step.config.value);
                if (!excelStep) html += `<p class="text-xs text-yellow-500 mt-1">⚠️ 未找到 Excel 读取步骤</p>`;
                else html += `<p class="text-xs text-yellow-500 mt-1">⚠️ Excel 文件未读取到表头</p>`;
            }
        } else {
            html += createInput('目标文本', 'config.value', step.config.value);
        }

        // 额外回车选项
        html += `
            <div class="form-group mb-4">
                <label class="label flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" 
                           ${step.config.extraEnter ? 'checked' : ''} 
                           onchange="updateConfig('extraEnter', this.checked)" 
                           class="checkbox-dark">
                    是否执行额外回车？
                </label>
                <p class="text-xs text-gray-500 mt-1">勾选后，在选择完成后会额外执行一次回车键以确认选择。</p>
            </div>
        `;

        html += createValidationBlock(step);
    }


    propertiesContent.innerHTML = html;
}


