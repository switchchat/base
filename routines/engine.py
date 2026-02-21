import json
import os
import time

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

DEMO_ROUTINES = [
    {
        "name": "morning prep",
        "steps": [
            {"tool": "get_weather", "args": {"location": "San Francisco"}},
            {"tool": "play_music", "args": {"song": "morning jazz playlist"}},
            {"tool": "set_timer", "args": {"minutes": 15}},
        ],
    },
    {
        "name": "evening wind-down",
        "steps": [
            {"tool": "play_music", "args": {"song": "lo-fi chill beats"}},
            {"tool": "set_alarm", "args": {"hour": 7, "minute": 0}},
            {"tool": "create_reminder", "args": {"title": "prepare lunch", "time": "7:30 AM"}},
        ],
    },
]


class RoutineEngine:
    def __init__(self):
        self.routines = {}
        os.makedirs(DATA_DIR, exist_ok=True)
        self._load_all()
        if not self.routines:
            for demo in DEMO_ROUTINES:
                self.create(demo["name"], demo["steps"])

    def _path(self, name):
        safe = name.lower().replace(" ", "_")
        return os.path.join(DATA_DIR, f"{safe}.json")

    def _load_all(self):
        for f in os.listdir(DATA_DIR):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(DATA_DIR, f)) as fh:
                        data = json.load(fh)
                        self.routines[data["name"]] = data
                except (json.JSONDecodeError, KeyError):
                    pass

    def create(self, name, steps):
        routine = {"name": name, "steps": steps}
        with open(self._path(name), "w") as f:
            json.dump(routine, f, indent=2)
        self.routines[name] = routine
        return routine

    def get(self, name):
        return self.routines.get(name)

    def list_all(self):
        return list(self.routines.values())

    def delete(self, name):
        if name in self.routines:
            path = self._path(name)
            if os.path.exists(path):
                os.remove(path)
            del self.routines[name]
            return True
        return False

    def update_steps(self, name, steps):
        if name not in self.routines:
            return None
        self.routines[name]["steps"] = steps
        with open(self._path(name), "w") as f:
            json.dump(self.routines[name], f, indent=2)
        return self.routines[name]

    def execute(self, name, execute_fn, progress_callback=None):
        routine = self.get(name)
        if not routine:
            return {"error": f"Routine '{name}' not found"}
        results = []
        steps = routine["steps"]
        for i, step in enumerate(steps):
            if progress_callback:
                progress_callback(i + 1, len(steps), "running", None)
            start = time.time()
            try:
                result = execute_fn(step["tool"], step["args"])
                elapsed = (time.time() - start) * 1000
                entry = {"step": i + 1, "tool": step["tool"], "args": step["args"],
                         "result": result, "time_ms": elapsed, "status": "success"}
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                entry = {"step": i + 1, "tool": step["tool"], "args": step["args"],
                         "error": str(e), "time_ms": elapsed, "status": "error"}
            results.append(entry)
            if progress_callback:
                progress_callback(i + 1, len(steps), entry["status"], entry)
        return {"routine": name, "results": results}

    def fuzzy_match(self, query):
        query_lower = query.lower().strip()
        for name in self.routines:
            if query_lower == name.lower():
                return name
        for name in self.routines:
            if query_lower in name.lower() or name.lower() in query_lower:
                return name
        query_words = set(query_lower.split())
        best_name = None
        best_overlap = 0
        for name in self.routines:
            name_words = set(name.lower().split())
            overlap = len(query_words & name_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_name = name
        return best_name if best_overlap > 0 else None
