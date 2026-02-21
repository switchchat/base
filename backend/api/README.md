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
