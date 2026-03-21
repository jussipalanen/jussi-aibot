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

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/jussipalanen/jussi-aibot.git
cd jussi-aibot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Start the server
./run.sh

# 3. Test the AI review (upload your resume)
curl -F "file=@your-resume.pdf" http://127.0.0.1:8000/ai/review
```

Visit `http://127.0.0.1:8000/docs` for interactive API documentation.

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

Test the API endpoints:

- Root endpoint: `http://127.0.0.1:8000/`
- **Swagger UI docs (Interactive API)**: `http://127.0.0.1:8000/docs` 
- ReDoc docs: `http://127.0.0.1:8000/redoc`
- Health check: `http://127.0.0.1:8000/health`

Quick health check from terminal:

```bash
curl http://127.0.0.1:8000/
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

## JussiSpace Agent

A conversational AI agent powered by Google Vertex AI (Gemini) that lets users search properties and check order status via natural language.

### How It Works

The agent module (`agent/`) defines tools that map to JussiSpace backend endpoints. Gemini decides which tool to call based on the user's message and handles multi-step tool calls automatically.

**Available tools:**

| Tool | Description |
| --- | --- |
| `search_properties` | Search apartments/offices by city, type, status |
| `get_property` | Get full details of a property by ID |
| `get_order_status` | Get status and details of a specific order |
| `list_orders` | List orders filtered by user or status |

### Setup

1. Install the Vertex AI SDK (already included in `requirements.txt`):

```bash
pip install -r requirements.txt
```

2. Authenticate with Google Cloud:

```bash
gcloud auth application-default login
```

3. Set the required environment variables in your `.env`:

```bash
JUSSISPACE_API_URL=https://your-api.com/api
AGENT_EMAIL=agent@jussispace.internal
AGENT_PASSWORD=your-agent-password
GCP_PROJECT=your-gcp-project
GCP_LOCATION=europe-west1
```

### Usage

```python
from agent.agent import ask

# Language auto-detected from the message
reply = ask("Show me available apartments in Helsinki")

# Force Finnish response
reply = ask("Näytä vapaat asunnot Helsingissä", language="fi")

# Force English response
reply = ask("Mikä on tilauksen 42 status?", language="en")
```

The `language` parameter is optional — `"fi"` for Finnish, `"en"` for English. When omitted, the agent mirrors the language of the user's message.

### File Structure

```
agent/
├── tools.py    — Gemini FunctionDeclaration definitions
├── client.py   — HTTP client for the JussiSpace backend (handles auth)
└── agent.py    — Vertex AI agentic loop
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

## Origin-Based Access Control (Frontend Security)

**Problem:** When frontend applications (browsers) call the API with `X-API-Key` header, the key is visible in browser developer tools, exposing it to potential attackers.

**Solution:** Configure allowed origins so frontend clients from trusted domains can access the API without sending the API key header.

### Configuration

Set `ALLOWED_ORIGINS` environment variable with comma-separated list of allowed frontend origins:

```bash
export ALLOWED_ORIGINS="http://localhost:3000,https://yourdomain.com,https://app.yourdomain.com"
```

**Local development (.env):**
```bash
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

**Docker Compose:**
Update `docker-compose.yml`:
```yaml
environment:
  ALLOWED_ORIGINS: "https://yourdomain.com,https://app.yourdomain.com"
```

**Cloud Run:**
```bash
gcloud run services update jussi-aibot \
  --set-env-vars=ALLOWED_ORIGINS="https://yourdomain.com,https://app.yourdomain.com" \
  --region=YOUR_REGION
```

### How It Works

1. **Browser requests from allowed origins**: Automatically allowed without `X-API-Key` header
2. **Backend/server requests**: Must include valid `X-API-Key` header
3. **Requests from non-allowed origins**: Must include valid `X-API-Key` header

The service checks the `Origin` or `Referer` header of incoming requests. If it matches an entry in `ALLOWED_ORIGINS`, the API key check is bypassed.

### Security Notes

- **Origin header cannot be spoofed by browsers** due to browser security policies
- **Non-browser clients** (curl, Postman, backend services) can spoof the Origin header, so they should still use API keys
- **Rate limiting still applies** to all requests regardless of origin
- **CORS is automatically configured** for allowed origins when `ALLOWED_ORIGINS` is set
- Leave `ALLOWED_ORIGINS` empty to require API key for all requests (maximum security)

### Example Requests

**From allowed frontend (no API key needed):**
```javascript
// Browser automatically sends Origin header
fetch('https://your-api.com/ai/review', {
  method: 'POST',
  body: formData
})
```

**From backend service (API key required):**
```bash
curl -H "X-API-Key: your-secret-key" \
  -F "file=@resume.pdf" \
  https://your-api.com/ai/review
```

**Testing with curl (simulating browser origin):**
```bash
# This works only for allowed origins
curl -H "Origin: http://localhost:3000" \
  -F "file=@resume.pdf" \
  http://127.0.0.1:8000/ai/review
```

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

Deploy from source (Cloud Run builds the image and sets `PORT`):

```bash
gcloud run deploy jussi-aibot \
	--source . \
	--region YOUR_REGION \
	--allow-unauthenticated
```
