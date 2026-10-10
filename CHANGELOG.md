# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

---

## [2.1.0] - 2026-10-10

Code review: the AI reviews source code in most programming languages, says whether it is ready for production and how risky it is, and suggests changes that can be applied with one click.

### Added

- Code review for source code in most programming languages: `code-review-en` and `code-review-fi` rubrics
- `input: code` rubric option: takes up to 20 source files at once, keeps line breaks and indentation, and numbers the lines per file
- `suggestions` in `POST /v1/review` results: the file, line, issue, current code and its replacement
- Programming language detection (`aibot/review/languages.py`): by file name, then by content; `languages` in code review results
- Code review page: line numbers in the code box, and **Apply** / **Apply all** buttons that write suggested changes into the pasted code (undo with Ctrl+Z)
- Production readiness (`production`: `ready`, `needs_work` or `not_ready` with a reason) and security risk (`security`: overall risk and vulnerabilities with severity, file, line and CWE id) in code review results, shown as indicators on the code review page. A high or critical risk always means not ready
- Code review demo at `/demo/code-review`, linked from the home page and the CV review page: up to 20 source files with their detected languages, pasted code with live language detection and no minimum length, and suggested changes with a **Copy** button
- Badges in the README

### Changed

- The review demo has no API key field and does not show the AI provider; server error details are hidden on the page
- `POST /v1/review` accepts the `file` field more than once (code rubrics only)
- `/demo/review` is for CVs and job applications only; code review has its own page at `/demo/code-review`
- The home page links to both demos

### Fixed

- Spacing between the demo cards on the home page

---

## [2.0.0] - 2026-10-08

The service is now a configurable platform: agents, tools, RAG and review rubrics are defined in YAML instead of Python. The `/ai/chat` and `/ai/review` endpoints keep their requests and responses.

### Added

- `/v1` API: `GET /v1/agents`, `POST /v1/agents/{agent_id}/chat`, `GET /v1/review/rubrics`, `POST /v1/review`, `GET /v1/providers`
- Agent definitions in `config/agents/*.yaml`: prompt, provider, model, languages, HTTP tools, auth profiles, pagination, RAG and context sources, with `${ENV}` substitution
- One shared agent loop with native tool calling, replacing the hand-written JSON tool protocol
- Provider layer (`aibot/llm`): Gemini via `google-genai` (API key or Vertex AI), OpenAI-compatible services (OpenAI, Groq, OpenRouter, Mistral, Ollama, custom), Puter and the local model
- Review rubrics in `config/rubrics/*.yaml`: `cv-fi`, `cv-en`, `cover-letter-en`
- Per-client API keys, origins, allowed agents and rubrics, and rate limits (`config/clients.yaml` or `CLIENTS_FILE`)
- `FORWARDED_IP_DEPTH` and `LOG_FORWARDED_FOR` for per-user rate limits behind a proxy
- Home page at `/` with links to `/docs`, `/redoc` and `/openapi.json`; JSON when requested with `Accept: application/json`
- Bearer auth in the OpenAPI schema, so `/docs` has an **Authorize** button
- Render Blueprint (`render.yaml`) and Render setup instructions
- CV & application review demo at `/demo/review`, linked from the home page: drag-and-drop upload or pasted text, CV or job application, results with stars, summary, strengths and areas to improve
- Finnish and English for the demo page and the reviews, with a Suomi / English switch
- `cover-letter-fi` rubric for Finnish job applications
- `POST /v1/review` accepts plain text in `text` instead of a file
- `DEMO_ENABLED`, `DEMO_PUBLIC` and `DEMO_RATE_LIMIT` settings; requests from the service's own pages are never rejected for their origin

### Changed

- `google-cloud-aiplatform` replaced by `google-genai`; Cloud Run keeps using Vertex AI with its service account, and any host can use `GEMINI_API_KEY`
- RAG embeddings use `gemini-embedding-001` and are cached by content
- AI and backend calls are asynchronous, and file text extraction runs in a worker thread, so one slow request no longer blocks the server
- Agents and providers start on first use; a missing `GCP_PROJECT` no longer stops the app from starting (unconfigured providers answer `503`)
- `slowapi` replaced by `limits`; rate limits are counted per client, IP and endpoint group
- Code moved into the `aibot` package; `routes.py`, `services.py`, `model.py` and `agent/` removed
- README reorganised into collapsible sections

### Fixed

- RAG reused the first search's results for 30 minutes, so a later search (e.g. another city) could get the wrong properties
- With both `AI_SECRET_KEY` and `ALLOWED_ORIGINS` set, server-to-server calls with a valid key were rejected for having no `Origin` header
- The JussiSpace login token was never refreshed; tools now log in again after a `401`
- Unreadable uploads return `400` instead of `500`

---

## [1.2.3] - 2026-04-07

### Changed

- Cloud Run `--min-instances` set to `0` — service scales to zero when idle, eliminating idle billing for the portfolio deployment
- Cloud Run `--concurrency` raised from `5` to `20` — handles portfolio traffic on a single instance without unnecessary scaling

---

## [1.2.2] - 2026-04-01

### Changed

- Vertex AI SDK initialised once at module load time instead of per-request, eliminating cold-start latency on the first API call
- Agent modules imported at the top of `routes.py` to match — lazy per-request imports removed
- CV agent system prompt changed from "concise" to "thorough" — responses are now detailed and complete
- CV agent default model bumped from `gemini-2.5-flash-lite` to `gemini-2.5-flash`

### Fixed

- Test suite no longer raises `RuntimeError` on import — `GCP_PROJECT` dummy value set in `conftest.py` before app load
- Test patch targets updated from `agent.agent.ask` to `routes.ask_jussispace` to match the module-level import binding

---

## [1.2.1] - 2026-03-25

### Fixed

- RAG search now indexes room data (`rooms`) alongside amenities — room-based queries (e.g. "3 bedroom apartment") now match correctly
- Gemini responses with multiple content parts no longer raise `"Multiple content parts are not supported"` — first text part is safely extracted
- Suppressed CVE-2026-4539 (`pygments`) in `pip-audit` CI steps — no fix version available upstream yet

### Changed

- Added missing docstrings to `agent/`, `services.py`, `routes.py`, `main.py`, `scripts/`, and `tests/`

---

## [1.2.0] - 2026-03-24

### Added

#### JussiSpace agent — RAG property search
- `agent/rag.py` — `PropertyRAG` class fetches all properties, embeds them with Vertex AI `text-embedding-004`, and returns the top-3 semantically matched results per query
- Embedding cache TTL of 30 minutes; model client cached for the container lifetime to avoid repeated loading overhead
- Colloquial/informal Finnish search language supported (e.g. "kolmio" → 3-room apartment, "kaksi" → 2 rooms, "saunan kera" → sauna amenity)

#### JussiSpace agent — HTML property cards
- Properties rendered as HTML cards with image, bold title as a deep link to the frontend, city, type, price and status
- Order responses include bold order ID and bold status

#### Tests
- `/ai/chat` endpoint tests added to `tests/test_api.py` — happy path, language/history forwarding, 503/502 error handling; fully mocked, no GCP credentials needed locally

### Changed

- `agent/client.py` — `search_properties` now fetches all pages in a loop (pagination); 10s timeout added to all HTTP calls
- `cloudbuild.yaml` — switched to gen2 execution environment, added `concurrency=5`, set explicit `gemini-2.5-flash-lite` defaults for `JUSSISPACE_VERTEX_MODEL` and `JUSSIMATIC_CV_VERTEX_MODEL`
- README updated to reflect multi-agent platform scope
- `.env.example` — added `JUSSISPACE_FRONTEND_URL` with WSL2+Docker networking note

---

## [1.1.0] - 2026-03-22

### Added

#### Jussimatic AI CV agent — photo support
- Profile photo is now included in the Gemini context from the `photo` and `photo_sizes` fields in the CV API response
- Added `_resolve_image_url()` — resolves relative storage paths (e.g. `resumes/1/photo.jpg`) to absolute URLs using `JUSSILOG_STORAGE_BASE_URL`; absolute URLs are passed through unchanged
- System prompt instructs Gemini to output a `[photo]...[/photo]` tag immediately after the opening sentence when introducing Jussi
- Added `JUSSILOG_STORAGE_BASE_URL` env var (`https://jussilog-backend-uploads.storage.googleapis.com`) to `.env.example` and `cloudbuild.yaml`

### Changed

#### Jussimatic AI CV agent — CV formatting
- Work experience entries are now structured blocks (Company / Role / Period / Location / About) instead of single-line dash entries
- Education entries are now structured blocks (School / Degree / Graduated / Location)
- Skill category names are now human-readable and localised — Finnish (`Sovelluskehykset`, `Ohjelmointikielet`, …) or English based on the CV's `language` field
- `show_skill_levels` and `show_language_levels` flags from the CV JSON are now respected — proficiency levels are omitted from the Gemini context when set to `false`
- Awards include `issuer` and `date` fields in the context
- Projects section is now included in the Gemini context (was silently skipped before)

---

## [1.0.0] - 2026-03-22

### Added

#### AI Chat (`POST /ai/chat`)
- Multi-handler conversational AI endpoint powered by Google Vertex AI (Gemini)
- `jussispace` handler — property search and order status via JSON-based agentic loop
- `jussimatic-ai-cv-chat` handler — Q&A about Jussi Alanen's CV with 5-minute in-memory cache
- Multi-turn conversation history support (`history` field)
- Optional `language` field (`fi` / `en`); auto-detects from user input when omitted
- Per-handler model overrides via `JUSSISPACE_VERTEX_MODEL` and `JUSSIMATIC_CV_VERTEX_MODEL` env vars

#### Vertex AI support
- Gemini (`gemini-2.5-flash-lite`) replaces Puter AI as the default provider for all AI endpoints
- `vertex_ai` provider added to `/ai/review`
- Configurable model and region via `VERTEX_MODEL`, `AGENT_VERTEX_MODEL`, `AGENT_GCP_LOCATION`
- GCP service account key mounting via `GCP_KEY_PATH` (Docker) / `GOOGLE_APPLICATION_CREDENTIALS`

#### Security
- `AI_SECRET_KEY` — `Authorization: Bearer` token required on `/ai/chat` and `/ai/review`; skipped in local dev when unset
- Server-side `Origin` header enforcement on AI endpoints; returns `403` for unlisted origins when `ALLOWED_ORIGINS` is set
- CORS always enforced — wildcard in dev, strict allowlist in production
- `robots.txt` (`Disallow: /`) and `X-Robots-Tag` header on all responses

#### Developer tooling (`./dev`)
- `up`, `down`, `restart`, `logs`, `build`, `ps`, `shell` — Docker Compose wrappers
- `test` / `test-local` — run pytest inside container or local venv
- `set-env [svc] [region]` — push non-secret `.env` values to a Cloud Run service without rebuilding
- `create-secrets` — create or update all required secrets in Secret Manager with `JUSSI_AIBOT_` prefix
- `generate-postman [out] [url]` — regenerate Postman collection from live OpenAPI schema

#### CI / GitHub Actions
- `pip-audit` — dependency CVE audit for `requirements.txt` and `requirements-ml.txt`
- `bandit` — SAST scan (medium+ severity, medium+ confidence)
- `trivy` — container vulnerability scan (HIGH/CRITICAL, unfixed only)
- `pytest` — full test suite (66 tests)
- Dependabot — weekly grouped updates for pip and GitHub Actions

#### Tests
- `tests/test_api.py` — 13 API endpoint tests with mocked AI providers
- `tests/test_services.py` — 30 unit tests for pure service functions
- `tests/test_origin_security.py` — rewritten as proper pytest suite with parametrize

#### Infrastructure
- `cloudbuild.yaml` — Kaniko build + Cloud Run deploy with all Vertex AI / agent env vars; secrets injected from Secret Manager (`JUSSI_AIBOT_` prefix)
- `postman/postman_collection.json` — Postman Collection v2.1 with `AI_SECRET_KEY` variable and disabled `Authorization` header on every request
- `scripts/generate_postman.py` — generates Postman collection from FastAPI OpenAPI schema
- `.github/dependabot.yml` — weekly grouped dependency updates

### Changed

- `DEFAULT_PROVIDER` changed from `puter_ai` to `vertex_ai` in production (`cloudbuild.yaml`)
- `docker-compose.yml` — added `restart: unless-stopped`, `env_file`, all new env vars, GCP key volume mount
- `Dockerfile` — upgraded base image from `python:3.10-slim` to `python:3.12-slim`
- `routes.py` — removed `X-API-Key` authentication; replaced with `AI_SECRET_KEY` bearer token
- `agent/agent.py` — replaced native Vertex AI function calling with JSON-based agentic loop (required for `gemini-2.5-flash-lite`)
- `agent/client.py` — `JUSSISPACE_API_URL` now reads from env with fallback instead of crashing on missing var
- Vertex AI initialisation moved from module-level to per-request to prevent stale region caching across hot-reloads
- `pytest.ini` — added `pythonpath = .` for CI compatibility
- README fully rewritten with environment URLs, security model, Cloud Run guide, and all new features

### Fixed

- `python-multipart` bumped `0.0.12` → `0.0.22` (CVE-2024-53981, CVE-2026-24486)
- `pdfplumber` bumped `0.11.4` → `0.11.9` (pulls in `pdfminer.six==20251230`, fixes CVE-2025-64512, CVE-2025-70559)
- `transformers` bumped `4.46.3` → `>=4.53.0` (fixes 17 CVEs including CVE-2025-5197, CVE-2025-6921)
- `build_review_response` — added missing `"Tyydyttävä"` and `"Heikko"` to valid rating set
- `bandit` format flag corrected from `text` to `txt`
- `trivy-action` version corrected from non-existent `0.29.0` to `v0.35.0`
- CodeQL action upgraded from `v3` to `v4`

### Removed

- `run.sh` — replaced by `./dev` script
- `X-API-Key` / `API_KEYS` / `API_KEY_HASHES` authentication from Python code
