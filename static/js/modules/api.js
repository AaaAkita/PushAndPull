export async function fetchExcelColumns(path) {
    if (!path) return null;
    try {
        const res = await fetch('/api/get_excel_columns', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        });
        const data = await res.json();
        if (data.status === 'success') {
            return data.columns;
        } else {
            console.warn("Failed to fetch columns:", data.message);
            return null;
        }
    } catch (e) {
        console.error(e);
        return null;
    }
}

export async function browseFile() {
    try {
        const res = await fetch('/api/browse_file', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            return data.path;
        }
    } catch (e) { console.error(e); }
    return null;
}

export async function pickSelectorAPI(url) {
    try {
        const res = await fetch('/api/pick_selector', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url || undefined })
        });
        return await res.json();
    } catch (e) {
        return { status: 'error', message: e.toString() };
    }
}

export async function debugOpenUrl(url) {
    try {
        await fetch('/api/debug/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });
    } catch (e) { console.error(e); }
}

export async function runFlowAPI(steps, options = {}) {
    try {
        const res = await fetch('/api/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ steps: steps, mode: options.mode })
        });
        return await res.json();
    } catch (e) {
        return { status: 'error', message: e.toString() };
    }
}

export async function listFlows() {
    try {
        const res = await fetch('/api/flows');
        const data = await res.json();
        if (data.status === 'success') {
            return data.flows;
        }
        return [];
    } catch (e) {
        console.error(e);
        return [];
    }
}

export async function saveFlowAPI(name, steps) {
    try {
        const res = await fetch('/api/flows', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, steps: steps })
        });
        return await res.json();
    } catch (e) {
        return { status: 'error', message: e.toString() };
    }
}

export async function deleteFlowAPI(name) {
    try {
        const res = await fetch(`/api/flows/${name}`, { method: 'DELETE' });
        return await res.json();
    } catch (e) {
        return { status: 'error', message: e.toString() };
    }
}

export async function renameFlowAPI(oldName, newName) {
    try {
        const res = await fetch('/api/flows/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ oldName, newName })
        });
        return await res.json();
    } catch (e) {
        return { status: 'error', message: e.toString() };
    }
}

export async function loadFlowAPI(name) {
    try {
        const res = await fetch(`/api/flows/${name}`);
        return await res.json();
    } catch (e) {
        console.error(e);
        return null;
    }
}
