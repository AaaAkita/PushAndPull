export const state = {
    steps: [],
    activeStepIndex: null,
    currentScheme: null,
    isDirty: false,
    flowTitle: '未命名流程'
};

export function setSteps(newSteps) {
    state.steps = newSteps;
    state.isDirty = true; // Mark as dirty whenever steps change
}

export function setIsDirty(value) {
    state.isDirty = value;
}

export function setActiveStepIndex(index) {
    state.activeStepIndex = index;
}

export function setCurrentScheme(name) {
    state.currentScheme = name;
}

export function setFlowTitle(title) {
    state.flowTitle = title;
}
