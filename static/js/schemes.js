
let allSchemes = [];
let currentEditingId = null;

// Icons bank for random assignment or deterministic based on name hash
const ICONS = [
    'fa-robot', 'fa-bolt', 'fa-layer-group', 'fa-wand-magic-sparkles',
    'fa-rocket', 'fa-code-branch', 'fa-network-wired', 'fa-gears'
];

async function init() {
    await loadSchemes();
}

async function loadSchemes() {
    try {
        const res = await fetch('/api/flows');
        const data = await res.json();
        if (data.status === 'success') {
            allSchemes = data.flows;
            renderSchemeList();
        } else {
            console.error("Failed to load schemes: " + data.message);
        }
    } catch (e) {
        console.error("Network error loading schemes", e);
    }
}

function renderSchemeList() {
    const grid = document.getElementById('scheme-grid');
    const filterInput = document.getElementById('scheme-search');
    const filter = filterInput ? filterInput.value.toLowerCase() : '';
    const countEl = document.getElementById('scheme-count');

    grid.innerHTML = '';

    const filtered = allSchemes.filter(file => {
        const name = file.replace('.json', '');
        return !filter || name.toLowerCase().includes(filter);
    });

    // Sort: Alphabetical
    filtered.sort();

    // Update Count
    if (countEl) countEl.innerText = `共找到 ${filtered.length} 个方案`;

    // 1. "Create New" Card (First item in grid)
    const createCard = document.createElement('div');
    createCard.className = 'scheme-card create-card';
    createCard.onclick = () => window.createNewScheme ? window.createNewScheme() : alert('Init error');
    createCard.innerHTML = `
        <i class="fa-solid fa-plus create-icon"></i>
        <span>新建空白方案</span>
    `;
    grid.appendChild(createCard);

    if (filtered.length === 0 && filter) {
        // No results found
        return;
    }

    filtered.forEach(file => {
        const name = file.replace('.json', '');

        // Deterministic Icon
        const charCode = name.charCodeAt(0) + (name.charCodeAt(name.length - 1) || 0);
        const iconClass = ICONS[charCode % ICONS.length];

        const card = document.createElement('div');
        card.className = 'scheme-card';
        // Click to open
        card.onclick = (e) => {
            // If click wasn't on an action button
            if (!e.target.closest('.card-actions')) {
                openScheme(name);
            }
        };

        const isCurrent = false;

        card.innerHTML = `
            ${isCurrent ? '<div class="status-badge">Current</div>' : ''}
            
            <div class="card-thumb">
                <i class="fa-solid ${iconClass} thumb-icon"></i>
                <div class="card-actions">
                    <button class="action-btn" title="重命名 (Rename)" onclick="renameScheme(event, '${name}')">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    <button class="action-btn" title="Duplicate" onclick="copyScheme(event, '${name}')">
                        <i class="fa-solid fa-copy"></i>
                    </button>
                    <button class="action-btn delete" title="Delete" onclick="deleteScheme(event, '${name}')">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
            
            <div class="card-body">
                <div class="card-title" title="${name}">${name}</div>
                <div class="card-subtitle">${file}</div>
            </div>
        `;
        grid.appendChild(card);
    });
}

function openScheme(name) {
    if (!name) return;
    window.location.href = `index.html?id=${encodeURIComponent(name)}`;
}

async function copyScheme(e, name) {
    if (e) e.stopPropagation();
    const newName = prompt(`复制 [${name}] 为:`, name + "_copy");
    if (newName) {
        try {
            const res = await fetch(`/api/flows/${name}`);
            const data = await res.json();
            if (data.status === 'success') {
                const saveRes = await fetch('/api/flows', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newName, steps: data.data.steps })
                });
                const saveData = await saveRes.json();
                if (saveData.status === 'success') {
                    loadSchemes();
                } else {
                    alert("Copy failed: " + saveData.message);
                }
            } else {
                alert("Failed to load source scheme");
            }
        } catch (err) { alert(err); }
    }
}

async function deleteScheme(e, name) {
    if (e) e.stopPropagation();
    if (confirm(`确定要删除 [${name}] 吗？此操作无法撤销。`)) {
        try {
            await fetch(`/api/flows/${name}`, { method: 'DELETE' });
            await loadSchemes();
        } catch (err) { alert(err); }
    }
}

async function renameScheme(e, name) {
    if (e) e.stopPropagation();
    const newName = prompt(`请输入新的方案名称:`, name);

    // Check if cancelled or empty or unchanged
    if (!newName || newName.trim() === "" || newName === name) return;

    try {
        const res = await fetch('/api/flows/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ oldName: name, newName: newName.trim() })
        });
        const data = await res.json();

        if (data.status === 'success') {
            loadSchemes();
        } else {
            alert('重命名失败: ' + data.message);
        }
    } catch (err) {
        alert('Network Error: ' + err);
    }
}

// Search
window.filterSchemes = renderSchemeList;
window.copyScheme = copyScheme;
window.deleteScheme = deleteScheme;
window.renameScheme = renameScheme;
window.openScheme = openScheme;
window.loadSchemes = loadSchemes; // For refresh btn
window.createNewScheme = null; // Defined in HTML

// Init
document.addEventListener('DOMContentLoaded', init);
