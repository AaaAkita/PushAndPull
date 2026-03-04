export function getTitleByType(type) {
    const map = {
        'excel_read': '读取 Excel',
        'open_url': '打开网址',
        'input_text': '输入文本',
        'click': '点击元素',
        'upload_file': '文件上传',
        'dropdown_select': '下拉智能选择',
        'keyboard': '键盘模拟',
        'wait': '等待/检测',
        'record_excel': '记录结果',
        'label_input': '标签输入'

    };
    return map[type] || type;
}

export function getStepSummary(step) {
    const c = step.config;
    if (step.type === 'open_url') return `打开: ${c.url || '...'}`;
    if (step.type === 'input_text') {
        const val = c.inputType === 'excel' ? `Excel: [${c.value}]` : c.value;
        return `输入: ${val || ''} -> ${c.selector || ''}`;
    }
    if (step.type === 'click') return `点击: ${c.selector || '...'}`;
    if (step.type === 'upload_file') return `上传: ${c.filePath ? '...' + c.filePath.slice(-15) : ''} -> ${c.selector || ''}`;
    if (step.type === 'wait') return `等待: ${c.time}ms`;
    if (step.type === 'excel_read') return `读取文件: ${c.filePath ? '...' + c.filePath.slice(-20) : '未设置'}`;
    if (step.type === 'dropdown_select') {
        const val = step.config.inputType === 'excel' ? `Excel: [${step.config.value}]` : step.config.value;
        return `选择: ${val || ''}`;
    }
    if (step.type === 'label_input') {
        const val = step.config.inputType === 'excel' ? `Excel: [${step.config.value}]` : step.config.value;
        return `标签输入: ${val || ''}`;
    }
    if (step.type === 'keyboard') {
        const target = step.config.selector ? ` -> ${step.config.selector}` : '';
        return `按键: ${step.config.key} (x${step.config.count || 1})${target}`;
    }
    return '';
}

export function escapeAttribute(str) {
    if (str === undefined || str === null) return '';
    return String(str).replace(/"/g, '&quot;');
}
