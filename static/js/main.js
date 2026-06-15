import { state, setSteps, setActiveStepIndex, setCurrentScheme, setIsDirty, setFlowTitle } from './modules/state.js';
import { getTitleByType } from './modules/utils.js';
import * as API from './modules/api.js';
import * as UI from './modules/ui.js';

// --- Business Logic ---

function addStep(type) {
    const newStep = {
        id: Date.now().toString(),
        type: type,
        title: getTitleByType(type),
        config: {
            waitBefore: 500,
            waitForSelector: "",
            // Type-specific defaults
            ...(type === 'open_url' ? {
                url: '',
                loginUserSelector: '',
                loginPassSelector: '',
                loginBtnSelector: '',
                loginUser: '',
                loginPass: '',
                waitAfter: 0, validateSelector: ''
            } : {}),
            ...(type === 'input_text' ? { selector: '', inputType: 'fixed', value: '', waitAfter: 0, validateSelector: '' } : {}),
            ...(type === 'keyboard' ? { selector: '', key: '', count: 1, waitBefore: 500, waitAfter: 0, validateSelector: '' } : {}),
            ...(type === 'label_input' ? { selector: '', inputType: 'fixed', value: '' } : {}),
            ...(type === 'click' ? { selector: '', waitAfter: 0, validateSelector: '' } : {}),
            ...(type === 'upload_file' ? { selector: '', filePath: '', waitAfter: 0, validateSelector: '' } : {}),
            ...(type === 'excel_read' ? { filePath: '', statusColumn: '执行结果' } : {}),
            ...(type === 'dropdown_select' ? { selector: '', optionSelector: 'li', value: '', inputType: 'fixed', expandMethod: 'hover', extraEnter: false, waitBefore: 500, waitAfter: 0, validateSelector: '' } : {}),

            ...(type === 'wait' ? { time: 1000 } : {}),
        }
    };
    const newSteps = [...state.steps];

    // Insert Logic: Append to end if nothing selected, or insert after selected
    if (state.activeStepIndex !== null && state.activeStepIndex >= 0 && state.activeStepIndex < newSteps.length) {
        newSteps.splice(state.activeStepIndex + 1, 0, newStep);
        setSteps(newSteps);
        selectStep(state.activeStepIndex + 1);
    } else {
        newSteps.push(newStep);
        setSteps(newSteps);
        selectStep(newSteps.length - 1);
    }
}

function selectStep(index) {
    setActiveStepIndex(index);
    UI.renderCanvas(); // Update active state styling
    UI.renderProperties();
    syncTestButton();
}

function removeStep(e, index) {
    e.stopPropagation(); // Prevent selection
    const newSteps = [...state.steps];
    newSteps.splice(index, 1);
    setSteps(newSteps);

    if (state.activeStepIndex === index) {
        setActiveStepIndex(null);
    } else if (state.activeStepIndex > index) {
        setActiveStepIndex(state.activeStepIndex - 1);
    }
    UI.renderCanvas();
    UI.renderProperties();
}

function moveStep(fromIndex, toIndex) {
    const steps = [...state.steps];
    const originalActiveId = state.steps[state.activeStepIndex] ? state.steps[state.activeStepIndex].id : null;

    const [movedStep] = steps.splice(fromIndex, 1);
    // Adjustment for shifting indices
    if (fromIndex < toIndex) {
        toIndex = toIndex - 1;
    }
    steps.splice(toIndex, 0, movedStep);
    setSteps(steps);

    // Restore selection by ID
    if (originalActiveId) {
        const newIdx = steps.findIndex(s => s.id === originalActiveId);
        setActiveStepIndex(newIdx);
    }

    UI.renderCanvas();
    UI.renderProperties();
}

function duplicateStep(e, index) {
    if (e) e.stopPropagation();

    // Deep copy the step
    const steps = [...state.steps];
    const originalStep = steps[index];

    // Create deep copy using JSON parse/stringify to handle nested objects (config) safely
    const newStep = JSON.parse(JSON.stringify(originalStep));

    // Update ID and Title
    newStep.id = Date.now().toString();
    newStep.title = originalStep.title + " (Copy)";

    // Insert after the original step
    steps.splice(index + 1, 0, newStep);

    setSteps(steps);
    // Select the new step
    selectStep(index + 1);
    UI.renderCanvas();
    UI.renderProperties();
}

function clearSteps() {
    if (confirm("确定要清空所有步骤吗？")) {
        setSteps([]);
        setActiveStepIndex(null);
        setCurrentScheme(null);
        UI.renderCanvas();
        UI.renderProperties();
        // Clear query param?
        window.history.pushState({}, document.title, window.location.pathname);
    }
}

function updateConfig(key, value, type) {
    if (state.activeStepIndex !== null) {
        const steps = [...state.steps];
        const step = steps[state.activeStepIndex];

        if (key.includes('.')) {
            const parts = key.split('.');
            step.config[parts[0]][parts[1]] = value;
        } else {
            step.config[key] = value;
        }
        setSteps(steps);

        UI.renderCanvas();

        if (key === 'inputType' || key === 'filePath') {
            UI.renderProperties();
        }
    }
}

function updateRoot(key, value) {
    if (state.activeStepIndex !== null) {
        const steps = [...state.steps];
        steps[state.activeStepIndex][key] = value;
        setSteps(steps);
        UI.renderCanvas();
    }
}

// --- API Helpers Wrapper ---

async function browseExcel() {
    const path = await API.browseFile();
    if (path) {
        const steps = [...state.steps];
        steps[state.activeStepIndex].config.filePath = path;
        setSteps(steps);

        if (steps[state.activeStepIndex].type === 'excel_read') {
            await fetchExcelColumns(state.activeStepIndex, path);
        }

        UI.renderProperties();
        UI.renderCanvas();
    }
}

async function fetchExcelColumns(index, path) {
    const cols = await API.fetchExcelColumns(path);
    if (cols) {
        const steps = [...state.steps];
        steps[index].config.columns = cols;
        setSteps(steps);
        console.log("Columns fetched:", cols);
    }
}

async function reloadExcelColumns(path) {
    if (state.activeStepIndex !== null) {
        await fetchExcelColumns(state.activeStepIndex, path);
    }
}

async function saveScheme() {
    console.log("Saving scheme...");
    let name = state.currentScheme;

    if (!name) {
        name = prompt("请输入方案名称:", "flow.json");
        if (!name) return false;
    }

    // Ensure .json
    if (!name.endsWith('.json')) {
        name += '.json';
    }

    const res = await API.saveFlowAPI(name, state.steps);
    if (res.status === 'success') {
        const { setIsDirty, setCurrentScheme } = await import('./modules/state.js');
        setCurrentScheme(name);
        setIsDirty(false); // Reset dirty flag
        updateSaveStatus(false);
        alert(`方案 [${name}] 保存成功!`);
        // Update URL if new
        const url = new URL(window.location);
        if (url.searchParams.get('id') !== name) {
            url.searchParams.set('id', name);
            window.history.pushState({}, '', url);
        }
        return true;
    } else {
        alert("保存失败: " + res.message);
        return false;
    }
}

async function pickSelector(configKey) {
    const url = prompt("请输入 URL 来辅助拾取 (留空使用当前页面):");
    const data = await API.pickSelectorAPI(url);
    if (data.status === 'success') {
        const selector = data.selector;
        updateConfig(configKey, selector);
        // Store picker metadata for UI display
        const meta = {
            strategy: data.strategy || 'unknown',
            confidence: data.confidence || 'low',
            warnings: data.warnings || []
        };
        updateConfig('_pickerMeta', meta);
        alert(`已拾取: ${selector}`);
        UI.renderProperties();
    } else {
        alert("拾取失败: " + data.message);
    }
}

async function testOpenUrl() {
    const step = state.steps[state.activeStepIndex];
    if (step && step.config.url) {
        await API.debugOpenUrl(step.config.url);
    } else {
        alert("请输入 URL");
    }
}


// --- Run Single Step ---
async function testStep(e, index) {
    if (e) e.stopPropagation();

    const step = state.steps[index];
    if (!step) return;

    console.log(`Testing step ${index}:`, step);

    // Prepare steps to run
    // If we have an excel_read step in the flow, we should include it
    // to provide context (data vars) for the test step.
    const stepsToRun = [];
    const excelStep = state.steps.find(s => s.type === 'excel_read');
    if (excelStep) {
        stepsToRun.push(excelStep);
    }
    stepsToRun.push(step);

    // We send payload
    const res = await API.runFlowAPI(stepsToRun, { mode: 'test' });

    if (!res) {
        alert("执行失败: 服务器无响应或网络错误");
        return;
    }

    // Engine returns { logs: [], success: bool } inside res.result
    const resultData = res.result || {};
    const logs = resultData.logs || [];
    const isLogicSuccess = resultData.success !== false; // Default true if undefined

    if (res.status === 'success' && isLogicSuccess) {
        console.log("Step output:", logs);
        alert("执行成功 (Success)!");
    } else {
        const errorMsg = res.message || logs.join('\n') || "未知错误";
        alert(`步骤执行失败 (Failed):\n${errorMsg}`);
    }
}

// --- Toolbar Helpers ---

function getElement(id, fallbackId) {
    return document.getElementById(id) || (fallbackId ? document.getElementById(fallbackId) : null);
}

function bindBtn(id, fallbackId, handler) {
    const btn = getElement(id, fallbackId);
    if (btn) btn.addEventListener('click', handler);
    return btn;
}

function updateSaveStatus(isDirty) {
    const el = document.getElementById('save-status');
    if (!el) return;
    if (isDirty) {
        el.textContent = '未保存';
        el.classList.add('dirty');
    } else {
        el.textContent = '已保存';
        el.classList.remove('dirty');
    }
}

function syncTestButton() {
    const btn = document.getElementById('test-btn-top');
    if (btn) btn.disabled = state.activeStepIndex === null;
}

function updateTitleFromState() {
    const input = document.getElementById('flow-title');
    if (input && state.flowTitle) {
        input.value = state.flowTitle;
        document.title = state.flowTitle + ' - Visual Playwright';
    }
}

// --- Initialization ---

function init() {
    const runBtn = getElement('run-btn-top', 'run-btn');
    const stopBtn = getElement('stop-btn-top', 'stop-btn');
    const saveBtn = getElement('save-btn-top', 'save-btn');

    // Run Button Handler
    if (runBtn) {
        runBtn.addEventListener('click', async () => {
            runBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 启动中...';
            runBtn.disabled = true;

            try {
                const res = await fetch('/api/execution/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ steps: state.steps, mode: 'normal' })
                });
                const data = await res.json();

                if (data.status === 'success') {
                    runBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 运行中...';
                    if (stopBtn) stopBtn.disabled = false;
                    startPolling();
                } else {
                    alert("启动失败: " + data.message);
                    runBtn.innerHTML = '<i class="fa-solid fa-play"></i> 运行';
                    runBtn.disabled = false;
                }
            } catch (e) {
                alert("启动请求错误: " + e);
                runBtn.innerHTML = '<i class="fa-solid fa-play"></i> 运行';
                runBtn.disabled = false;
            }
        });
    }

    // Stop Button Handler
    if (stopBtn) {
        stopBtn.addEventListener('click', async () => {
            if (!confirm("确定要停止运行吗?")) return;
            stopBtn.disabled = true;
            stopBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 停止中...';
            try {
                await fetch('/api/execution/stop', { method: 'POST' });
            } catch (e) {
                console.error("Stop failed", e);
            }
        });
    }

    // Polling Logic
    let pollInterval = null;

    function resetRunButtons() {
        const rb = getElement('run-btn-top', 'run-btn');
        const sb = getElement('stop-btn-top', 'stop-btn');
        if (rb) {
            rb.innerHTML = '<i class="fa-solid fa-play"></i> 运行';
            rb.disabled = false;
        }
        if (sb) {
            sb.innerHTML = '<i class="fa-solid fa-stop"></i> 停止';
            sb.disabled = true;
        }
    }

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);

        pollInterval = setInterval(async () => {
            try {
                const res = await fetch('/api/execution/status');
                const data = await res.json();

                if (data.status === 'success') {
                    const info = data.data;

                    if (!info.is_running) {
                        clearInterval(pollInterval);
                        pollInterval = null;
                        resetRunButtons();

                        const finalLogs = info.logs || [];
                        const lastLog = finalLogs[finalLogs.length - 1] || "";

                        if (lastLog.includes("⛔")) {
                            alert("流程已停止!\n" + finalLogs.join('\n'));
                        } else {
                            alert("流程执行完成!\n" + finalLogs.join('\n'));
                        }
                    }
                }
            } catch (e) {
                console.error("Poll error", e);
            }
        }, 1000);
    }

    async function checkInitialStatus() {
        try {
            const res = await fetch('/api/execution/status');
            const data = await res.json();
            if (data.status === 'success' && data.data && data.data.is_running) {
                const rb = getElement('run-btn-top', 'run-btn');
                if (rb) {
                    rb.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 运行中...';
                    rb.disabled = true;
                }
                if (stopBtn) stopBtn.disabled = false;
                startPolling();
            }
        } catch (e) {
            console.log("Initial status check failed", e);
        }
    }

    checkInitialStatus();

    // Save Button Handler
    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            await saveScheme();
        });
    }

    // Test Button Handler
    const testBtn = document.getElementById('test-btn-top');
    if (testBtn) {
        testBtn.addEventListener('click', () => {
            if (state.activeStepIndex !== null) {
                testStep(null, state.activeStepIndex);
            }
        });
    }

    // Flow Title Editing
    const titleInput = document.getElementById('flow-title');
    if (titleInput) {
        titleInput.addEventListener('change', () => {
            const value = titleInput.value.trim() || '未命名流程';
            setFlowTitle(value);
            document.title = value + ' - Visual Playwright';
        });
        titleInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') titleInput.blur();
        });
    }

    // Save status polling
    setInterval(() => {
        updateSaveStatus(state.isDirty);
    }, 500);

    // Make global for inline handlers
    window.addStep = addStep;
    window.duplicateStep = duplicateStep;
    window.removeStep = removeStep;
    window.moveStep = moveStep;
    window.testStep = testStep;
    window.selectStep = selectStep;
    window.clearSteps = clearSteps;
    window.updateConfig = updateConfig;
    window.updateRoot = updateRoot;
    window.browseExcel = browseExcel;
    window.fetchExcelColumns = fetchExcelColumns;
    window.reloadExcelColumns = reloadExcelColumns;
    window.pickSelector = pickSelector;
    window.testOpenUrl = testOpenUrl;
    window.handleSchemeNav = handleSchemeNav;

    // Load from URL param
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id');
    if (id) {
        loadSchemeById(id);
    }

    updateTitleFromState();
    syncTestButton();

    // Render initial state
    UI.renderCanvas();
}

// New Navigation Guard
async function handleSchemeNav() {
    if (state.isDirty) {
        // Use a Confirm dialog to ask user
        // True = Save, False = Don't Save (Direct Go)
        // Note: Standard confirm doesn't have "Cancel" (Stay). 
        // We will interpret "Cancel" of confirm as "Don't Save".
        // If user wants to "Stay", they currently can't via simple confirm.
        // But user request said: "Save -> Go, No Save -> Go".
        const wantSave = confirm("当前方案有未保存的修改。\n\n[确定] = 保存并跳转\n[取消] = 不保存，直接跳转");

        if (wantSave) {
            const success = await saveScheme();
            if (success) {
                window.location.href = 'schemes.html';
            }
            // If save failed or cancelled, we stay.
        } else {
            // User chose not to save
            window.location.href = 'schemes.html';
        }
    } else {
        window.location.href = 'schemes.html';
    }
}


async function loadSchemeById(name) {
    // Correctly handle the API response structure { status: 'success', data: { steps: ... } }
    const res = await API.loadFlowAPI(name);

    // Check if we got a valid response wrapper
    if (res && res.status === 'success' && res.data) {
        // Access steps from the inner 'data' object
        setSteps(res.data.steps || []);

        // Reset dirty after load (setSteps sets it to true, so we override)
        const { setIsDirty } = await import('./modules/state.js');
        setIsDirty(false);

        setActiveStepIndex(null);

        // Normalize name
        const finalName = name.endsWith('.json') ? name : name + '.json';
        setCurrentScheme(finalName);

        UI.renderCanvas();
        UI.renderProperties();
        console.log(`Loaded scheme: ${finalName}`);
    } else {
        console.error("Failed to load scheme:", res);
        alert("无法加载方案: " + (res ? res.message : 'Unknown Error'));
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
