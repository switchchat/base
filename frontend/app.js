// ============================================================
// Voice Routines — Frontend App
// ============================================================

let isRecording = false;

// ---- DOM refs ----
const micBtn = document.getElementById('mic-btn');
const micLabel = document.getElementById('mic-label');
const waveformCanvas = document.getElementById('waveform');
const execLog = document.getElementById('execution-log');
const routineList = document.getElementById('routine-list');
const timingDisplay = document.getElementById('timing-display');
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');

// ============================================================
// Audio Recording (Python-side via sounddevice)
// ============================================================

async function startRecording() {
    const res = await pywebview.api.start_recording();
    if (res.status === 'already_recording') return;
    if (res.error) {
        showToast('Mic error: ' + res.error, 'error');
        return;
    }
    isRecording = true;
    micBtn.classList.add('recording');
    micLabel.textContent = 'Recording... click to stop';
}

async function stopRecording() {
    isRecording = false;
    micBtn.classList.remove('recording');
    micLabel.textContent = 'Transcribing...';

    const totalStart = performance.now();
    const txResult = await pywebview.api.stop_recording();

    if (txResult.error) {
        showToast('Transcription error: ' + txResult.error, 'error');
        micLabel.textContent = 'Click to record';
        return;
    }

    const text = txResult.text;
    if (!text) {
        showToast('No speech detected', 'error');
        micLabel.textContent = 'Click to record';
        return;
    }

    addTranscript(text, txResult.time_ms);
    micLabel.textContent = 'Executing...';

    const cmdResult = await pywebview.api.process_command(text);
    const totalMs = performance.now() - totalStart;

    handleResult(cmdResult, txResult.time_ms, totalMs);
    micLabel.textContent = 'Click to record';
}

// ============================================================
// Command Flow
// ============================================================

async function processTextCommand(text) {
    if (!text.trim()) return;
    addTranscript(text, 0);
    micLabel.textContent = 'Processing...';

    const totalStart = performance.now();
    const cmdResult = await pywebview.api.process_command(text);
    const totalMs = performance.now() - totalStart;

    handleResult(cmdResult, 0, totalMs);
    micLabel.textContent = 'Click to record';
}

function handleResult(result, transcribeMs, totalMs) {
    if (result.type === 'direct') {
        for (const r of result.results) {
            addLogEntry(r.tool, r.args, r.result, 'success', r.time_ms);
        }
        showTiming(transcribeMs, result.inference_ms, totalMs);
        showToast('Command executed', 'success');

    } else if (result.type === 'routine_created') {
        addRoutineHeader('Created: ' + result.routine.name);
        for (let i = 0; i < result.routine.steps.length; i++) {
            const s = result.routine.steps[i];
            addLogEntry(s.tool, s.args, null, 'success', 0);
        }
        showToast(result.message, 'success');
        loadRoutines();

    } else if (result.type === 'routine_executed') {
        if (result.result && result.result.results) {
            let allSuccess = true;
            for (const r of result.result.results) {
                if (r.status !== 'success') allSuccess = false;
            }
            showToast(
                `Routine "${result.result.routine}" ${allSuccess ? 'completed' : 'finished with errors'}`,
                allSuccess ? 'success' : 'error'
            );
        }

    } else if (result.type === 'no_action') {
        addLogEntry('system', {}, { message: result.message }, 'error', 0);
        showToast(result.message, 'error');

    } else if (result.type === 'error') {
        addLogEntry('system', {}, { message: result.message }, 'error', 0);
        showToast(result.message, 'error');
    }
}

// ============================================================
// UI Rendering
// ============================================================

function clearEmptyState() {
    const empty = execLog.querySelector('.empty-state');
    if (empty) empty.remove();
}

function addTranscript(text, timeMs) {
    clearEmptyState();
    const div = document.createElement('div');
    div.className = 'transcript-entry';
    div.innerHTML = `
        <div class="label">You said${timeMs > 0 ? ` (${Math.round(timeMs)}ms)` : ''}</div>
        <div class="text">${escapeHtml(text)}</div>
    `;
    execLog.appendChild(div);
    execLog.scrollTop = execLog.scrollHeight;
}

function addRoutineHeader(text) {
    clearEmptyState();
    const div = document.createElement('div');
    div.className = 'routine-header';
    div.textContent = text;
    execLog.appendChild(div);
    execLog.scrollTop = execLog.scrollHeight;
}

function addLogEntry(tool, args, result, status, timeMs) {
    clearEmptyState();
    const div = document.createElement('div');
    div.className = `log-entry ${status}`;

    const argsStr = Object.entries(args || {}).map(([k, v]) => `${k}: ${v}`).join(', ');
    const resultStr = result ? JSON.stringify(result, null, 2) : '';

    div.innerHTML = `
        <div class="entry-header">
            <span class="entry-tool">${escapeHtml(tool)}</span>
            <span class="entry-status ${status}">
                ${status === 'running' ? '<span class="spinner"></span> ' : ''}${status}
            </span>
        </div>
        ${argsStr ? `<div class="entry-args">${escapeHtml(argsStr)}</div>` : ''}
        ${resultStr ? `<div class="entry-result">${escapeHtml(resultStr)}</div>` : ''}
        ${timeMs > 0 ? `<div class="entry-time">${Math.round(timeMs)}ms</div>` : ''}
    `;
    execLog.appendChild(div);
    execLog.scrollTop = execLog.scrollHeight;
    return div;
}

function showTiming(transcribeMs, inferenceMs, totalMs) {
    const parts = [];
    if (transcribeMs > 0) parts.push(`transcribe: ${Math.round(transcribeMs)}ms`);
    if (inferenceMs > 0) parts.push(`inference: ${Math.round(inferenceMs)}ms`);
    parts.push(`total: ${Math.round(totalMs)}ms`);
    timingDisplay.textContent = parts.join(' | ');
}

// ---- Routine progress callback (called from Python) ----
window.onRoutineProgress = function(step, total, status, result) {
    if (step === 1 && status === 'running') {
        clearEmptyState();
    }

    if (status === 'running') {
        const div = addLogEntry(
            result ? result.tool : `Step ${step}`,
            result ? result.args : {},
            null,
            'running',
            0
        );
        div.id = `step-${step}`;
    } else {
        const existing = document.getElementById(`step-${step}`);
        if (existing) {
            existing.remove();
        }
        if (result) {
            addLogEntry(
                result.tool,
                result.args,
                result.result || { error: result.error },
                result.status,
                result.time_ms
            );
        }
    }
};

// ============================================================
// Routine Sidebar
// ============================================================

async function loadRoutines() {
    const routines = await pywebview.api.get_routines();
    routineList.innerHTML = '';

    for (const r of routines) {
        const div = document.createElement('div');
        div.className = 'routine-item';
        div.innerHTML = `
            <div class="routine-name">${escapeHtml(r.name)}</div>
            <div class="routine-meta">${r.steps.length} step${r.steps.length !== 1 ? 's' : ''}</div>
            <div class="routine-actions">
                <button class="btn-run" onclick="event.stopPropagation(); runRoutine('${escapeAttr(r.name)}')">Run</button>
                <button class="btn-delete" onclick="event.stopPropagation(); deleteRoutine('${escapeAttr(r.name)}')">Delete</button>
            </div>
        `;
        div.addEventListener('click', () => showRoutineDetail(r));
        routineList.appendChild(div);
    }
}

function showRoutineDetail(routine) {
    clearEmptyState();
    execLog.innerHTML = '';
    addRoutineHeader('Routine: ' + routine.name);

    for (let i = 0; i < routine.steps.length; i++) {
        const step = routine.steps[i];
        const card = document.createElement('div');
        card.className = 'step-card';
        card.draggable = true;
        card.dataset.index = i;

        const argsStr = Object.entries(step.args || {}).map(([k, v]) => `${k}: ${v}`).join(', ');
        card.innerHTML = `
            <div class="step-num">${i + 1}</div>
            <div class="step-info">
                <div class="step-tool">${escapeHtml(step.tool)}</div>
                <div class="step-args">${escapeHtml(argsStr)}</div>
            </div>
        `;

        card.addEventListener('dragstart', (e) => {
            card.classList.add('dragging');
            e.dataTransfer.setData('text/plain', i.toString());
        });
        card.addEventListener('dragend', () => card.classList.remove('dragging'));
        card.addEventListener('dragover', (e) => e.preventDefault());
        card.addEventListener('drop', (e) => {
            e.preventDefault();
            const fromIdx = parseInt(e.dataTransfer.getData('text/plain'));
            const toIdx = parseInt(card.dataset.index);
            if (fromIdx !== toIdx) {
                reorderSteps(routine, fromIdx, toIdx);
            }
        });

        execLog.appendChild(card);
    }
}

async function reorderSteps(routine, fromIdx, toIdx) {
    const steps = [...routine.steps];
    const [moved] = steps.splice(fromIdx, 1);
    steps.splice(toIdx, 0, moved);
    routine.steps = steps;
    await pywebview.api.update_routine_steps(routine.name, JSON.stringify(steps));
    showRoutineDetail(routine);
    showToast('Steps reordered', 'info');
}

async function runRoutine(name) {
    clearEmptyState();
    execLog.innerHTML = '';
    addRoutineHeader('Running: ' + name);

    const result = await pywebview.api.process_command('run ' + name);
    handleResult(result, 0, 0);
}

async function deleteRoutine(name) {
    await pywebview.api.delete_routine(name);
    showToast(`Deleted routine "${name}"`, 'info');
    loadRoutines();
    execLog.innerHTML = '<div class="empty-state"><div class="empty-icon">&#127908;</div><p>Tap the mic and speak a command</p></div>';
}

// ============================================================
// Toast Notifications
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

// ============================================================
// Event Listeners
// ============================================================

micBtn.addEventListener('click', () => {
    if (isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
});

sendBtn.addEventListener('click', () => {
    const text = textInput.value.trim();
    if (text) {
        textInput.value = '';
        processTextCommand(text);
    }
});

textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        const text = textInput.value.trim();
        if (text) {
            textInput.value = '';
            processTextCommand(text);
        }
    }
});

// ---- Init ----
window.addEventListener('pywebviewready', () => {
    loadRoutines();
});
