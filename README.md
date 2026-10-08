# Jussi AI Bot

A configurable AI agent platform built with FastAPI. It runs **chat agents** that call your APIs and rank results with RAG, and **document reviews** (CVs, cover letters) against rubrics — all defined in YAML, so a new platform needs a config file instead of new code.

- 🤖 **Agents from config** — prompt, model, tools, auth and RAG in `config/agents/*.yaml`
- 🛠️ **Native tool calling** — the model calls your REST endpoints directly
- 🔎 **RAG** — search results ranked by meaning with embeddings
- 📝 **Document reviews** — 0–5 stars, summary, strengths and weaknesses, per rubric and language
- 🧠 **Many AI providers** — Gemini (API key or Vertex AI), Puter, OpenAI, Groq, OpenRouter, Mistral, Ollama
- 🔐 **Per-client API keys** — each client gets its own agents, origins and rate limit
- 📄 **PDF, DOC and DOCX** uploads

## API documentation

The API documents itself. Open the root URL for a home page with links, or go straight to the docs:

| | Local | Production (Cloud Run) |
|---|---|---|
| Home page | [`localhost:8080/`](http://localhost:8080/) | [`/`](https://jussi-aibot-production-61766311353.europe-north1.run.app/) |
| **Swagger UI** (try requests in the browser) | [`localhost:8080/docs`](http://localhost:8080/docs) | [`/docs`](https://jussi-aibot-production-61766311353.europe-north1.run.app/docs) |
| ReDoc (readable reference) | [`localhost:8080/redoc`](http://localhost:8080/redoc) | [`/redoc`](https://jussi-aibot-production-61766311353.europe-north1.run.app/redoc) |
| OpenAPI JSON | [`localhost:8080/openapi.json`](http://localhost:8080/openapi.json) | [`/openapi.json`](https://jussi-aibot-production-61766311353.europe-north1.run.app/openapi.json) |

On Render the same paths work on your service URL, e.g. `https://<your-service>.onrender.com/docs`.

In Swagger UI, click **Authorize** and enter your API key to call protected endpoints.

---

<details open>
<summary><b>🚀 Quick start</b></summary>

```bash
git clone https://github.com/jussipalanen/jussi-aibot.git
cd jussi-aibot
cp .env.example .env          # add GEMINI_API_KEY (free key: https://aistudio.google.com)
./dev up                      # build and start with Docker
```

Then open [`http://localhost:8080/docs`](http://localhost:8080/docs) and try `GET /v1/agents`.

Without Docker:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
./dev local                   # http://127.0.0.1:8000
```

With no clients configured, local development needs no API key.

</details>

<details>
<summary><b>📖 Using the API</b></summary>

All endpoints are listed with examples in [`/docs`](http://localhost:8080/docs). The main ones:

| Method | Path | What it does |
|---|---|---|
| `GET` | `/v1/agents` | Agents you may use |
| `POST` | `/v1/agents/{agent_id}/chat` | Chat with an agent |
| `GET` | `/v1/review/rubrics` | Review rubrics you may use |
| `POST` | `/v1/review` | Review a document against a rubric |
| `GET` | `/v1/providers` | Which AI providers have credentials (deployment check) |
| `GET` | `/health` | Health check (no AI calls) |
| `GET` | `/version` | App and runtime versions |
| `POST` | `/ai/chat`, `/ai/review` | Legacy endpoints, kept for existing frontends |

Send your key from servers as `Authorization: Bearer <key>`. Browser clients listed in the clients config are recognised by their origin instead (see **Security**).

### Chat

```bash
curl -X POST http://localhost:8080/v1/agents/jussispace/chat \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Entä Tampereella?",
    "language": "fi",
    "history": [
      {"role": "user", "content": "Näytä vapaat asunnot Helsingissä"},
      {"role": "assistant", "content": "Löysin 3 asuntoa Helsingissä..."}
    ]
  }'
```

```json
{ "agent": "jussispace", "reply": "Tampereella on saatavilla seuraavat asunnot..." }
```

- `language` is optional: one of the agent's languages (see `GET /v1/agents`); without it the agent answers in the user's language.
- `history` is optional: earlier messages, oldest first. The agent keeps the last 10 by default.

### Review

```bash
curl -X POST http://localhost:8080/v1/review \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@resume.pdf" \
  -F "rubric=cv-en"
```

```json
{
  "rubric": "cv-en",
  "language": "en",
  "provider": "gemini",
  "stars": 4,
  "rating_text": "Very good",
  "summary": "A clear, well-structured CV with strong technical experience...",
  "strengths": ["Clear structure", "Measurable achievements", "Relevant skills"],
  "weaknesses": ["Summary could be shorter", "Education dates missing"]
}
```

Optional form fields: `provider` (defaults to `REVIEW_PROVIDER`) and `model`.

### Errors

| Status | Meaning |
|---|---|
| `400` | Bad input: unsupported or unreadable file, unknown provider |
| `401` / `403` | Missing or wrong key / origin not allowed |
| `404` | Unknown agent or rubric, or not allowed for your client |
| `413` | File too large (`MAX_UPLOAD_MB`, default 50) |
| `429` | Rate limit exceeded; see the `Retry-After` header |
| `502` | The AI provider or a backend failed |
| `503` | A provider or data source is not configured |

</details>

<details>
<summary><b>🤖 Agents</b></summary>

Each file in `config/agents/` defines one agent. Values like `${NAME}` or `${NAME:-default}` are read from environment variables, so secrets stay out of the files.

| Agent | What it does |
|---|---|
| `jussispace` | Searches JussiSpace properties (with RAG) and checks orders |
| `jussimatic-ai-cv-chat` | Answers questions about a CV fetched from `JUSSIMATIC_CV_API_URL` |

### Add an agent

Create `config/agents/<id>.yaml` and restart. A minimal example:

```yaml
id: shop-helper
name: Shop helper
description: Answers product questions.
provider: gemini                 # gemini, groq, openai, openrouter, mistral, ollama, ...
model: gemini-2.5-flash-lite     # empty = provider default

language_instructions:
  fi: Vastaa aina suomeksi.
  en: Always respond in English.

system_prompt: |
  You help customers of Example Shop. Use the tools for real data; never invent products.

auth:
  shop:
    type: header                 # none | bearer | header | login
    header: X-API-Key
    value: ${SHOP_API_KEY}

tools:
  - name: search_products
    description: Search products by keyword.
    parameters:                  # JSON Schema; only these arguments are sent
      type: object
      properties:
        q: {type: string, description: Search words}
    http:
      method: GET
      url: https://shop.example.com/api/products
      auth: shop
    rag:                         # keep the 5 results closest to the user's message
      top_k: 5
      fields: [name, description, category]

  - name: get_product
    description: Get one product by ID.
    parameters:
      type: object
      properties:
        id: {type: integer}
      required: [id]
    http:
      url: https://shop.example.com/api/products/{id}   # {id} is filled and URL-encoded
      auth: shop
```

### Building blocks

| Key | Purpose |
|---|---|
| `tools[].http` | `method`, `url` (with `{param}` placeholders), `auth`, `headers`, `timeout`, `paginate` |
| `tools[].http.paginate` | Fetch every page (`page_param`, `limit_param`, `page_size`, `data_field`, `total_pages_field`, `max_pages`) |
| `tools[].rag` | Rank a list result by meaning: `data_field`, `top_k`, `fields` to embed |
| `auth.<name>.type: login` | POST `body` to `login_url`, read `token_field`, send as bearer token, log in again after a 401 |
| `context` | JSON from a URL rendered into the system prompt (e.g. a CV or FAQ), cached for `ttl` seconds; `asset_base_url` + `asset_fields` turn relative image paths into full URLs |
| `embedding` | `provider` and `model` for RAG (defaults to the chat provider, or Gemini) |
| `max_steps`, `history_limit`, `temperature` | Loop and generation limits |

The model only fills in argument values: hosts, paths and methods come from the config, and arguments not in the JSON Schema are dropped.

### How RAG works

When a tool has `rag`, its list result is ranked against the user's message with embeddings, and only the best `top_k` items reach the model. Each search ranks its own results, and embeddings are cached by content, so repeated items are not embedded again.

</details>

<details>
<summary><b>📝 Document review</b></summary>

### Rubrics

Each file in `config/rubrics/` is a rubric:

| Rubric | Language | For |
|---|---|---|
| `cv-fi` | Finnish | CVs (falls back to keyword scoring if the model returns no JSON) |
| `cv-en` | English | CVs |
| `cover-letter-en` | English | Cover letters |

Add your own by copying one: set `id`, `language`, six `labels` (for 0–5 stars) and a `prompt` that contains `{document_text}` and asks for JSON with `stars`, `summary`, `strengths` and `weaknesses`.

### Legacy `POST /ai/review`

Kept unchanged for existing frontends: Finnish CV review, form fields `file` and `provider` (`default`, `puter_ai` or `vertex_ai`; defaults to `DEFAULT_PROVIDER`). `vertex_ai` now runs on the Gemini provider, so it works with either a Gemini API key or Vertex AI.

| Stars | Rating |
|---|---|
| 5 | Erinomainen |
| 4 | Erittäin hyvä |
| 3 | Hyvä |
| 2 | Tyydyttävä |
| 1 | Heikko |
| 0 | Huono |

</details>

<details>
<summary><b>🧠 AI providers</b></summary>

| Provider | Tools | Embeddings | Setup |
|---|---|---|---|
| `gemini` | ✅ | ✅ | `GEMINI_API_KEY` **or** `GCP_PROJECT` (Vertex AI) |
| `groq`, `openai`, `openrouter`, `mistral` | ✅ | depends on service | `<NAME>_API_KEY` and `<NAME>_MODEL` |
| `ollama` | ✅ | ✅ | `OLLAMA_BASE_URL` and `OLLAMA_MODEL` |
| `openai_compat` | ✅ | depends on service | `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, `OPENAI_COMPAT_MODEL` |
| `puter` | ❌ | ❌ | `PUTER_API_KEY` (reviews only) |
| `local` | ❌ | ❌ | Finnish TurkuNLP model; build with `INCLUDE_ML_DEPS=1` and set `DISABLE_LOCAL_MODEL=false` |

Old names still work: `vertex_ai` → `gemini`, `puter_ai` → `puter`, `default` → `local`.

### Gemini: API key or Vertex AI

- **API key** (any host, including Render): create one in [Google AI Studio](https://aistudio.google.com/apikey) and set `GEMINI_API_KEY`. There is a free tier with rate limits. On the free tier Google may use requests to improve its products, so turn on billing for the key if you review real people's CVs.
- **Vertex AI** (Google Cloud): leave `GEMINI_API_KEY` empty and set `GCP_PROJECT` and `GCP_LOCATION`. On Cloud Run the service account is used automatically; elsewhere set `GOOGLE_APPLICATION_CREDENTIALS` to a key file.

If both are set, the API key is used.

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_MODEL` | `VERTEX_MODEL` or `gemini-2.5-flash-lite` | Default model for reviews |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Embeddings for RAG |
| `GEMINI_EMBED_BATCH_SIZE` | 100 (API key), 1 (Vertex AI) | Texts per embedding request |

</details>

<details>
<summary><b>🔐 Security, clients and rate limits</b></summary>

### Per-client keys (recommended)

Copy `config/clients.example.yaml` to `config/clients.yaml` (gitignored), or point `CLIENTS_FILE` at a file elsewhere:

```yaml
clients:
  - id: jussimatic-backend          # server-to-server
    key_sha256: <sha256 of the key>   # or: key: ${JUSSIMATIC_API_KEY}
    agents: [jussimatic-ai-cv-chat]
    rubrics: ["*"]
    rate_limit: 500/day

  - id: jussispace-web              # browser: no key, recognised by origin
    origins: [https://jussispace-production.lab.jussialanen.com]
    agents: [jussispace]
    rubrics: []
    rate_limit: 50/day
```

Hash a key with:

```bash
python -c "import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest())" "<key>"
```

How a request is matched:

| Request | Result |
|---|---|
| `Authorization: Bearer <key>` matches a client | ✅ that client — if it lists origins and an `Origin` header is sent, it must match |
| No key, `Origin` of a client without a key | ✅ that browser client |
| No key, `Origin` of a client that has a key | ❌ `401` |
| Wrong key | ❌ `401` |
| Unknown origin | ❌ `403` |

The `Origin` header can be faked by scripts, so browser-only clients are best for low-risk agents with tight rate limits. Keep keys on servers, never in browser JavaScript.

### Single-key setup

Without a clients file, `AI_SECRET_KEY` and `ALLOWED_ORIGINS` define one client, as before. Server-to-server calls with the key no longer need an `Origin` header. With neither set, the API is open (local development).

### CORS

Browsers may call from any origin listed for a client. Without any origins configured, CORS allows all origins (keys are still required when configured).

### Rate limits

Counted per client, per IP address, separately for chat and review. `DAILY_RATE_LIMIT` (default `50/day`) applies unless a client sets `rate_limit`. Formats: `50/day`, `10/hour`, `5/minute`. Limits are kept in memory and reset when the service restarts.

Behind a proxy (Render, Cloud Run) every request comes from the proxy's address, so all users of a client share one limit. To limit per user, set `FORWARDED_IP_DEPTH` to the position of the real client IP in `X-Forwarded-For`, counted from the right. To find it, set `LOG_FORWARDED_FOR=true`, make a request, read the `Client IP check` line in the logs, then remove the setting. Counting from the right matters: entries on the left can be sent by the caller.

</details>

<details>
<summary><b>☁️ Deploy on Render</b></summary>

The repository includes a Blueprint (`render.yaml`) for a free Docker web service.

### 1. Get a Gemini API key

Create one in [Google AI Studio](https://aistudio.google.com/apikey). No Google Cloud project or key file is needed.

### 2. Create the service

1. Merge the changes to `main` (the Blueprint deploys `main`).
2. In the [Render dashboard](https://dashboard.render.com): **New → Blueprint**, connect GitHub and pick `jussipalanen/jussi-aibot`.
3. Render reads `render.yaml` and asks for the secret values:

   | Variable | Value |
   |---|---|
   | `GEMINI_API_KEY` | Your key from step 1 |
   | `AGENT_EMAIL`, `AGENT_PASSWORD` | JussiSpace agent login |
   | `JUSSIMATIC_CV_API_URL` | CV API URL (full URL with its `code` parameter) |
   | `AI_SECRET_KEY` | A long random key: `openssl rand -hex 32` |
   | `ALLOWED_ORIGINS` | Your frontends, comma-separated, e.g. `https://jussimatic.com,https://jussispace.com` |
   | `PUTER_API_KEY` | Optional; only for `provider=puter_ai` |

4. Click **Apply**. The first build takes a few minutes.

Prefer the dashboard? **New → Web Service → Docker**, set the health check path to `/health`, and add the variables from `render.yaml` under **Environment**.

### 3. Check it works

```bash
BASE=https://<your-service>.onrender.com
curl $BASE/health                                              # {"status":"ok"}
curl -H "Authorization: Bearer $AI_SECRET_KEY" $BASE/v1/providers   # gemini: configured true
```

Then open `$BASE/docs`, click **Authorize**, and try `POST /v1/agents/jussispace/chat`.

### 4. Point your frontends at Render

Replace the Cloud Run URL with the Render URL in your frontends or their backends. The `/ai/chat` and `/ai/review` endpoints work as before.

### Optional

- **Per-client keys:** under **Environment → Secret Files** add `clients.yaml` (see **Security**), then set `CLIENTS_FILE=/etc/secrets/clients.yaml`.
- **Per-user rate limits:** see **Rate limits** above to set `FORWARDED_IP_DEPTH`.
- **Custom domain:** **Settings → Custom Domains**; add it to `ALLOWED_ORIGINS` if a browser calls it.

### Free plan notes

- The service sleeps after 15 minutes without traffic; the next request waits about a minute while it starts.
- 512 MB memory: keep `DISABLE_LOCAL_MODEL=true` and don't build with `INCLUDE_ML_DEPS=1`.
- Caches and rate-limit counters are in memory and reset when the service sleeps or redeploys.
- Gemini usage is billed (or free-tier limited) by Google, not Render.

</details>

<details>
<summary><b>☁️ Deploy on Google Cloud Run</b></summary>

**Production URL:** `https://jussi-aibot-production-61766311353.europe-north1.run.app`

Commits to `main` deploy through Cloud Build when a trigger is configured. Manually:

```bash
gcloud builds submit --config=cloudbuild.yaml
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_DEFAULT_PROVIDER=vertex_ai,_ALLOWED_ORIGINS=https://yourdomain.com
```

Gemini runs through Vertex AI with the service's own service account (`GCP_PROJECT` is set by `cloudbuild.yaml`). Grant it the **Vertex AI User** role:

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:YOUR_SA@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/aiplatform.user
```

Secrets come from Secret Manager (`JUSSI_AIBOT_*`). Create or update one:

```bash
echo -n "value" | gcloud secrets versions add JUSSI_AIBOT_AGENT_PASSWORD --data-file=-
```

Push non-secret `.env` values to the running service without rebuilding:

```bash
./dev set-env                                    # jussi-aibot-production, europe-north1
```

</details>

<details>
<summary><b>🐳 Local development and Docker</b></summary>

| Command | Description |
|---|---|
| `./dev up` | Build and start the container in the background |
| `./dev down` | Stop and remove containers |
| `./dev restart` | Restart containers |
| `./dev logs` | Follow logs |
| `./dev build` | Rebuild images |
| `./dev shell` | Shell inside the container |
| `./dev local` | Run with the local venv (no Docker) |
| `./dev test` / `./dev test-local` | Run tests in Docker / locally |
| `./dev generate-postman` | Regenerate the Postman collection |
| `./dev set-env [svc] [region]` | Push `.env` values to Cloud Run |

Compose mounts the project and runs Uvicorn with `--reload`, so code and config edits apply immediately. `.env` is loaded automatically and never copied into the image.

Vertex AI locally: put a service account key in `secrets/gcp-key.json` (gitignored) and set `GCP_KEY_PATH=./secrets/gcp-key.json` and `GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp-key.json` in `.env`. A `GEMINI_API_KEY` is simpler.

Local Finnish model (large image):

```bash
docker build --build-arg INCLUDE_ML_DEPS=1 -t jussi-aibot:ml .
```

</details>

<details>
<summary><b>⚙️ Environment variables</b></summary>

See `.env.example` for a commented template.

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME`, `APP_DESCRIPTION` | Jussi AI Bot | Shown on the home page and in the docs |
| `CONFIG_DIR` | `./config` | Folder with `agents/` and `rubrics/` |
| `GEMINI_API_KEY` | — | Gemini API key |
| `GCP_PROJECT`, `GCP_LOCATION` | —, `europe-north1` | Vertex AI (when no API key) |
| `AGENT_PROVIDER` | `gemini` | Default provider for the shipped agents |
| `AGENT_VERTEX_MODEL` | `gemini-2.5-flash-lite` | Default model for the shipped agents |
| `JUSSISPACE_VERTEX_MODEL`, `JUSSIMATIC_CV_VERTEX_MODEL` | — | Per-agent model overrides |
| `JUSSISPACE_API_URL`, `JUSSISPACE_FRONTEND_URL` | JussiSpace URLs | JussiSpace backend and links in answers |
| `AGENT_EMAIL`, `AGENT_PASSWORD` | — | JussiSpace agent login |
| `JUSSIMATIC_CV_API_URL` | — | CV JSON for the CV agent |
| `JUSSILOG_STORAGE_BASE_URL` | — | Base URL for relative CV image paths |
| `REVIEW_PROVIDER` | `gemini` | Default provider for `/v1/review` |
| `DEFAULT_PROVIDER` | `default` | Default provider for legacy `/ai/review` |
| `VERTEX_PROMPT_MAX_CHARS`, `PUTER_PROMPT_MAX_CHARS` | `6000` | Max document characters sent (0 = all) |
| `MAX_UPLOAD_MB` | `50` | Upload size limit |
| `PUTER_API_KEY`, `PUTER_MODEL`, `PUTER_DRIVER` | —, `gpt-4o-mini`, `openai-completion` | Puter AI |
| `<NAME>_API_KEY`, `<NAME>_MODEL`, `<NAME>_BASE_URL`, `<NAME>_EMBEDDING_MODEL` | — | OpenAI-compatible providers |
| `DISABLE_LOCAL_MODEL` | `false` | Turn off the local model |
| `CLIENTS_FILE` | `config/clients.yaml` if present | Per-client keys and limits |
| `AI_SECRET_KEY`, `ALLOWED_ORIGINS` | — | Single-client setup |
| `DAILY_RATE_LIMIT` | `50/day` | Default rate limit |
| `FORWARDED_IP_DEPTH` | `0` | Client IP position in `X-Forwarded-For` from the right |
| `LOG_FORWARDED_FOR` | `false` | Log forwarded headers to find the depth |

</details>

<details>
<summary><b>🧪 Testing and CI</b></summary>

```bash
pip install -r requirements.txt pytest httpx
pytest                                  # all tests; AI providers are faked, no keys needed
pytest tests/test_engine.py -v          # one file
```

| File | Covers |
|---|---|
| `tests/test_api.py` | Home page, health, legacy `/ai/chat` and `/ai/review` |
| `tests/test_v1.py` | `/v1` endpoints, rubrics, shipped config files |
| `tests/test_engine.py` | Agent loop, HTTP tools, pagination, login refresh, RAG, context sources |
| `tests/test_providers.py` | Gemini and OpenAI-compatible message conversion |
| `tests/test_security.py` | Keys, origins, clients file, CORS, rate limits |
| `tests/test_services.py` | Legacy Finnish review helpers |
| `tests/test_origin_security.py` | Origin matching edge cases |

`tests/verify_origin_security.sh` and `tests/test_origin_access.sh` run against a live server.

Every pull request to `main` or `dev-*` runs **pip-audit**, **bandit**, a **trivy** image scan and **pytest** (`.github/workflows/pr-checks.yml`). Dependabot opens weekly update PRs.

### Postman

```bash
./dev generate-postman                                   # postman/postman_collection.json
./dev generate-postman postman/staging.json https://staging.example.com
```

Import with **File → Import**. Set the `AI_SECRET_KEY` collection variable and enable the `Authorization` header on requests that need it.

</details>

<details>
<summary><b>🗂️ Project structure</b></summary>

```
main.py                    ASGI entry point (uvicorn main:app)
aibot/
  app.py                   App factory: routes, CORS, shared services
  settings.py              Environment settings
  configfile.py            YAML loading with ${ENV} substitution
  security.py              Clients, keys, origins, rate limits
  api/                     Routes: pages.py (/, /health), v1.py, legacy.py
  agents/                  Agent config schema, registry and the shared agent loop
  tools/http.py            Configurable HTTP tools and auth sessions
  knowledge/               RAG ranking, context sources, JSON-to-text rendering
  llm/                     Providers: gemini, openai_compat, puter, local
  review/                  Text extraction, rubrics, legacy Finnish review
config/
  agents/*.yaml            Agent definitions
  rubrics/*.yaml           Review rubrics
  clients.example.yaml     Template for per-client keys
render.yaml                Render Blueprint
cloudbuild.yaml            Cloud Build → Cloud Run
```

</details>

<details>
<summary><b>🔄 Upgrading from 1.x</b></summary>

- `/ai/chat` and `/ai/review` keep the same requests and responses.
- The Vertex AI SDK was replaced by `google-genai`. Cloud Run keeps working with its service account; any host can use `GEMINI_API_KEY` instead.
- RAG uses `gemini-embedding-001` (was `text-embedding-004`) and ranks every search separately. Before, the first search's results were reused for 30 minutes, even for other cities.
- With both `AI_SECRET_KEY` and `ALLOWED_ORIGINS` set, server calls with the key no longer need an `Origin` header.
- Agent prompts and tools moved from Python to `config/agents/*.yaml`.
- The app no longer fails to start without `GCP_PROJECT`; unconfigured providers answer `503`.

</details>
