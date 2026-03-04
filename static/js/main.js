import { state, setSteps, setActiveStepIndex, setCurrentScheme } from './modules/state.js';
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

// --- Initialization ---

function init() {
    // Global Buttons
    // Run Button Handler
    document.getElementById('run-btn').addEventListener('click', async () => {
        const runBtn = document.getElementById('run-btn');
        const stopBtn = document.getElementById('stop-btn');

        runBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 启动中...';
        runBtn.disabled = true;

        // Use Async Start
        // We use fetch directly or add method to API module. 
        // For simplicity, let's assume we can use fetch here or we should ideally add to API.js
        // But since we are editing main.js, let's just do fetch here for the specific endpoints 
        // OR reuse API.runFlowAPI if we update it? 
        // Let's stick to fetch for the new endpoints to avoid editing API.js if not needed, 
        // though clean code suggests updating API.js. 
        // Let's just do fetch here for valid JSON to be safe.

        try {
            const res = await fetch('/api/execution/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ steps: state.steps, mode: 'normal' })
            });
            const data = await res.json();

            if (data.status === 'success') {
                runBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 运行中...';
                stopBtn.disabled = false;
                startPolling();
            } else {
                alert("启动失败: " + data.message);
                runBtn.innerHTML = '<i class="fa-solid fa-play"></i> 运行流程';
                runBtn.disabled = false;
            }
        } catch (e) {
            alert("启动请求错误: " + e);
            runBtn.innerHTML = '<i class="fa-solid fa-play"></i> 运行流程';
            runBtn.disabled = false;
        }
    });

    // Stop Button Handler
    document.getElementById('stop-btn').addEventListener('click', async () => {
        if (!confirm("确定要停止运行吗?")) return;

        const stopBtn = document.getElementById('stop-btn');
        stopBtn.disabled = true; // Prevent double click
        stopBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 停止中...';

        try {
            await fetch('/api/execution/stop', { method: 'POST' });
        } catch (e) {
            console.error("Stop failed", e);
        }
    });

    // Polling Logic
    let pollInterval = null;
    let lastLogCount = 0; // To show only new logs if we wanted, but UI usually doesn't show logs live in this version?
    // Wait, the previous code showed alert ONLY at the end.
    // "res.logs ... join"
    // The user wants to see logs? The original requirement didn't explicitly say "show logs live", 
    // but the original run button showed an alert at the end with logs.
    // If we run async, we can't alert at the end easily if the user closes the tab.
    // But if the tab is open, we should probably show logs or at least status.
    // Since there is no log console in the UI (only empty-state or canvas), 
    // maybe we should just accumulate logs and alert at the end like before?
    // Or just console.log for now?
    // The previous implementation: alert('流程执行完成!\n' + (res.logs || []).join('\n'));
    // We should try to replicate this behavior: when finished, show alert.

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);

        pollInterval = setInterval(async () => {
            try {
                const res = await fetch('/api/execution/status');
                const data = await res.json();

                if (data.status === 'success') {
                    const info = data.data; // { is_running: bool, logs: [] }

                    if (!info.is_running) {
                        // Finished
                        clearInterval(pollInterval);
                        pollInterval = null;

                        document.getElementById('run-btn').innerHTML = '<i class="fa-solid fa-play"></i> 运行流程';
                        document.getElementById('run-btn').disabled = false;
                        document.getElementById('stop-btn').innerHTML = '<i class="fa-solid fa-stop"></i> 停止流程';
                        document.getElementById('stop-btn').disabled = true;

                        // Check if it was stopped or finished naturally?
                        // The logs usually contain the info.
                        const finalLogs = info.logs || [];
                        const lastLog = finalLogs[finalLogs.length - 1] || "";

                        if (lastLog.includes("⛔")) {
                            alert("流程已停止!\n" + finalLogs.join('\n'));
                        } else {
                            alert("流程执行完成!\n" + finalLogs.join('\n'));
                        }
                    } else {
                        // Still running
                        // We could update UI to show log count or last log?
                        // For now just keep spinning
                    }
                }
            } catch (e) {
                console.error("Poll error", e);
            }
        }, 1000);
    }

    // Check status on load in case page was refreshed while running
    checkInitialStatus();

    async function checkInitialStatus() {
        try {
            const res = await fetch('/api/execution/status');
            const data = await res.json();
            if (data.status === 'success' && data.data && data.data.is_running) {
                document.getElementById('run-btn').innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 运行中...';
                document.getElementById('run-btn').disabled = true;
                document.getElementById('stop-btn').disabled = false;
                startPolling();
            }
        } catch (e) {
            console.log("Initial status check failed", e);
        }
    }

    document.getElementById('save-btn').addEventListener('click', async () => {
        const success = await saveScheme();
        if (success) {
            // Already alert inside saveScheme
        }
    });

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
