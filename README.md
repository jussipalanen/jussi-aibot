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
- **Rate limit: 50 requests per day per IP address** (configurable via `DAILY_RATE_LIMIT` env var)
- **API key required** when `API_KEYS` is set (recommended for production)
- **Provider parameter optional in form-data:** `provider=default` or `provider=puter_ai` (uses `DEFAULT_PROVIDER` env var if not specified)

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
curl -F "provider=default" -F "file=@/path/to/resume.pdf" http://127.0.0.1:8000/ai/review
```

Example request (Puter AI provider):

```bash
curl -F "provider=puter_ai" -F "file=@/path/to/resume.pdf" http://127.0.0.1:8000/ai/review
```

Example response schema:

```json
{
	"provider": "puter_ai",
	"rating_text": "Erittäin hyvä",
	"stars": 4,
	"summary": "...",
	"provider_raw_output": "...",
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

## Rate Limiting

The API includes IP-based rate limiting to prevent abuse. Default: **50 requests per day per IP**.

**Configure the limit:**

Environment variable format: `"<number>/<period>"` where period is `second`, `minute`, `hour`, or `day`.

Examples:
- `DAILY_RATE_LIMIT="50/day"` - 50 requests per day (default)
- `DAILY_RATE_LIMIT="100/day"` - 100 requests per day
- `DAILY_RATE_LIMIT="10/hour"` - 10 requests per hour

**Local development (.env):**
```bash
export DAILY_RATE_LIMIT="100/day"
uvicorn main:app --reload
```

**Docker Compose:**
Update `docker-compose.yml`:
```yaml
environment:
  DAILY_RATE_LIMIT: "100/day"
```

**Cloud Run:**
```bash
gcloud run services update jussi-aibot-production \
  --set-env-vars=DAILY_RATE_LIMIT=100/day \
  --region=europe-north1
```

**Update default provider (Cloud Run):**
```bash
gcloud run services update jussi-aibot-production \
  --set-env-vars=DEFAULT_PROVIDER=puter_ai \
  --region=europe-north1
```

**Rate limit exceeded response:**
When a client exceeds the rate limit, they receive a `429 Too Many Requests` error with details about when they can retry.

## API Key Protection

To prevent abuse, you can require an API key for `/ai/review`.

**Enable API keys:**
Set `API_KEYS` to a comma-separated list of allowed keys.

**Hardened option (recommended for production):**
Store only hashes instead of raw keys using `API_KEY_HASHES`.

Example:
```bash
export API_KEYS="key1,key2,key3"
```

**Hash-based example (bash only):**
```bash
# Generate a strong key
API_KEY=$(openssl rand -base64 32 | tr -d '\n')

# Create SHA-256 hash of that key
API_KEY_HASH=$(echo -n "$API_KEY" | openssl dgst -sha256 | awk '{print $2}')

# Store only the hash on the server
export API_KEY_HASHES="$API_KEY_HASH"

# Use this key in requests
echo "X-API-Key: $API_KEY"
```

**Request header:**
Clients must send:
```
X-API-Key: key1
```

If `API_KEYS` is not set, the endpoint remains open (useful for local dev).

## Provider Selection (`default` vs `puter_ai`)

The `/ai/review` endpoint supports two providers via multipart form field `provider`:

- `default`: local TurkuNLP model inside this service
- `puter_ai`: Puter Python SDK (`ChatCompletion.create`)

**Default Provider Configuration:**

If the `provider` field is not specified in the request, the service uses the `DEFAULT_PROVIDER` environment variable (defaults to `default`):

```bash
DEFAULT_PROVIDER=default  # or puter_ai
```

If `provider=puter_ai` and Puter is not configured or fails, the API returns an error. It does **not** fall back to `default` automatically.

Required env vars for Puter provider:

```bash
PUTER_API_KEY=your_puter_key
PUTER_MODEL=gpt-4o-mini
PUTER_DRIVER=openai-completion
PUTER_PROMPT_MAX_CHARS=6000
```

Latency tuning for `puter_ai`:

- Lower `PUTER_PROMPT_MAX_CHARS` to reduce input size sent to Puter (faster, less context).
- Recommended range: `3000` to `6000` characters.
- Set `PUTER_PROMPT_MAX_CHARS=0` to disable truncation.

Postman setup for `/ai/review`:

- Method: `POST`
- Body: `form-data`
- Form fields:
	- `provider` = `default` or `puter_ai`
	- `file` = your resume file (type `File`)
- Header:
	- `X-API-Key: <your_key>` (if API key protection enabled)

## Google Cloud Run

Deploy from source (Cloud Run builds the image and sets `PORT`):

```bash
gcloud run deploy jussi-aibot \
	--source . \
	--region YOUR_REGION \
	--allow-unauthenticated
```
