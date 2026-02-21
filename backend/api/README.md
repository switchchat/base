# Python API (FastAPI)

This folder contains a minimal FastAPI-based HTTP API scaffold.

Quick start:

1. Create a virtualenv and install dependencies:

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

2. Run the server locally:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Endpoints:
- `GET /health` - health check
- `POST /predict` - example prediction endpoint (placeholder)

Session workflow:
- `POST /session/start` - starts a backend session
- `GET /session/status` - returns current session state and called functions
- `POST /session/end` - ends the current session and returns called API functions

Session rules:
- Application endpoints only work when a session is active.
- If session is inactive, endpoints return HTTP `409` with detail: `Session is inactive. Call /session/start first.`

Common application endpoints:
- `GET /info`
- `GET /models`
- `POST /predict`
- `POST /embed`
- `POST /predict/trigger` (no body, button-friendly)
- `POST /embed/trigger` (no body, button-friendly)
