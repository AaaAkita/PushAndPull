/* ========== Light Theme List Schemes.js ========== */

let allSchemeDetails = [];

const ICON_MAP = {
    'a': 'fa-robot', 'b': 'fa-bolt', 'c': 'fa-code-branch', 'd': 'fa-database',
    'e': 'fa-envelope', 'f': 'fa-file', 'g': 'fa-gear', 'h': 'fa-house',
    'i': 'fa-image', 'j': 'fa-jar', 'k': 'fa-key', 'l': 'fa-link',
    'm': 'fa-magnifying-glass', 'n': 'fa-network-wired', 'o': 'fa-object-group',
    'p': 'fa-pen', 'q': 'fa-qrcode', 'r': 'fa-rocket', 's': 'fa-shield-halved',
    't': 'fa-table', 'u': 'fa-user', 'v': 'fa-video', 'w': 'fa-wand-magic-sparkles',
    'x': 'fa-xmark', 'y': 'fa-yin-yang', 'z': 'fa-zap',
};

const FALLBACK = 'fa-layer-group';

function getIcon(name) {
    return ICON_MAP[name.toLowerCase()[0]] || FALLBACK;
}

function domain(url) {
    if (!url) return '';
    try { return new URL(url).hostname; } catch { return ''; }
}

function urlFrom(steps) {
    if (!Array.isArray(steps)) return '';
    const s = steps.find(x => x.type === 'open_url');
    return s && s.config && s.config.url ? s.config.url : '';
}

function excelFrom(steps) {
    if (!Array.isArray(steps)) return '';
    const s = steps.find(x => x.type === 'excel_read');
    if (!s || !s.config || !s.config.filePath) return '';
    const fp = s.config.filePath;
    return fp.split(/[\\/]/).pop() || fp;
}

async function init() { await loadSchemes(); }

async function loadSchemes() {
    try {
        const res = await fetch('/api/flows');
        const data = await res.json();
        if (data.status !== 'success') {
            document.title = '加载失败 - Visual Playwright';
            return;
        }
        const items = data.flows || [];
        const details = await Promise.all(items.map(async item => {
            const f = typeof item === 'string' ? item : item.name;
            const mtime = typeof item === 'object' ? item.mtime : 0;
            const mtimeStr = typeof item === 'object' ? item.mtime_str : '';
            try {
                const r = await fetch(`/api/flows/${encodeURIComponent(f)}`);
                const d = await r.json();
                const steps = (d.data && d.data.steps) || [];
                const u = urlFrom(steps);
                const ex = excelFrom(steps);
                return { file: f, name: f.replace('.json', ''), steps, url: u, domain: domain(u), excel: ex, mtime, mtimeStr, running: false };
            } catch { return { file: f, name: f.replace('.json', ''), steps: [], url: '', domain: '', excel: '', mtime, mtimeStr, running: false }; }
        }));
        allSchemeDetails = details;
        render();
    } catch (e) {
        console.error(e);
        document.title = '加载失败 - Visual Playwright';
    }
}

function render() {
    const container = document.getElementById('scheme-list');
    const filter = document.getElementById('scheme-search')?.value.toLowerCase().trim() || '';

    const filtered = allSchemeDetails.filter(s =>
        !filter || s.name.toLowerCase().includes(filter) || s.url.toLowerCase().includes(filter) || s.domain.toLowerCase().includes(filter) || s.excel.toLowerCase().includes(filter)
    );

    document.title = `方案管理中心 (${filtered.length}) - Visual Playwright`;

    if (!filtered.length) {
        container.innerHTML = `<div class="empty"><i class="fa-regular fa-folder-open"></i><strong>暂无方案</strong><p>${filter ? '未找到匹配搜索的方案' : '点击"新建方案"开始创建你的第一个自动化方案'}</p></div>`;
        return;
    }

    // Sort by mtime desc
    filtered.sort((a, b) => b.mtime - a.mtime);

    const groups = {};
    filtered.forEach(s => {
        const k = s.domain || '未设置网页';
        (groups[k] = groups[k] || []).push(s);
    });

    // Sort group keys by max mtime desc within each group
    const keys = Object.keys(groups).sort((a, b) => {
        const ma = Math.max(...groups[a].map(x => x.mtime));
        const mb = Math.max(...groups[b].map(x => x.mtime));
        return mb - ma;
    });

    let html = '<div class="list-header"><span>方案名称</span><span>目标网页</span><span>Excel 文件</span><span>域名</span><span>修改时间</span><span>操作</span></div>';

    keys.forEach(k => {
        const gid = 'g-' + k.replace(/[^a-zA-Z0-9]/g, '_');
        html += `<div class="group-header" onclick="toggleGroup('${gid}')"><i class="fa-solid fa-chevron-down" id="i-${gid}"></i>${k}<span class="badge">${groups[k].length}</span></div>`;
        html += `<div class="group-rows" id="${gid}">`;
        groups[k].forEach(s => {
            const icon = getIcon(s.name);
            const urlHtml = s.url
                ? `<a href="${s.url}" target="_blank" onclick="event.stopPropagation()">${s.url}</a>`
                : `<span class="empty">— 未设置 —</span>`;
            const domHtml = s.domain ? s.domain : '<span class="none">未设置</span>';
            const excelHtml = s.excel
                ? `<i class="fa-solid fa-table"></i>${s.excel}`
                : `<span class="empty">— 未设置 —</span>`;
            const mtimeHtml = s.mtimeStr || '—';
            html += `
                <div class="row" onclick="openScheme('${s.name}')">
                    <span class="name-cell"><span class="icon"><i class="fa-solid ${icon}"></i></span>${s.name}</span>
                    <span class="url-cell"><i class="fa-solid fa-link"></i>${urlHtml}</span>
                    <span class="excel-cell">${excelHtml}</span>
                    <span class="domain-cell ${s.domain ? '' : 'none'}">${domHtml}</span>
                    <span class="mtime-cell">${mtimeHtml}</span>
                    <span class="action-cell">
                        <button class="run" title="运行" onclick="runScheme(event,'${s.name}')"><i class="fa-solid fa-play"></i></button>
                        <button class="stop" title="停止" onclick="stopScheme(event,'${s.name}')"><i class="fa-solid fa-pause"></i></button>
                        <button title="重命名" onclick="renameScheme(event,'${s.name}')"><i class="fa-solid fa-pen"></i></button>
                        <button title="复制" onclick="copyScheme(event,'${s.name}')"><i class="fa-solid fa-copy"></i></button>
                        <button class="del" title="删除" onclick="deleteScheme(event,'${s.name}')"><i class="fa-solid fa-trash"></i></button>
                    </span>
                </div>
            `;
        });
        html += '</div>';
    });

    container.innerHTML = html;
}

function toggleGroup(gid) {
    const rows = document.getElementById(gid);
    const icon = document.getElementById('i-' + gid);
    if (rows && icon) {
        rows.classList.toggle('collapsed');
        icon.style.transform = rows.classList.contains('collapsed') ? 'rotate(-90deg)' : 'rotate(0deg)';
    }
}

function openScheme(name) { window.location.href = `index.html?id=${encodeURIComponent(name)}`; }

async function runScheme(e, name) {
    e.stopPropagation();
    const s = allSchemeDetails.find(x => x.name === name);
    if (!s?.steps?.length) { alert('方案为空，无法运行'); return; }
    try {
        const res = await fetch('/api/execution/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ steps: s.steps, mode: 'normal' }) });
        const data = await res.json();
        if (data.status === 'success') { s.running = true; alert(`方案 [${name}] 已启动运行`); render(); }
        else alert('启动失败: ' + (data.message || '未知错误'));
    } catch (err) { alert('启动请求失败: ' + err); }
}

async function stopScheme(e, name) {
    e.stopPropagation();
    try {
        const res = await fetch('/api/execution/stop', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            const s = allSchemeDetails.find(x => x.name === name);
            if (s) s.running = false;
            alert('运行已停止'); render();
        } else alert('停止失败: ' + (data.message || '未知错误'));
    } catch (err) { alert('停止请求失败: ' + err); }
}

async function copyScheme(e, name) {
    e.stopPropagation();
    const n = prompt(`复制 [${name}] 为:`, name + '_copy');
    if (!n?.trim()) return;
    try {
        const r = await fetch(`/api/flows/${encodeURIComponent(name)}`);
        const d = await r.json();
        if (d.status === 'success') {
            const s = await fetch('/api/flows', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: n.trim(), steps: d.data.steps }) });
            const sd = await s.json();
            if (sd.status === 'success') await loadSchemes(); else alert('复制失败: ' + sd.message);
        } else alert('加载源方案失败');
    } catch (err) { alert('网络错误: ' + err); }
}

async function deleteScheme(e, name) {
    e.stopPropagation();
    if (!confirm(`确定要删除方案 [${name}] 吗？此操作无法撤销。`)) return;
    try { await fetch(`/api/flows/${encodeURIComponent(name)}`, { method: 'DELETE' }); await loadSchemes(); }
    catch (err) { alert('删除失败: ' + err); }
}

async function renameScheme(e, name) {
    e.stopPropagation();
    const n = prompt(`请输入新的方案名称:`, name);
    if (!n?.trim() || n.trim() === name) return;
    try {
        const r = await fetch('/api/flows/rename', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ oldName: name, newName: n.trim() }) });
        const d = await r.json();
        if (d.status === 'success') await loadSchemes(); else alert('重命名失败: ' + d.message);
    } catch (err) { alert('网络错误: ' + err); }
}

async function createNewScheme() {
    const n = prompt('请输入新方案名称:');
    if (!n?.trim()) return;
    try {
        const r = await fetch('/api/flows', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: n.trim(), steps: [] }) });
        const d = await r.json();
        if (d.status === 'success') window.location.href = `index.html?id=${encodeURIComponent(n.trim())}`;
        else alert('创建失败: ' + d.message);
    } catch (err) { alert('创建请求失败: ' + err); }
}

function filterSchemes() { render(); }

// Global exports
Object.assign(window, { filterSchemes, copyScheme, deleteScheme, renameScheme, openScheme, runScheme, stopScheme, toggleGroup, createNewScheme, loadSchemes });

// Init
document.addEventListener('DOMContentLoaded', init);
