import sys
sys.path.insert(0, "cactus/python/src")

import base64
import json
import os
import re
import struct
import tempfile
import threading
import time
import wave

import numpy as np
import sounddevice as sd

from cactus import cactus_init, cactus_transcribe, cactus_destroy
from main import generate_hybrid
from tools.registry import ACTION_TOOLS, execute_tool
from routines.engine import RoutineEngine

WHISPER_PATH = "cactus/weights/whisper-small"
WHISPER_PROMPT = "<|startoftranscript|><|en|><|transcribe|><|notimestamps|>"
SAMPLE_RATE = 16000


class Api:
    def __init__(self):
        self._window = None
        self._lock = threading.Lock()
        self._whisper = None
        self._engine = RoutineEngine()
        self._recording = False
        self._recorded_frames = []

    def set_window(self, window):
        self._window = window

    def _get_whisper(self):
        if self._whisper is None:
            self._whisper = cactus_init(WHISPER_PATH)
        return self._whisper

    # ------------------------------------------------------------------
    # Native audio recording (Python-side, bypasses browser permissions)
    # ------------------------------------------------------------------
    def start_recording(self):
        if self._recording:
            return {"status": "already_recording"}
        self._recorded_frames = []

        def callback(indata, frames, time_info, status):
            if self._recording:
                self._recorded_frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='int16',
            callback=callback,
        )
        self._stream.start()
        self._recording = True
        return {"status": "recording"}

    def stop_recording(self):
        if not self._recording:
            return {"error": "Not recording", "text": "", "time_ms": 0}

        self._recording = False
        self._stream.stop()
        self._stream.close()

        if not self._recorded_frames:
            return {"error": "No audio captured", "text": "", "time_ms": 0}

        audio_data = np.concatenate(self._recorded_frames, axis=0)

        # Audio diagnostics
        duration_s = len(audio_data) / SAMPLE_RATE
        rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
        print(f"[audio] duration={duration_s:.1f}s, rms={rms:.0f}, frames={len(self._recorded_frames)}")

        if duration_s < 0.5:
            return {"error": "Recording too short", "text": "", "time_ms": 0}

        # Write WAV to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            with wave.open(tmp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # int16
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio_data.tobytes())

        # Transcribe
        start = time.time()
        try:
            with self._lock:
                whisper = self._get_whisper()
                raw = cactus_transcribe(whisper, tmp_path, prompt=WHISPER_PROMPT)
            elapsed = (time.time() - start) * 1000
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            text = parsed.get("response", "") if isinstance(parsed, dict) else str(parsed)
            text = text.strip()
            print(f"[audio] transcription: {text!r}")

            # Filter out Whisper hallucinations
            hallucinations = {"[blank_audio]", "[blank audio]", "(blank audio)", "you",
                              "thank you", "thanks", "bye", "okay", ""}
            if text.lower().strip(".,!? ") in hallucinations:
                return {"error": "No speech detected", "text": "", "time_ms": round(elapsed, 1)}

            result = {"text": text, "time_ms": round(elapsed, 1)}
        except Exception as e:
            result = {"error": str(e), "text": "", "time_ms": 0}
        finally:
            os.unlink(tmp_path)

        return result

    # ------------------------------------------------------------------
    # Voice transcription (base64 fallback — kept for compatibility)
    # ------------------------------------------------------------------
    def transcribe_base64(self, audio_b64):
        tmp_path = None
        try:
            audio_bytes = base64.b64decode(audio_b64)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            start = time.time()
            with self._lock:
                whisper = self._get_whisper()
                raw = cactus_transcribe(whisper, tmp_path, prompt=WHISPER_PROMPT)
            elapsed = (time.time() - start) * 1000
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            text = parsed.get("response", "") if isinstance(parsed, dict) else str(parsed)
            return {"text": text.strip(), "time_ms": round(elapsed, 1)}
        except Exception as e:
            return {"error": str(e), "text": "", "time_ms": 0}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ------------------------------------------------------------------
    # Command processing — the core intent router
    # ------------------------------------------------------------------
    def process_command(self, text):
        if not text or not text.strip():
            return {"type": "error", "message": "Empty command"}

        text = text.strip()

        # Check for routine creation
        create_match = None
        routine_name = None
        steps_text = None

        # Pattern 1: "create routine called X: steps..."
        create_match = re.match(
            r"(?:create|make|add|set up|build)\s+(?:a\s+)?routine\s+(?:called|named)\s+(.+?)\s*:\s*(.+)",
            text, re.IGNORECASE
        )
        if create_match:
            routine_name = create_match.group(1).strip()
            steps_text = create_match.group(2).strip()

        # Pattern 2: "create routine called X to/that/which steps..."
        if not routine_name:
            create_match = re.match(
                r"(?:create|make|add|set up|build)\s+(?:a\s+)?routine\s+(?:called|named)\s+(.+?)\s+(?:to|that|which|with)\s+(.+)",
                text, re.IGNORECASE
            )
            if create_match:
                routine_name = create_match.group(1).strip()
                steps_text = create_match.group(2).strip()

        # Pattern 3: "create a X routine, step1, step2..."  or  "create a X routine to step1 and step2"
        _ARTICLES = {"a", "an", "the", "my"}
        if not routine_name:
            create_match = re.match(
                r"(?:create|make|add|set up|build)\s+(?:a\s+)?(.+?)\s+routine\s*[,:]\s*(.+)",
                text, re.IGNORECASE
            )
            if create_match and create_match.group(1).strip().lower() not in _ARTICLES:
                routine_name = create_match.group(1).strip()
                steps_text = create_match.group(2).strip()

        if not routine_name:
            create_match = re.match(
                r"(?:create|make|add|set up|build)\s+(?:a\s+)?(.+?)\s+routine\s+(?:to|that|which|with)\s+(.+)",
                text, re.IGNORECASE
            )
            if create_match and create_match.group(1).strip().lower() not in _ARTICLES:
                routine_name = create_match.group(1).strip()
                steps_text = create_match.group(2).strip()

        # Pattern 4: "create a routine, steps" or "create a routine to steps" (auto-name)
        if not routine_name:
            # Try comma/colon/period delimiter
            create_match = re.match(
                r"(?:create|make|add|set up|build)\s+(?:a\s+)?routine\s*[,:.]\s*(.+)",
                text, re.IGNORECASE
            )
            if not create_match:
                # Try conjunction word delimiter
                create_match = re.match(
                    r"(?:create|make|add|set up|build)\s+(?:a\s+)?routine\s+(?:to|that|which|with)\s+(.+)",
                    text, re.IGNORECASE
                )
            if create_match:
                routine_name = "my routine"
                steps_text = create_match.group(1).strip()

        if routine_name and steps_text:
            return self._create_routine(routine_name, steps_text)

        # Check for routine execution: "run/execute/start X"
        run_match = re.match(
            r"(?:run|execute|start|do|trigger|launch)\s+(?:the\s+)?(?:routine\s+)?(.+)",
            text, re.IGNORECASE
        )
        if run_match:
            routine_name = self._engine.fuzzy_match(run_match.group(1).strip())
            if routine_name:
                return self._execute_routine(routine_name)

        # Direct command — run through generate_hybrid
        return self._direct_command(text)

    def _create_routine(self, name, steps_text):
        # Use cloud (Gemini) for the full steps text — it handles multi-tool
        # intent parsing much better than the local 270M model
        from main import generate_cloud
        print(f"[routine] Creating routine '{name}' from: {steps_text!r}")
        messages = [{"role": "user", "content": steps_text}]
        try:
            result = generate_cloud(messages, ACTION_TOOLS)
            print(f"[routine] Cloud result: {result}")
        except Exception as e:
            print(f"[routine] Cloud error: {e}")
            return {"type": "error", "message": f"Cloud API error: {e}"}

        steps = []
        for call in result.get("function_calls", []):
            steps.append({"tool": call["name"], "args": call.get("arguments", {})})

        if not steps:
            return {"type": "error", "message": "Could not parse any steps from your description"}

        routine = self._engine.create(name, steps)
        return {
            "type": "routine_created",
            "routine": routine,
            "message": f"Created routine '{name}' with {len(steps)} steps",
        }

    def _execute_routine(self, name):
        def progress(step, total, status, result):
            if self._window:
                self._window.evaluate_js(
                    f"window.onRoutineProgress && window.onRoutineProgress({step}, {total}, '{status}', {json.dumps(result)})"
                )

        result = self._engine.execute(name, execute_tool, progress_callback=progress)
        return {"type": "routine_executed", "result": result}

    @staticmethod
    def _is_actionable(text):
        """Reject very short or clearly non-command inputs."""
        words = [w for w in text.lower().split() if len(w) >= 2]
        if len(words) < 2:
            return False
        action_keywords = {
            "weather", "alarm", "timer", "play", "music", "send", "message",
            "remind", "reminder", "search", "contact", "call", "set", "get",
            "check", "find", "tell", "text", "whats", "what's",
        }
        return bool(set(words) & action_keywords)

    def _direct_command(self, text):
        if not self._is_actionable(text):
            return {"type": "no_action", "message": f"I didn't recognize a command in \"{text}\". Try something like \"What's the weather in Tokyo\" or \"Set a timer for 5 minutes\"."}

        messages = [{"role": "user", "content": text}]
        start = time.time()
        with self._lock:
            result = generate_hybrid(messages, ACTION_TOOLS)
        inference_ms = (time.time() - start) * 1000

        calls = result.get("function_calls", [])
        if not calls:
            return {"type": "no_action", "message": "Could not determine an action for that command"}

        exec_results = []
        for call in calls:
            exec_start = time.time()
            exec_result = execute_tool(call["name"], call.get("arguments", {}))
            exec_ms = (time.time() - exec_start) * 1000
            exec_results.append({
                "tool": call["name"],
                "args": call.get("arguments", {}),
                "result": exec_result,
                "time_ms": round(exec_ms, 1),
            })

        return {
            "type": "direct",
            "results": exec_results,
            "inference_ms": round(inference_ms, 1),
            "source": result.get("source", "on-device"),
        }

    # ------------------------------------------------------------------
    # Direct routine execution (called by Run button, bypasses text parser)
    # ------------------------------------------------------------------
    def run_routine(self, name):
        routine = self._engine.get(name)
        if not routine:
            name = self._engine.fuzzy_match(name)
            if not name:
                return {"type": "error", "message": f"Routine not found"}
        return self._execute_routine(name)

    # ------------------------------------------------------------------
    # Routine CRUD for frontend
    # ------------------------------------------------------------------
    def get_routines(self):
        return self._engine.list_all()

    def save_routine(self, name, steps_json):
        steps = json.loads(steps_json) if isinstance(steps_json, str) else steps_json
        return self._engine.create(name, steps)

    def delete_routine(self, name):
        return self._engine.delete(name)

    def update_routine_steps(self, name, steps_json):
        steps = json.loads(steps_json) if isinstance(steps_json, str) else steps_json
        return self._engine.update_steps(name, steps)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self):
        if self._whisper:
            cactus_destroy(self._whisper)
            self._whisper = None
