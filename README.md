# Jussi AI Bot

[![PR Checks](https://github.com/jussipalanen/jussi-aibot/actions/workflows/pr-checks.yml/badge.svg?branch=main)](https://github.com/jussipalanen/jussi-aibot/actions/workflows/pr-checks.yml)
![Version](https://img.shields.io/badge/version-2.0.0-blue)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.137-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)
![Security](https://img.shields.io/badge/security-bandit%20%7C%20pip--audit%20%7C%20trivy-success)
[![Deploy to Render](https://img.shields.io/badge/Deploy%20to-Render-46E3B7?logo=render&logoColor=white)](https://render.com/deploy?repo=https://github.com/jussipalanen/jussi-aibot)

A configurable AI agent platform built with FastAPI. It runs **chat agents** that call your APIs and rank results with RAG, **document reviews** (CVs, cover letters) and **code reviews** against rubrics — all defined in YAML, so a new platform needs a config file instead of new code.

- 🤖 **Agents from config** — prompt, model, tools, auth and RAG in `config/agents/*.yaml`
- 🛠️ **Native tool calling** — the model calls your REST endpoints directly
- 🔎 **RAG** — search results ranked by meaning with embeddings
- 📝 **Document reviews** — 0–5 stars, summary, strengths and weaknesses, per rubric and language
- 🧑‍💻 **Code reviews** — source code in most programming languages, several files at once, automatic language detection, and suggested code changes (current code → replacement)
- 🧠 **Many AI providers** — Gemini (API key or Vertex AI), Puter, OpenAI, Groq, OpenRouter, Mistral, Ollama
- 🔐 **Per-client API keys** — each client gets its own agents, origins and rate limit
- 📄 **PDF, DOC and DOCX** uploads, or plain text
- 🌐 **Review demos** — browser pages in Finnish and English: `/demo/review` for CVs and applications, `/demo/code-review` for code

## API documentation

The API documents itself. Open the root URL for a home page with links, or go straight to the docs:

| | Local | Production (Cloud Run) |
|---|---|---|
| Home page | [`localhost:8080/`](http://localhost:8080/) | [`/`](https://jussi-aibot-production-61766311353.europe-north1.run.app/) |
| **Review demo** (CV & application review) | [`localhost:8080/demo/review`](http://localhost:8080/demo/review) | [`/demo/review`](https://jussi-aibot-production-61766311353.europe-north1.run.app/demo/review) |
| **Code review demo** | [`localhost:8080/demo/code-review`](http://localhost:8080/demo/code-review) | [`/demo/code-review`](https://jussi-aibot-production-61766311353.europe-north1.run.app/demo/code-review) |
| **Swagger UI** (try requests in the browser) | [`localhost:8080/docs`](http://localhost:8080/docs) | [`/docs`](https://jussi-aibot-production-61766311353.europe-north1.run.app/docs) |
| ReDoc (readable reference) | [`localhost:8080/redoc`](http://localhost:8080/redoc) | [`/redoc`](https://jussi-aibot-production-61766311353.europe-north1.run.app/redoc) |
| OpenAPI JSON | [`localhost:8080/openapi.json`](http://localhost:8080/openapi.json) | [`/openapi.json`](https://jussi-aibot-production-61766311353.europe-north1.run.app/openapi.json) |

On Render the same paths work on your service URL, e.g. `https://<your-service>.onrender.com/docs`, `https://<your-service>.onrender.com/demo/review` and `https://<your-service>.onrender.com/demo/code-review`.

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

Send the document as `file` (PDF, DOC, DOCX) **or** as plain text in `text` (up to 100 000 characters):

```bash
curl -X POST http://localhost:8080/v1/review \
  -H "Authorization: Bearer $API_KEY" \
  -F "rubric=cover-letter-fi" \
  -F "text=Hei, haen backend-kehittäjän tehtävää..."
```

Optional form fields: `provider` (defaults to `REVIEW_PROVIDER`) and `model`.

### Code review

![Python](https://img.shields.io/badge/-Python-3776AB?logo=python&logoColor=white)
![JavaScript](https://img.shields.io/badge/-JavaScript-F7DF1E?logo=javascript&logoColor=black)
![TypeScript](https://img.shields.io/badge/-TypeScript-3178C6?logo=typescript&logoColor=white)
![Java](https://img.shields.io/badge/-Java-ED8B00?logo=openjdk&logoColor=white)
![Kotlin](https://img.shields.io/badge/-Kotlin-7F52FF?logo=kotlin&logoColor=white)
![C#](https://img.shields.io/badge/-C%23-512BD4?logo=dotnet&logoColor=white)
![C++](https://img.shields.io/badge/-C%2B%2B-00599C?logo=cplusplus&logoColor=white)
![Go](https://img.shields.io/badge/-Go-00ADD8?logo=go&logoColor=white)
![Rust](https://img.shields.io/badge/-Rust-000000?logo=rust&logoColor=white)
![PHP](https://img.shields.io/badge/-PHP-777BB4?logo=php&logoColor=white)
![Ruby](https://img.shields.io/badge/-Ruby-CC342D?logo=ruby&logoColor=white)
![Swift](https://img.shields.io/badge/-Swift-F05138?logo=swift&logoColor=white)
![SQL](https://img.shields.io/badge/-SQL-4479A1?logo=postgresql&logoColor=white)
![Shell](https://img.shields.io/badge/-Shell-4EAA25?logo=gnubash&logoColor=white)
![and more](https://img.shields.io/badge/-and%20more-lightgrey)

Use the `code-review-en` or `code-review-fi` rubric. Send up to 20 source files (repeat `file`) or paste the code in `text`; there is no minimum length. Line breaks and indentation are kept, and lines are numbered so findings point to them.

```bash
curl -X POST http://localhost:8080/v1/review \
  -H "Authorization: Bearer $API_KEY" \
  -F "rubric=code-review-en" \
  -F "file=@app/db.py" \
  -F "file=@app/routes.py"
```

The result has the usual fields plus:

- `languages` — the detected programming languages
- `production` — is the code ready for production: `ready`, `needs_work` or `not_ready`, with a reason
- `security` — the overall risk (`none`, `low`, `medium`, `high`, `critical`) and the vulnerabilities found, most severe first, with file, line and CWE id
- `suggestions` — what to replace and what to use instead

The service keeps the verdicts consistent: the risk is never lower than the most severe issue, and a `high` or `critical` risk always means `not_ready`. These are an AI's judgement, a quick first check rather than a replacement for a security audit or tools such as bandit, Semgrep or CodeQL.

```json
{
  "rubric": "code-review-en",
  "languages": ["Python"],
  "production": { "verdict": "not_ready", "reason": "The SQL injection must be fixed first." },
  "security": {
    "risk": "critical",
    "issues": [
      {
        "severity": "critical",
        "title": "SQL injection",
        "detail": "The query is built from user input. Use a parameterised query.",
        "file": "db.py",
        "line": 14,
        "cwe": "CWE-89"
      }
    ]
  },
  "stars": 3,
  "rating_text": "Good",
  "summary": "A small Flask API in Python. Clear structure, but one query is open to SQL injection...",
  "strengths": ["Small, focused functions", "Consistent naming"],
  "weaknesses": ["db.py line 14: SQL built from user input", "routes.py line 8: errors are swallowed"],
  "suggestions": [
    {
      "file": "db.py",
      "line": 14,
      "issue": "The query is built from user input, which allows SQL injection. Use a parameter.",
      "original": "cur.execute(f\"SELECT * FROM users WHERE name = '{name}'\")",
      "replacement": "cur.execute(\"SELECT * FROM users WHERE name = %s\", (name,))"
    }
  ]
}
```

Accepted files: `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.vue`, `.svelte`, `.java`, `.kt`, `.scala`, `.go`, `.rs`, `.c`, `.h`, `.cpp`, `.hpp`, `.cs`, `.php`, `.rb`, `.swift`, `.dart`, `.lua`, `.r`, `.sql`, `.sh`, `.ps1`, `.html`, `.css`, `.scss`, `.json`, `.yaml`, `.toml`, `.xml`, `.tf`, `Dockerfile`, `Makefile` and more. Files must be UTF-8 text. Up to 60 000 characters are reviewed per request.

**Language detection** (`aibot/review/languages.py`): a file's language comes from its name (`EXTENSION_LANGUAGES`); pasted code is matched against weighted regular expressions (`LANGUAGE_RULES`) for Python, JavaScript, TypeScript, Java, Kotlin, C#, C, C++, Go, Rust, PHP, Ruby, Swift, SQL, Shell, HTML, CSS, JSON, YAML and Dockerfile. The code review page runs the same rules in the browser, so the language shown while typing matches the result. To support a new language, add its extension and, optionally, a rule. Rules run on untrusted input, so keep them within one line (`[ \t]` rather than `\s`) and avoid nested repeats; `tests/test_code_review.py` checks that hostile input stays fast.

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
| `cover-letter-fi` | Finnish | Job applications |
| `cover-letter-en` | English | Job applications |
| `code-review-fi` | Finnish | Source code, with suggested changes |
| `code-review-en` | English | Source code, with suggested changes |

Add your own by copying one: set `id`, `language`, six `labels` (for 0–5 stars) and a `prompt` that contains `{document_text}` and asks for JSON with `stars`, `summary`, `strengths` and `weaknesses`. Name it `<type>-<language>` (e.g. `portfolio-fi`) so the demo page groups the language versions under one document type.

Set `input: code` for source code: the rubric then takes up to 20 source files instead of one document, keeps line breaks and indentation, numbers the lines (restarting for each `==> file <==`), detects the `languages`, and returns any `suggestions` the prompt asks for (`file`, `line`, `issue`, `original`, `replacement`). Code rubrics appear on the code review page, the others on the CV & application page. For example, a rubric that checks only security could copy `code-review-en.yaml` with a narrower prompt.

### Review demos (`/demo/review` and `/demo/code-review`)

Two browser pages for trying reviews, linked from the home page and from each other:

| Page | What it does |
|---|---|
| `/demo/review` — **CV & application review** | Choose CV or job application, then drag and drop a PDF, DOC or DOCX file or paste the text |
| `/demo/code-review` — **Code review** | Drop up to 20 source files, or paste code in a monospace box with no minimum length. Each file and the pasted code show their detected language. The result adds **Production readiness** and **Security risk** indicators (green, amber or red), the security issues with their CWE links, and suggested changes — the current code and its replacement, with a **Copy** button |

Both pages:

- **Suomi / English** switch for the page and the review language. The default comes from `?lang=fi` or `?lang=en`, the visitor's last choice, or the browser language.
- Show the stars, rating, summary, strengths and areas to improve.
- Share one template (`review.html`) and script (`review.js`); `config.page` picks the rubrics and texts.

Who can use it:

| Setting | Effect |
|---|---|
| No clients configured (local dev) | Works without a key |
| Keys configured, `DEMO_PUBLIC=false` (default) | The page has no key field, so visitors get "not available"; reviews need the API with a key |
| `DEMO_PUBLIC=true` | Works without a key from the page itself, for reviews only, limited by `DEMO_RATE_LIMIT` (default `10/day`) |
| `DEMO_ENABLED=false` | Both pages and the home page links removed |

With `DEMO_PUBLIC=true`, anyone can use your AI quota up to the demo limit. Set `FORWARDED_IP_DEPTH` so the limit applies per visitor rather than to everyone together (see **Rate limits**).

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
| No key, from the service's own pages, `DEMO_PUBLIC=true` | ✅ demo client: reviews only, `DEMO_RATE_LIMIT` |

Requests from the service's own pages (the review demo) are never rejected for their origin, so a valid key always works there.

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

   The Blueprint sets `DEMO_PUBLIC=true`, so visitors can use the review demo without a key (20 reviews a day in total until `FORWARDED_IP_DEPTH` is set). Set it to `false` to close the demo to visitors.

4. Click **Apply**. The first build takes a few minutes.

Prefer the dashboard? **New → Web Service → Docker**, set the health check path to `/health`, and add the variables from `render.yaml` under **Environment**.

### 3. Check it works

```bash
BASE=https://<your-service>.onrender.com
curl $BASE/health                                              # {"status":"ok"}
curl -H "Authorization: Bearer $AI_SECRET_KEY" $BASE/v1/providers   # gemini: configured true
```

Then open `$BASE/demo/review` and review a CV, or `$BASE/demo/code-review` and review some code, or open `$BASE/docs`, click **Authorize**, and try `POST /v1/agents/jussispace/chat`.

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
| `DEMO_ENABLED` | `true` | Serve the review demos at `/demo/review` and `/demo/code-review` |
| `DEMO_PUBLIC` | `false` | Allow the demo page without a key (reviews only) |
| `DEMO_RATE_LIMIT` | `10/day` | Limit for keyless demo reviews |

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
| `tests/test_demo.py` | Review demo page, plain-text reviews, demo access rules |
| `tests/test_code_review.py` | Code reviews: source files, several files, line numbers, suggestions, language detection, code review page |
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
  api/                     Routes: pages.py (/, /demo/review, /demo/code-review, /health), v1.py, legacy.py
  web/                     Home and demo page templates, CSS and JavaScript
  agents/                  Agent config schema, registry and the shared agent loop
  tools/http.py            Configurable HTTP tools and auth sessions
  knowledge/               RAG ranking, context sources, JSON-to-text rendering
  llm/                     Providers: gemini, openai_compat, puter, local
  review/                  Text and code extraction, language detection, rubrics, legacy Finnish review
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
