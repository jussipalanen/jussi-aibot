# jussi-aibot

Minimal FastAPI app with a root route.

## Prerequisites

- Python 3.10+
- `pip`

## Setup

1. Create a virtual environment:

```bash
python3 -m venv .venv
```

2. Activate it:

```bash
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

Start the FastAPI development server:

```bash
uvicorn main:app --reload
```

Server will start at:

- `http://127.0.0.1:8000`

## Verify

- Root endpoint: `http://127.0.0.1:8000/`
- Swagger UI docs: `http://127.0.0.1:8000/docs`
- ReDoc docs: `http://127.0.0.1:8000/redoc`

Quick check from terminal:

```bash
curl http://127.0.0.1:8000/
```
