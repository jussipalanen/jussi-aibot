# Jussi AI-BOT: A FastAPI Service in Python

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

Or use the project launcher script (recommended):

```bash
./run.sh
```

Optional custom host/port:

```bash
HOST=127.0.0.1 PORT=8001 ./run.sh
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

## Resume Review API

The `/ai/review` endpoint accepts an uploaded resume file and returns a JSON review.

Supported file formats:
- PDF
- DOC, DOCS
- DOCX

Constraints:
- Finnish-only input (the review works only for Finnish resumes)
- Max upload size: 50MB

Rating scale (0-5):

| Stars | Rating |
| --- | --- |
| 5 | Erinomainen |
| 4 | Erittäin hyvä |
| 3 | Hyvä |
| 2 | Tyydyttävä |
| 1 | Heikko |
| 0 | Huono |

Example request:

```bash
curl -F "file=@/path/to/resume.pdf" http://127.0.0.1:8000/ai/review
```

Example response schema:

```json
{
	"rating_text": "Erittäin hyvä",
	"stars": 4,
	"summary": "...",
	"strengths": ["..."],
	"weaknesses": ["..."]
}
```

## Docker

Build the image:

```bash
docker build -t jussi-aibot .
```

Run locally (maps host 8000 to container 8080):

```bash
docker run --rm -p 8000:8080 jussi-aibot
```

Or with Compose:

```bash
docker compose up --build
```

Hot reload with Compose (auto-restart on code changes):

```bash
docker compose up --build
```

When you edit a `.py` file, Uvicorn reloads the app. Refresh the browser to see changes.

## Google Cloud Run

Deploy from source (Cloud Run builds the image and sets `PORT`):

```bash
gcloud run deploy jussi-aibot \
	--source . \
	--region YOUR_REGION \
	--allow-unauthenticated
```
