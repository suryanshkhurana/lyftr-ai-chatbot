# Lyftr AI: LLM chatbot with key failover and response caching

React + FastAPI + LiteLLM + SQLite. A multi-turn chatbot that keeps working when an LLM API key is rate-limited, out of quota, or returning 5xx errors, and that answers repeated prompts from LiteLLM's built-in cache. Every assistant reply shows its resolution source, model, latency, and per-request token usage.

```
backend/    FastAPI app (routes, chat service, LiteLLM gateway, SQLite repository) + pytest suite
frontend/   React + Vite + TypeScript UI + Vitest suite
docker-compose.yml  Makefile  .env.example
```

## Live URLs

| | URL |
|---|---|
| Frontend | https://lyftr-ai-chatbot-two.vercel.app |
| Backend | https://lyftr-ai-chatbot-pop8.onrender.com (e.g. [`/health`](https://lyftr-ai-chatbot-pop8.onrender.com/health)) |
| Repository | https://github.com/suryanshkhurana/lyftr-ai-chatbot |

The backend runs on Render's free tier: after ~15 minutes idle it sleeps, and the first request can take ~50 s to wake it. Its in-memory LiteLLM cache also resets when it sleeps or redeploys (history in SQLite does not reset on sleep; Render's free tier has no persistent disk, so a redeploy starts a fresh database).

## Run locally: with Docker and without

### With Docker (recommended)

Requirements: Docker Desktop (or Docker Engine + Compose v2) and `make`. On Windows, use Git Bash or WSL for `make`, or run `docker compose up -d --build` directly.

```bash
cp .env.example .env          # then put at least two real keys in LLM_API_KEYS
make up                       # builds and starts both services
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000/health

`make down` stops and removes the containers but **keeps** the named volume `lyftr_data` (mounted at `/data`), so session history survives restarts. `make logs` tails both services.

### Without Docker

Backend (Python 3.12+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export LLM_API_KEYS="key-one,key-two"                   # or put the variables in backend/.env
export DATABASE_URL="sqlite:///./data/app.db"
export ALLOWED_ORIGINS="http://localhost:3000"
export ENABLE_FAILURE_SIMULATION=true
uvicorn app.main:create_app --factory --port 8000
python -m pytest                                        # 56 tests, no real keys or network needed
```

Frontend (Node 22+):

```bash
cd frontend
npm ci
VITE_API_BASE_URL=http://localhost:8000 npm run dev     # http://localhost:3000
npm test                                                # 11 tests
```

### Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `LLM_API_KEYS` | yes | Comma-separated key pool, at least 2. Ids are `key_1`, `key_2`, … in this order. |
| `DATABASE_URL` | yes | SQLite URL. Docker: `sqlite:////data/app.db` (on the named volume). |
| `ALLOWED_ORIGINS` | yes | Comma-separated CORS origins (the frontend URL). |
| `ENABLE_FAILURE_SIMULATION` | yes | `true` enables the `X-Simulate-Failure` header. |
| `LLM_MODEL` | no | LiteLLM model id, default `gemini/gemini-flash-lite-latest`. |
| `LLM_API_BASE` | no | Base URL for OpenAI-compatible/self-hosted endpoints. |
| `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT_SECONDS` | no | Fixed generation settings (they are part of the cache identity). |
| `DEFAULT_SYSTEM_PROMPT` | no | System prompt for sessions without an override. |
| `LOG_LEVEL` | no | Default `INFO`. |
| `VITE_API_BASE_URL` | frontend build | URL the **browser** uses to reach the backend. |

Any LiteLLM-supported provider works. The default is Gemini because two free keys are easy to create in Google AI Studio. `gemini-flash-lite-latest` is Google's alias for the current lite model, chosen after testing: `gemini-2.5-flash-lite` is no longer available to new keys, and newer pinned models were frequently returning `503 high demand` on the free tier. Gemini 3.x models reject `temperature`, so LiteLLM's `drop_params` drops unsupported params per model.

## Design decisions: key fallback, caching, SQLite session storage

**Request flow.** The client sends only `{session_id, message, system_prompt?}`. The backend loads that session's stored history from SQLite and builds `[system, ...history, user]`. It sends that list through the LiteLLM Router, measures latency on the server, and only after a successful completion writes the user and assistant messages in a single transaction. A failed request (422/503) writes nothing, not even a session row.

**Key fallback (LiteLLM Router).** Each key is its own Router model group (`key_1`, `key_2`, …, with `model_info.id` set to the same id), chained with `fallbacks=[{"key_1": ["key_2", ...]}]`.
- `num_retries=0` makes each key exactly one attempt, so the order is deterministic.
- `disable_cooldowns=True` stops one failure (real or simulated) from changing how later requests are routed.
- LiteLLM's generic fallback covers 429/quota, 5xx/unavailable, and timeouts.
- `key_id` comes from `response._hidden_params["model_id"]`. `fallback_attempts` is the answering key's position in the chain, because every key before it failed.
- I verified that LiteLLM's `x-litellm-attempted-fallbacks` header is *not* a failed-key count: it reports `1` when key_3 answers after two failures.
- If the whole chain fails, the gateway boundary converts the error to `503 {"detail":"all providers unavailable"}`.
- An empty completion is treated as a failure rather than returned as a reply.

**Failure simulation.** `X-Simulate-Failure` is parsed only when `ENABLE_FAILURE_SIMULATION=true`. The parsed map lives in a `ContextVar` for that one request. A LiteLLM `CustomLogger.async_pre_call_check` hook, which the Router awaits before each deployment attempt, raises the same exception LiteLLM raises for a real provider status (`RateLimitError`, `InternalServerError`, `BadGatewayError`, `ServiceUnavailableError`). The Router's normal fallback then takes over. Real credentials and router state are never modified. Simulated requests bypass the cache (`cache={"no-cache": True, "no-store": True}`), so a cached answer can never hide a failover demonstration. A malformed or unknown-key header returns 422 with a readable `detail`.

**Caching (LiteLLM built-in, in-memory).** `litellm.cache = Cache(type="local")` with `Router(cache_responses=True)`. The cache key is LiteLLM's own: model, plus the full message list, plus generation params. `session_id` is never sent to the LLM, so the same first message in a new session hits. Two LiteLLM details had to be handled, and both are covered by regression tests:
1. Inside the Router, LiteLLM keys the cache on the *model group name*. With one group per key, an answer produced through key_2 would be invisible to requests that start at key_1. LiteLLM's documented `caching_groups` puts all key groups in one namespace. The group's first element is the real `LLM_MODEL`, so the identity is still model + messages, and changing the model never reuses another model's answer.
2. The Router passes `caching=False` unless `cache_responses=True` is set.

A hit is detected with `response._hidden_params["cache_hit"] is True` and reports `LLM_CACHE`, `key_id: null`, `fallback_attempts: 0`. It returns the identical text and the usage stored with the cached response. LiteLLM writes cache entries in a background task, so a request fired within milliseconds of the first may still be live. Because the cache is in-memory, it resets when the backend restarts; history does not.

**Tokens and latency.** `input_tokens`/`output_tokens` are the provider's `usage.prompt_tokens`/`completion_tokens` for that single request, covering system prompt, history, and new message, never a running total. If a provider omits usage, LiteLLM's `token_counter` is used. `latency_ms` is server-measured wall time for the request, from receipt until the completion is available.

**SQLite.** Python's `sqlite3`, schema created at startup, WAL mode.
- The `messages` table matches the assignment exactly (`id, session_id, role, content, metadata, created_at`), with an index on `(session_id, id)`. Assistant `metadata` is a JSON string; user metadata is `NULL`. `created_at` is UTC ISO-8601.
- A `sessions` table stores the per-session `system_prompt` override and is the authority for "unknown session", so history 404s are exact.
- `GET /sessions/{id}/messages` returns rows oldest first and never includes the system prompt.
- In Docker the file is `/data/app.db` on the named volume `lyftr_data`.

**API surface.** Exactly `GET /health`, `POST /chat`, `GET /sessions/{session_id}/messages`; FastAPI docs/OpenAPI are disabled. `/health` returns 200 only when SQLite answers a query, the key pool (≥2 keys) is loaded, and the cache is enabled; otherwise 503 with a reason. Every error is JSON with `detail`, and unexpected exceptions become a generic 500 without a stack trace. Configured keys are redacted from every log record.

**Frontend.** A session id is generated on each page load and kept only in React state, never in browser storage. Each assistant reply container (`assistant-message`) holds its own `meta-source`, `meta-model`, `meta-latency`, `meta-input-tokens`, and `meta-output-tokens` elements, each containing only its value. Errors render inline as alerts, never as assistant replies. The typed text is kept for retry and the input clears only after success.

## Verification: how to see failover, cache hits and per-message token usage

Set `B` to the backend URL (`http://localhost:8000` locally).

```bash
B=http://localhost:8000
curl -s $B/health
# {"status":"ok","keys_configured":2,"cache_enabled":true}
```

**Multi-turn + per-message tokens:**

```bash
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -d '{"session_id":"demo-1","message":"What is the capital of France?"}'
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -d '{"session_id":"demo-1","message":"What about Spain?"}'
curl -s $B/sessions/demo-1/messages
```

The second reply understands "What about Spain?" from context. Its `input_tokens` is larger because that request carried the history, and it is the count for that request only. In the UI the same numbers appear under every reply (`In … tokens`, `Out … tokens`).

**Cache hit:** send the *same first message* in a *new* session (in the UI: reload the page and ask the same first question):

```bash
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -d '{"session_id":"demo-2","message":"What is the capital of France?"}'
```

Expect `"resolution_source":"LLM_CACHE"`, the identical `reply`, the same `input_tokens`/`output_tokens`, `"key_id":null`, `"fallback_attempts":0`, and a much lower `latency_ms`. A different message, or the same message after different history, comes back `LIVE_INFERENCE`.

**Failover** (requires `ENABLE_FAILURE_SIMULATION=true`):

```bash
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: key_1=429' -d '{"session_id":"demo-3","message":"Give me one fun fact"}'
# 200, "key_id":"key_2", "fallback_attempts":1, a real answer
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: key_1=500' -d '{"session_id":"demo-3","message":"Another one"}'
# 200, "key_id":"key_2", "fallback_attempts":1
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: *=429' -d '{"session_id":"demo-4","message":"hi"}' -w ' %{http_code}\n'
# {"detail":"all providers unavailable"} 503
curl -s $B/sessions/demo-4/messages -w ' %{http_code}\n'
# {"detail":"session not found"} 404  -> nothing was stored
```

Also supported: `key_1=429,key_2=500` and statuses `502`/`503`. The UI marks a failover reply with "via key_2 after 1 failed key".

**Validation:** an empty or whitespace-only message, a missing `session_id`, a message over 4000 characters, or malformed JSON returns 422 JSON. Pasting more than 4000 characters into the UI shows the error inline.

**Automated tests** (no real keys, no network): `cd backend && python -m pytest` gives **57 passed**; `cd frontend && npm test` gives **11 passed**.
- Backend tests run the real LiteLLM Router, fallback, and cache code against a registered LiteLLM `CustomLLM` mock provider. They cover the contract, 422/503/404 bodies, nothing saved on failure, simulated and *real* provider 429/5xx failover, 3-key fallback counts, cache hits across sessions (including after a fallback), cache misses on different prompt/history/system prompt/model, latency ordering, token accounting, session isolation, system-prompt persistence, history order, restart persistence, CORS, exactly three routes, and keys never appearing in responses or logs.
- I also verified end to end over real HTTP: uvicorn with LiteLLM's `openai/` provider against a local mock OpenAI-compatible server, plus the production frontend bundle driven in headless Chrome.

## Setup Used: your editor and AI tools

- AI: Claude (Anthropic) as a coding agent. It implemented the code from my specification documents (PRD, architecture, rules, phases, design), probed the pinned LiteLLM version's behavior, and wrote and ran the test suites.
- Editor: VS Code

## Bonus features (if any): what you added beyond the requirements and why

- **Session system prompt** (`system-prompt-input`): the optional feature, persisted per session in a `sessions` table so later turns keep it, and never returned by the history endpoint.
- **Failover badge in the UI**: replies served by a fallback key show which key answered and how many failed first, so failover is visible without reading JSON.
- **Service status indicator**: the header calls the existing `GET /health` once on load. No extra backend route.
- **Secret redaction in logs**: every log record, including LiteLLM's, has configured keys replaced with `***` (tested).
- **Shared cache across keys** via LiteLLM `caching_groups`, so an answer produced during an outage is reused once the primary key recovers.
