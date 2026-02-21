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
    get_weather: { icon: '\u2601', cls: 'weather' },
    play_music: { icon: '\u266B', cls: 'music' },
    set_timer: { icon: '\u23F1', cls: 'timer' },
    set_alarm: { icon: '\u23F0', cls: 'alarm' },
    send_message: { icon: '\u2709', cls: 'message' },
    create_reminder: { icon: '\uD83D\uDD14', cls: 'reminder' },
    search_contacts: { icon: '\uD83D\uDC64', cls: 'contact' },
};

function getToolVisual(toolName) {
    return TOOL_ICONS[toolName] || { icon: '\u2699', cls: 'default' };
}

function now() {
    const d = new Date();
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
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
        addChatMsg('error', 'Transcription error: ' + txResult.error);
        return;
    }
    if (!txResult.text) {
        addChatMsg('error', 'No speech detected');
        return;
    }

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
    // Remove "Processing..." message
    const msgs = chatMessages.querySelectorAll('.chat-msg.system');
    const last = msgs[msgs.length - 1];
    if (last && last.textContent.includes('Processing')) last.remove();

    if (result.type === 'direct') {
        for (const r of result.results) {
            addChatMsg('system', `${r.tool}(${formatArgs(r.args)})`, r.time_ms);
            addLogLine('success', r.tool, formatArgs(r.args));
        }
        showTiming(transcribeMs, result.inference_ms, totalMs);
        showToast('Command executed', 'success');

    } else if (result.type === 'routine_created') {
        addChatMsg('system', result.message);
        addLogLine('success', 'routine_created', result.routine.name);
        showToast(result.message, 'success');
        loadRoutines();

    } else if (result.type === 'routine_executed') {
        if (result.result && result.result.results) {
            const allOk = result.result.results.every(r => r.status === 'success');
            addChatMsg('system', `Routine "${result.result.routine}" ${allOk ? 'completed' : 'finished with errors'}`);
            showToast(`Routine ${allOk ? 'completed' : 'had errors'}`, allOk ? 'success' : 'error');
        }

    } else if (result.type === 'no_action' || result.type === 'error') {
        addChatMsg('error', result.message);
        addLogLine('error', 'no_action', result.message);
    }
}

// ============================================================
// Chat Messages
// ============================================================
function addChatMsg(type, text, timeMs) {
    const div = document.createElement('div');
    const cls = type === 'error' ? 'chat-msg error-msg' : `chat-msg ${type}`;
    div.className = cls;

    const prefix = type === 'user' ? 'You' : type === 'error' ? 'Error' : 'System';
    const timeStr = timeMs ? `<span class="chat-time">${Math.round(timeMs)}ms</span>` : '';

    div.innerHTML = `<span class="chat-prefix">${prefix}</span>${escapeHtml(text)}${timeStr}`;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
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
                    <div class="flow-node-title">${escapeHtml(step.tool)}</div>
                    <div class="flow-node-step">Step ${i + 1}</div>
                </div>
            </div>
            <div class="flow-node-args">${argsHtml}</div>
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

    if (status === 'running') {
        if (node) node.className = 'flow-node running';
        addLogLine('running', result ? result.tool : `Step ${step}`, 'executing...');
    } else {
        if (node) node.className = `flow-node ${status}`;
        if (conn) conn.className = 'flow-connector active';
        if (result) {
            const detail = result.status === 'success'
                ? formatArgs(result.result || {})
                : (result.error || 'failed');
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
            loadRoutines(); // re-render active state
        });
        routineList.appendChild(div);
    }
}

async function runRoutine(name) {
    // Select it first
    const routines = await pywebview.api.get_routines();
    activeRoutine = routines.find(r => r.name === name) || activeRoutine;
    if (activeRoutine) renderFlow(activeRoutine);
    loadRoutines();

    addChatMsg('system', `Running routine "${name}"...`);
    addLogLine('info', 'routine', `started: ${name}`);

    const result = await pywebview.api.process_command('run ' + name);
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
    return str.replace(/'/g, "\\'").replace(/"/g, '\\"');
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
