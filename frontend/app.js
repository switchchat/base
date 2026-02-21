// ============================================================
// Voice Routines — Frontend
// ============================================================

let isRecording = false;
let activeRoutine = null;

// ---- DOM refs ----
const micBtn = document.getElementById('mic-btn');
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');
const routineList = document.getElementById('routine-list');
const flowContainer = document.getElementById('flow-container');
const canvasEmpty = document.getElementById('canvas-empty');
const chatMessages = document.getElementById('chat-messages');
const bottomLogs = document.getElementById('bottom-logs');
const timingDisplay = document.getElementById('timing-display');
const canvasView = document.getElementById('canvas-view');
const logsView = document.getElementById('logs-view');
const execLog = document.getElementById('execution-log');

// Tool icons
const TOOL_ICONS = {
    get_weather:     { icon: '\u2601\uFE0F', cls: 'weather',  label: 'Weather' },
    play_music:      { icon: '\uD83C\uDFB5', cls: 'music',    label: 'Music' },
    set_timer:       { icon: '\u23F1\uFE0F', cls: 'timer',    label: 'Timer' },
    set_alarm:       { icon: '\u23F0',        cls: 'alarm',    label: 'Alarm' },
    send_message:    { icon: '\uD83D\uDCE8', cls: 'message',  label: 'Message' },
    create_reminder: { icon: '\uD83D\uDD14', cls: 'reminder', label: 'Reminder' },
    search_contacts: { icon: '\uD83D\uDC64', cls: 'contact',  label: 'Contacts' },
};

function getToolVisual(toolName) {
    return TOOL_ICONS[toolName] || { icon: '\u2699\uFE0F', cls: 'default', label: toolName };
}

function now() {
    return new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// ============================================================
// Tab switching
// ============================================================
document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const view = tab.dataset.view;
        canvasView.classList.toggle('hidden', view !== 'canvas');
        logsView.classList.toggle('hidden', view !== 'logs');
    });
});

// ============================================================
// Audio Recording (Python-side)
// ============================================================
async function startRecording() {
    const res = await pywebview.api.start_recording();
    if (res.error) {
        showToast('Mic error: ' + res.error, 'error');
        return;
    }
    isRecording = true;
    micBtn.classList.add('recording');
}

async function stopRecording() {
    isRecording = false;
    micBtn.classList.remove('recording');
    addChatMsg('system', 'Transcribing...');

    const totalStart = performance.now();
    const txResult = await pywebview.api.stop_recording();

    if (txResult.error) {
        removeLast('Processing');
        removeLast('Transcribing');
        addChatMsg('error', 'Transcription error: ' + txResult.error);
        return;
    }
    if (!txResult.text) {
        removeLast('Transcribing');
        addChatMsg('error', 'No speech detected');
        return;
    }

    removeLast('Transcribing');
    addChatMsg('user', txResult.text, txResult.time_ms);
    addChatMsg('system', 'Processing...');

    const cmdResult = await pywebview.api.process_command(txResult.text);
    const totalMs = performance.now() - totalStart;
    handleResult(cmdResult, txResult.time_ms, totalMs);
}

// ============================================================
// Command Flow
// ============================================================
async function processTextCommand(text) {
    if (!text.trim()) return;
    addChatMsg('user', text);
    addChatMsg('system', 'Processing...');

    const totalStart = performance.now();
    const cmdResult = await pywebview.api.process_command(text);
    const totalMs = performance.now() - totalStart;
    handleResult(cmdResult, 0, totalMs);
}

function handleResult(result, transcribeMs, totalMs) {
    removeLast('Processing');

    if (result.type === 'direct') {
        for (const r of result.results) {
            const summary = r.result.summary || `${r.tool} completed`;
            addChatMsg('result', summary, r.time_ms, r.tool);
            addLogLine('success', r.tool, summary);
        }
        showTiming(transcribeMs, result.inference_ms, totalMs);

    } else if (result.type === 'routine_created') {
        addChatMsg('result', result.message, null, 'routine');
        addLogLine('success', 'created', result.routine.name);
        loadRoutines();
        // Auto-select the new routine
        activeRoutine = result.routine;
        renderFlow(result.routine);

    } else if (result.type === 'routine_executed') {
        if (result.result && result.result.results) {
            const allOk = result.result.results.every(r => r.status === 'success');
            // Show each step result in chat
            for (const r of result.result.results) {
                const summary = r.result ? (r.result.summary || JSON.stringify(r.result)) : r.error;
                addChatMsg('result', summary, r.time_ms, r.tool);
            }
            addChatMsg('system', allOk
                ? `Routine "${result.result.routine}" completed successfully`
                : `Routine "${result.result.routine}" finished with errors`);
        }

    } else if (result.type === 'no_action' || result.type === 'error') {
        addChatMsg('error', result.message);
        addLogLine('error', 'error', result.message);
    }
}

// ============================================================
// Chat Messages
// ============================================================
function addChatMsg(type, text, timeMs, toolName) {
    const div = document.createElement('div');
    div.className = `chat-msg ${type}`;

    const timeStr = timeMs ? `<span class="chat-time">${Math.round(timeMs)}ms</span>` : '';

    if (type === 'user') {
        div.innerHTML = `<span class="chat-prefix">\u25B6</span>${escapeHtml(text)}${timeStr}`;
    } else if (type === 'result') {
        const vis = toolName ? getToolVisual(toolName) : null;
        const icon = vis ? `<span class="chat-tool-icon">${vis.icon}</span>` : '';
        div.innerHTML = `${icon}<span class="chat-result-text">${escapeHtml(text)}</span>${timeStr}`;
    } else if (type === 'error') {
        div.innerHTML = `<span class="chat-prefix chat-error-prefix">\u2717</span>${escapeHtml(text)}`;
    } else {
        div.innerHTML = `<span class="chat-prefix chat-sys-prefix">\u2022</span><span class="chat-sys-text">${escapeHtml(text)}</span>`;
    }

    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeLast(containing) {
    const msgs = chatMessages.querySelectorAll('.chat-msg');
    for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].textContent.includes(containing)) {
            msgs[i].remove();
            return;
        }
    }
}

// ============================================================
// Bottom Logs
// ============================================================
function addLogLine(status, tool, detail) {
    const div = document.createElement('div');
    div.className = 'log-line';

    const iconMap = { success: '\u2713', error: '\u2717', running: '\u25CB', info: '\u2022' };
    div.innerHTML = `
        <span class="log-timestamp">${now()}</span>
        <span class="log-icon ${status}">${iconMap[status] || '\u2022'}</span>
        <span class="log-content"><strong>${escapeHtml(tool)}</strong> ${escapeHtml(detail || '')}</span>
    `;
    bottomLogs.appendChild(div);
    bottomLogs.scrollTop = bottomLogs.scrollHeight;
}

// ============================================================
// Routine Flow Canvas
// ============================================================
function renderFlow(routine) {
    if (!routine) {
        flowContainer.innerHTML = '';
        flowContainer.appendChild(canvasEmpty);
        canvasEmpty.style.display = '';
        return;
    }

    canvasEmpty.style.display = 'none';
    flowContainer.innerHTML = '';

    const chain = document.createElement('div');
    chain.className = 'flow-chain';

    // Start node
    const start = document.createElement('div');
    start.className = 'flow-start';
    start.innerHTML = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';
    chain.appendChild(start);

    for (let i = 0; i < routine.steps.length; i++) {
        const step = routine.steps[i];
        const vis = getToolVisual(step.tool);

        // Connector
        const conn = document.createElement('div');
        conn.className = 'flow-connector';
        conn.id = `conn-${i}`;
        chain.appendChild(conn);

        // Node
        const node = document.createElement('div');
        node.className = 'flow-node';
        node.id = `node-${i}`;
        node.draggable = true;
        node.dataset.index = i;

        const argsHtml = Object.entries(step.args || {})
            .map(([k, v]) => `<span class="arg-key">${k}:</span> <span class="arg-val">${escapeHtml(String(v))}</span>`)
            .join('<br>');

        node.innerHTML = `
            <div class="flow-node-header">
                <div class="flow-node-icon ${vis.cls}">${vis.icon}</div>
                <div>
                    <div class="flow-node-title">${escapeHtml(vis.label)}</div>
                    <div class="flow-node-step">Step ${i + 1}</div>
                </div>
            </div>
            ${step.condition ? `<div class="flow-node-condition">◆ ${escapeHtml(step.condition)}</div>` : ''}
            <div class="flow-node-args">${argsHtml}</div>
            <div class="flow-node-result" id="result-${i}"></div>
        `;

        // Drag/drop reorder
        node.addEventListener('dragstart', e => {
            e.dataTransfer.setData('text/plain', i.toString());
            node.style.opacity = '0.5';
        });
        node.addEventListener('dragend', () => { node.style.opacity = '1'; });
        node.addEventListener('dragover', e => e.preventDefault());
        node.addEventListener('drop', e => {
            e.preventDefault();
            const from = parseInt(e.dataTransfer.getData('text/plain'));
            const to = parseInt(node.dataset.index);
            if (from !== to) reorderSteps(routine, from, to);
        });

        chain.appendChild(node);
    }

    flowContainer.appendChild(chain);
}

// Progress callback from Python during routine execution
window.onRoutineProgress = function(step, total, status, result) {
    const nodeIdx = step - 1;
    const node = document.getElementById(`node-${nodeIdx}`);
    const conn = document.getElementById(`conn-${nodeIdx}`);
    const resultDiv = document.getElementById(`result-${nodeIdx}`);

    if (status === 'running') {
        if (node) node.className = 'flow-node running';
        if (resultDiv) resultDiv.innerHTML = '<span class="spinner"></span> Running...';
        addLogLine('running', result ? result.tool : `step ${step}`, 'executing...');
    } else {
        if (node) node.className = `flow-node ${status}`;
        if (conn) conn.className = 'flow-connector active';
        if (result && resultDiv) {
            const summary = result.result ? (result.result.summary || JSON.stringify(result.result)) : result.error;
            const timeStr = result.time_ms ? ` <span class="node-time">${Math.round(result.time_ms)}ms</span>` : '';
            resultDiv.innerHTML = `<span class="node-result-text">${escapeHtml(summary)}</span>${timeStr}`;
        }
        if (result) {
            const detail = result.result ? (result.result.summary || '') : (result.error || 'failed');
            addLogLine(result.status, result.tool, detail);
        }
    }
};

// ============================================================
// Sidebar
// ============================================================
async function loadRoutines() {
    const routines = await pywebview.api.get_routines();
    routineList.innerHTML = '';

    for (const r of routines) {
        const div = document.createElement('div');
        div.className = 'routine-item' + (activeRoutine && activeRoutine.name === r.name ? ' active' : '');
        div.innerHTML = `
            <div class="routine-name">${escapeHtml(r.name)}</div>
            <div class="routine-meta">${r.steps.length} step${r.steps.length !== 1 ? 's' : ''}</div>
            <div class="routine-actions">
                <button class="btn-run" onclick="event.stopPropagation(); runRoutine('${escapeAttr(r.name)}')">Run</button>
                <button class="btn-delete" onclick="event.stopPropagation(); deleteRoutine('${escapeAttr(r.name)}')">Del</button>
            </div>
        `;
        div.addEventListener('click', () => {
            activeRoutine = r;
            renderFlow(r);
            loadRoutines();
        });
        routineList.appendChild(div);
    }
}

async function runRoutine(name) {
    const routines = await pywebview.api.get_routines();
    activeRoutine = routines.find(r => r.name === name) || activeRoutine;
    if (activeRoutine) renderFlow(activeRoutine);
    loadRoutines();

    addChatMsg('system', `Running "${name}"...`);
    addLogLine('info', 'routine', `started: ${name}`);

    const result = await pywebview.api.run_routine(name);
    handleResult(result, 0, 0);
}

async function deleteRoutine(name) {
    await pywebview.api.delete_routine(name);
    showToast(`Deleted "${name}"`, 'info');
    if (activeRoutine && activeRoutine.name === name) {
        activeRoutine = null;
        renderFlow(null);
    }
    loadRoutines();
}

async function reorderSteps(routine, fromIdx, toIdx) {
    const steps = [...routine.steps];
    const [moved] = steps.splice(fromIdx, 1);
    steps.splice(toIdx, 0, moved);
    routine.steps = steps;
    await pywebview.api.update_routine_steps(routine.name, JSON.stringify(steps));
    renderFlow(routine);
    showToast('Steps reordered', 'info');
}

// ============================================================
// Timing
// ============================================================
function showTiming(transcribeMs, inferenceMs, totalMs) {
    const parts = [];
    if (transcribeMs > 0) parts.push(`STT ${Math.round(transcribeMs)}ms`);
    if (inferenceMs > 0) parts.push(`LLM ${Math.round(inferenceMs)}ms`);
    parts.push(`Total ${Math.round(totalMs)}ms`);
    timingDisplay.textContent = parts.join(' \u2022 ');
}

// ============================================================
// Toast
// ============================================================
function showToast(message, type) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type || 'info'}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// ============================================================
// Utilities
// ============================================================
function escapeHtml(str) {
    if (typeof str !== 'string') return String(str);
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function escapeAttr(str) {
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function formatArgs(obj) {
    return Object.entries(obj || {}).map(([k, v]) => `${k}=${v}`).join(', ');
}

// ============================================================
// Event Listeners
// ============================================================
micBtn.addEventListener('click', () => {
    if (isRecording) stopRecording();
    else startRecording();
});

sendBtn.addEventListener('click', () => {
    const text = textInput.value.trim();
    if (text) { textInput.value = ''; processTextCommand(text); }
});

textInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
        const text = textInput.value.trim();
        if (text) { textInput.value = ''; processTextCommand(text); }
    }
});

// ---- Init ----
window.addEventListener('pywebviewready', () => {
    loadRoutines();
    addLogLine('info', 'system', 'Voice Routines ready');
});
