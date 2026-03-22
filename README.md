# Jussi AI-BOT: AI-Powered Resume Review Service

An intelligent FastAPI service that uses AI to analyze and review resumes. Upload your resume and get instant feedback with ratings, strengths, weaknesses, and actionable improvements.

## Key Features

- 🤖 **AI-Powered Analysis**: Advanced machine learning models review your resume
- ⭐ **Smart Ratings**: Get a 0-5 star rating with detailed explanations
- 💪 **Strengths & Weaknesses**: Identify what works and what needs improvement
- 🇫🇮 **Finnish Language Support**: Optimized for Finnish resumes and feedback
- 🚀 **Multiple AI Providers**: Choose between local models or cloud-based AI (Puter AI)
- 🔒 **Secure & Private**: Origin-based access control for frontend applications
- ⚡ **Rate Limited**: Fair usage policies to prevent abuse
- 📄 **Multiple Formats**: Supports PDF, DOC, and DOCX files
- 🏢 **JussiSpace Agent**: Conversational agent for searching properties and checking orders

## Environments

| Environment | Base URL |
| --- | --- |
| Local (Docker) | `http://localhost:8080` |
| Production (Cloud Run) | `https://jussi-aibot-production-61766311353.europe-north1.run.app` |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/jussipalanen/jussi-aibot.git
cd jussi-aibot

# 2. Start with Docker (recommended)
./dev up

# 3. Test the AI review
curl -F "file=@your-resume.pdf" http://localhost:8080/ai/review
```

Visit `http://localhost:8080/docs` for interactive API documentation (production: replace with production URL above).

## Prerequisites

- Python 3.12+ and `pip` (local dev)
- Docker + Docker Compose (Docker dev)

## Development

### Using `./dev` (recommended)

The `dev` script is a thin wrapper around Docker Compose with a local fallback:

| Command | Description |
|---|---|
| `./dev up` | Build image and start container in background |
| `./dev down` | Stop and remove containers |
| `./dev restart` | Restart running containers |
| `./dev logs` | Follow container logs (default: `api` service) |
| `./dev logs api` | Follow logs for a specific service |
| `./dev build` | Rebuild images without starting |
| `./dev ps` | Show container status |
| `./dev shell` | Open a shell inside the container |
| `./dev local` | Run directly with local venv (no Docker) |
| `./dev set-env [svc] [region]` | Push non-secret `.env` values to a Cloud Run service |
| `./dev help` | Show all commands |

### Local venv (no Docker)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./dev local
```

Optional custom host/port:

```bash
HOST=127.0.0.1 PORT=8001 ./dev local
```

Server will start at `http://127.0.0.1:8001`.

## Verify

After `./dev up`, the service is available at `http://localhost:8080`:

| URL | Description |
|---|---|
| `http://localhost:8080/` | Root endpoint |
| `http://localhost:8080/health` | Health check |
| `http://localhost:8080/docs` | Swagger UI (interactive) |
| `http://localhost:8080/redoc` | ReDoc documentation |

Quick health check:

```bash
curl http://localhost:8080/health
```

## AI-Powered Resume Review

The `/ai/review` endpoint uses advanced AI models to analyze your resume and provide comprehensive feedback.

### What You Get

📊 **Intelligent Analysis:**
- **Rating (0-5 stars)**: Overall assessment of your resume quality
- **Detailed Summary**: Comprehensive review in Finnish
- **Strengths**: What makes your resume stand out
- **Weaknesses**: Areas that need improvement
- **Actionable Feedback**: Specific suggestions to enhance your resume

### How It Works

Upload your resume, and the AI agent will:
1. Extract and analyze the content
2. Evaluate structure, clarity, and presentation
3. Assess experience and qualifications
4. Generate personalized feedback with ratings

### Supported Formats
- PDF
- DOC, DOCS, DOCX

### Usage Constraints

- 🇫🇮 **Language**: Optimized for Finnish resumes (Finnish feedback)
- 📦 **File Size**: Maximum 50MB per upload
- ⏱️ **Rate Limit**: 50 requests per day per IP (configurable)
- 🔑 **Authentication**: API key or origin-based access (see security section below)

**Provider Selection**: Choose between `default` (local TurkuNLP model) or `puter_ai` (cloud-based AI). Specify via `provider` parameter or use `DEFAULT_PROVIDER` environment variable.

**Puter-only mode (recommended for Cloud Run):** Disable local model downloads to avoid Hugging Face rate limits.

```bash
DEFAULT_PROVIDER=puter_ai
DISABLE_LOCAL_MODEL=true
```

### Rating Scale (0-5 stars)

| Stars | Rating |
| --- | --- |
| 5 | Erinomainen |
| 4 | Erittäin hyvä |
| 3 | Hyvä |
| 2 | Tyydyttävä |
| 1 | Heikko |
| 0 | Huono |

### Example Usage

**Using default provider (local AI model):**

```bash
curl -F "provider=default" -F "file=@/path/to/resume.pdf" http://127.0.0.1:8000/ai/review
```

**Using Puter AI provider (cloud-based):**

```bash
curl -F "provider=puter_ai" -F "file=@/path/to/resume.pdf" http://127.0.0.1:8000/ai/review
```

### AI Response Format

The API returns a comprehensive JSON response with AI-generated insights:

```json
{
	"provider": "puter_ai",
	"rating_text": "Erittäin hyvä",
	"stars": 4,
	"summary": "Comprehensive AI-generated analysis of your resume...",
	"provider_raw_output": "...",
	"strengths": [
		"Clear and professional presentation",
		"Strong technical skills highlighted",
		"Good work experience progression"
	],
	"weaknesses": [
		"Could benefit from quantifiable achievements",
		"Education section needs more detail"
	]
}
```

## AI Chat (`POST /ai/chat`)

A multi-handler conversational AI endpoint powered by Google Vertex AI (Gemini). Use the `handler` field to select which chatbot to invoke.

### Handlers

| Handler | Description |
| --- | --- |
| `jussispace` | Search properties and check order status in JussiSpace |
| `jussimatic-ai-cv-chat` | Q&A about Jussi Alanen's CV and professional background |

### API endpoint

```
POST /ai/chat
Content-Type: application/json
```

**Request body:**

| Field | Required | Description |
| --- | --- | --- |
| `handler` | Yes | Which chatbot to use (see table above) |
| `message` | Yes | User's message |
| `language` | No | `"fi"` or `"en"` — auto-detected when omitted |
| `history` | No | Previous messages for multi-turn chat |

**Single turn:**
```json
{
  "handler": "jussispace",
  "message": "Näytä vapaat asunnot Helsingissä",
  "language": "fi",
  "history": []
}
```

**Multi-turn (pass history from frontend):**
```json
{
  "handler": "jussispace",
  "message": "Entä Tampereella?",
  "language": "fi",
  "history": [
    {"role": "user", "content": "Näytä vapaat asunnot Helsingissä"},
    {"role": "assistant", "content": "Löysin 3 asuntoa Helsingissä..."}
  ]
}
```

**Response:**
```json
{ "reply": "Helsingissä on saatavilla seuraavat asunnot..." }
```

### Required environment variables

All of these must be set in `.env`:

| Variable | Description | Example |
| --- | --- | --- |
| `GCP_PROJECT` | GCP project ID | `my-gcp-project` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account key **inside the container** | `/secrets/gcp-key.json` |
| `GCP_KEY_PATH` | Path to service account key **on the host** (Docker mount) | `./secrets/gcp-key.json` |
| `AGENT_EMAIL` | JussiSpace agent login email | `agent@example.com` |
| `AGENT_PASSWORD` | JussiSpace agent password — **wrap in single quotes** if it contains `$` | `'p@$$word'` |
| `JUSSISPACE_API_URL` | JussiSpace backend base URL | `https://backend-lab-jussispace.jussialanen.com/api` |
| `JUSSIMATIC_CV_API_URL` | Jussimatic CV API URL (full URL with code param) | `https://backend-laravel.dev.jussialanen.com/api/resumes/current?owner=...&code=...` |

Optional (defaults shown):

| Variable | Default | Description |
| --- | --- | --- |
| `AGENT_VERTEX_MODEL` | `gemini-2.5-flash-lite` | Default Gemini model for all handlers |
| `AGENT_GCP_LOCATION` | `europe-north1` | Vertex AI region |
| `JUSSISPACE_VERTEX_MODEL` | _(falls back to `AGENT_VERTEX_MODEL`)_ | Model override for `jussispace` handler |
| `JUSSIMATIC_CV_VERTEX_MODEL` | _(falls back to `AGENT_VERTEX_MODEL`)_ | Model override for `jussimatic-ai-cv-chat` handler |

### Service account key setup

1. Download the service account JSON key from GCP Console
2. Place it in `secrets/` inside the project directory (gitignored):

```bash
mkdir -p secrets
cp /path/to/your-key.json secrets/gcp-key.json
```

3. Set in `.env`:

```bash
GCP_KEY_PATH=./secrets/gcp-key.json
GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp-key.json
```

### Adding a new handler

1. Add the handler name to `SUPPORTED_CHAT_HANDLERS` in `routes.py`
2. Create `agent/<handler>_agent.py` with an `ask(message, language, history)` function
3. Add an `elif` branch in the `/ai/chat` endpoint
4. Optionally add a `<HANDLER>_VERTEX_MODEL` env var for a model override

### File structure

```
agent/
├── tools.py                 — JussiSpace tool definitions
├── client.py                — HTTP client for JussiSpace backend (handles auth)
├── agent.py                 — JussiSpace agentic loop
└── jussimatic_cv_agent.py   — Jussimatic CV chat agent
```

## Docker

The project ships with a `Dockerfile` and `docker-compose.yml`. Use `./dev` for the common workflows:

```bash
./dev up        # build + start (detached)
./dev logs      # tail logs
./dev down      # stop + remove
./dev restart   # restart without rebuild
./dev build     # rebuild image only
./dev shell     # sh into the running container
```

The Compose setup mounts `.:/app` and runs Uvicorn with `--reload`, so any `.py` edit is picked up live without restarting the container.

**Optional ML dependencies** (local model, large image):

```bash
docker build --build-arg INCLUDE_ML_DEPS=1 -t jussi-aibot:ml .
```

**Environment variables** can be placed in a `.env` file in the project root — Compose loads it automatically (it is gitignored and excluded from the Docker build context):

```bash
cp .env.example .env   # if an example file exists
# or create manually:
echo "PUTER_API_KEY=your_key" >> .env
```

## Testing

### Run the test suite

```bash
# Install test dependencies (once)
pip install -r requirements.txt pytest httpx

# Run all tests
pytest

# Verbose output
pytest -v

# Run a specific file
pytest tests/test_services.py -v

# Run a specific test
pytest tests/test_api.py::test_health -v
```

### Test structure

| File | What it covers |
|---|---|
| `tests/test_origin_security.py` | Origin matching logic — exact match, prefix/suffix attacks, protocol mismatch, port mismatch |
| `tests/test_services.py` | Pure service functions — `normalize_whitespace`, `extract_json_from_text`, `map_rating_text`, `analyze_resume_heuristics`, `build_review_response`, `beautify_provider_output`, `_extract_puter_text` |
| `tests/test_api.py` | API endpoints via `TestClient` — health, routing, input validation, auth, provider flows (AI providers are mocked) |

### Shell integration tests

These require a running server and are intended for manual or staging use:

```bash
# Start the server first
./dev up

# Run origin security verification
bash tests/verify_origin_security.sh

# Run origin access tests
bash tests/test_origin_access.sh
```

### Configuration

`pytest.ini` sets sensible defaults — no extra flags needed for a standard run:

```ini
[pytest]
testpaths = tests
addopts = -v --tb=short
```

## Postman Collection

Generate a Postman Collection v2.1 directly from the live OpenAPI schema:

```bash
# Default output (postman/postman_collection.json, base URL http://localhost:8080)
./dev generate-postman

# Custom output file
./dev generate-postman postman/my_collection.json

# Custom output + base URL (e.g. staging)
./dev generate-postman postman/my_collection.json https://staging.example.com
```

Then import into Postman: **File → Import → select the generated `.json` file**.

The collection includes:
- All endpoints grouped by tag
- Form-data body pre-configured for `/ai/review` (file upload + provider field)
- A disabled `X-API-Key` header on every request — enable and fill in `{{API_KEY}}` when needed
- Collection-level variables: `base_url` and `API_KEY`

> The generator reads the FastAPI OpenAPI schema at build time — no running server required.

## CI / GitHub Actions

Every pull request to `main` or `dev-*` branches runs four automated checks:

| Job | Tool | What it checks |
|---|---|---|
| **Dependency Audit** | `pip-audit` | Known CVEs in `requirements.txt` and `requirements-ml.txt` |
| **SAST** | `bandit` | Insecure code patterns (medium+ severity), results uploaded to GitHub Security tab |
| **Container Scan** | `trivy` | HIGH/CRITICAL OS and package vulnerabilities in the built Docker image |
| **Tests** | `pytest` | Full test suite including unit and API tests |

SARIF results from bandit and trivy appear in **Security → Code scanning** in the GitHub repository.

### Dependabot

Dependabot is configured to open weekly PRs for:
- Python package updates (`requirements.txt`, `requirements-ml.txt`)
- GitHub Actions version updates

Dependency PRs are grouped to reduce noise — all Python packages arrive as a single PR.

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

## Security

The `/ai/chat` and `/ai/review` endpoints are protected by three layers. All three are enforced on every request.

### Layer 1 — Bearer token (`AI_SECRET_KEY`)

A shared secret known only to your backend servers. The AI API validates it on every call to `/ai/chat` and `/ai/review`.

**Why a bearer token and not `X-API-Key`?**
Any header sent from a browser is visible in dev tools. The bearer token is never sent by the browser — it lives on your backend server (jussimatic, jussispace) and is added only when the backend proxies the request to this API:

```
Browser → jussimatic backend (holds AI_SECRET_KEY) → AI API
```

The browser never sees the key.

**Setup:**

Generate a strong key:
```bash
openssl rand -hex 32
```

Store it in Secret Manager (Cloud Run):
```bash
echo -n "your-generated-key" | gcloud secrets create AI_SECRET_KEY --data-file=-
```

Set it in your calling backend as an environment variable, then include it in every request:
```http
Authorization: Bearer <your-key>
```

**Behaviour:**
- `AI_SECRET_KEY` not set → no auth required (local dev)
- `AI_SECRET_KEY` set → `Authorization: Bearer <key>` header required; wrong or missing key → `401`

---

### Layer 2 — Origin enforcement (`ALLOWED_ORIGINS`)

Even with the bearer token in place, the API also checks the `Origin` header server-side on every POST to `/ai/chat` and `/ai/review`.

**Why both?**
- The bearer token protects server-to-server calls
- The origin check ensures that even if the key leaked, it can only be used from your known domains

**Setup:**

Set `ALLOWED_ORIGINS` to a comma-separated list of your frontend domains:

```bash
# .env (local dev — leave empty to allow all)
ALLOWED_ORIGINS=

# Production
ALLOWED_ORIGINS=https://jussimatic.com,https://jussispace.com,http://localhost:3000
```

Update Cloud Run without rebuilding:
```bash
./dev set-env
# or directly:
gcloud run services update jussi-aibot-production \
  --region=europe-north1 \
  --update-env-vars=ALLOWED_ORIGINS=https://jussimatic.com,https://jussispace.com
```

**Behaviour:**
- `ALLOWED_ORIGINS` not set → no origin restriction (local dev)
- `ALLOWED_ORIGINS` set → `Origin` header must match; missing or unknown origin → `403`

---

### Layer 3 — CORS

The CORS middleware ensures browsers enforce the origin policy automatically before a request even reaches your handler. When `ALLOWED_ORIGINS` is set, only those origins receive the `Access-Control-Allow-Origin` response header — browsers block all others at the pre-flight stage.

| `ALLOWED_ORIGINS` | CORS behaviour |
| --- | --- |
| Not set (local dev) | `Access-Control-Allow-Origin: *` — all origins allowed |
| Set (production) | Only listed origins allowed; all others blocked by browser |

---

### Summary

| Scenario | Result |
|---|---|
| Backend from jussimatic/jussispace with correct bearer token + allowed origin | ✅ Allowed |
| Browser from allowed origin (CORS passes, no origin check triggered by browser) | ✅ Allowed |
| Any caller with wrong or missing bearer token | ❌ `401 Unauthorized` |
| Any caller with unlisted `Origin` header | ❌ `403 Forbidden` |
| Browser from an unlisted origin | ❌ Blocked by browser (CORS) + `403` from server |
| Rate limit exceeded | ❌ `429 Too Many Requests` |

> **Note:** The `Origin` header can be spoofed by non-browser HTTP clients. The bearer token is the primary protection against scripted abuse — the origin check is a second line of defence.

## Provider Selection

The `/ai/review` endpoint supports three providers via the multipart form field `provider`:

| Provider | Backend | Notes |
| --- | --- | --- |
| `default` | Local TurkuNLP GPT-3 Finnish model | Requires ML dependencies |
| `puter_ai` | Puter AI SDK (cloud) | Requires `PUTER_API_KEY` |
| `vertex_ai` | Google Vertex AI — Gemini | Requires GCP credentials |

**Default Provider Configuration:**

If `provider` is not specified in the request, the service uses the `DEFAULT_PROVIDER` environment variable:

```bash
DEFAULT_PROVIDER=vertex_ai  # default, puter_ai, or vertex_ai
```

If the selected provider is not configured or fails, the API returns an error — it does **not** fall back to another provider automatically.

**Vertex AI provider** (recommended):

```bash
GCP_PROJECT=your-gcp-project
GCP_LOCATION=europe-west1
VERTEX_MODEL=gemini-1.5-pro
VERTEX_PROMPT_MAX_CHARS=6000
```

Authenticate locally with:

```bash
gcloud auth application-default login
```

In Cloud Run, use Workload Identity or a service account with the `Vertex AI User` role — no key file needed.

**Puter AI provider:**

```bash
PUTER_API_KEY=your_puter_key
PUTER_MODEL=gpt-4o-mini
PUTER_DRIVER=openai-completion
PUTER_PROMPT_MAX_CHARS=6000
```

Latency tuning: lower `*_PROMPT_MAX_CHARS` to reduce input size (faster, less context). Set to `0` to disable truncation.

Postman setup for `/ai/review`:

- Method: `POST`
- Body: `form-data`
- Form fields:
	- `provider` = `default`, `puter_ai`, or `vertex_ai`
	- `file` = your resume file (type `File`)
- Header:
	- `X-API-Key: <your_key>` (required unless your origin is in `ALLOWED_ORIGINS`)

## Google Cloud Run

**Production URL:** `https://jussi-aibot-production-61766311353.europe-north1.run.app`

### Deploy via Cloud Build (recommended)

Commits to `main` trigger Cloud Build automatically (if a trigger is configured).
Manual build + deploy:

```bash
gcloud builds submit --config=cloudbuild.yaml
```

Override specific env vars at build time:

```bash
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_DEFAULT_PROVIDER=vertex_ai,_ALLOWED_ORIGINS=https://yourdomain.com
```

### Update env vars without rebuilding

Push non-secret values from your local `.env` to the running Cloud Run service:

```bash
./dev set-env                              # default: jussi-aibot-production, europe-north1
./dev set-env jussi-aibot-production europe-north1
```

Sensitive values (`AI_SECRET_KEY`, `AGENT_EMAIL`, `AGENT_PASSWORD`, `API_KEYS`, `PUTER_API_KEY`) are skipped by `set-env` — manage them via Secret Manager (see below).

### Deploy from source (one-off)

```bash
gcloud run deploy jussi-aibot-production \
  --source . \
  --region europe-north1 \
  --allow-unauthenticated
```

### Secrets (Secret Manager)

Sensitive values are injected as Secret Manager secrets in `cloudbuild.yaml`:

| Secret name | Used for |
| --- | --- |
| `AI_SECRET_KEY` | Bearer token for `/ai/chat` and `/ai/review` — never put in browser JS |
| `AGENT_EMAIL` | JussiSpace agent login email |
| `AGENT_PASSWORD` | JussiSpace agent password |
| `PUTER_API_KEY` | Puter AI key |

Create/update a secret:

```bash
echo -n "your-value" | gcloud secrets create AGENT_PASSWORD --data-file=-
# or update existing:
echo -n "your-value" | gcloud secrets versions add AGENT_PASSWORD --data-file=-
```

### Vertex AI in Cloud Run

Cloud Run uses the service account attached to the revision — no key file needed. The `GOOGLE_APPLICATION_CREDENTIALS` env var is **not required** in Cloud Run. Grant the service account the `Vertex AI User` role:

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:YOUR_SA@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/aiplatform.user
```

