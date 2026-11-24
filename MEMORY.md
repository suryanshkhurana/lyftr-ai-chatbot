# MEMORY — Lyftr AI chatbot (key failover + LiteLLM cache)

## Objective / non-negotiables
- React FE + FastAPI BE + LiteLLM gateway + SQLite only + LiteLLM built-in cache. Docker Compose, multi-stage Dockerfiles, Makefile (`up`, `down`).
- Exactly 3 routes: `GET /health`, `POST /chat`, `GET /sessions/{session_id}/messages`. Docs/OpenAPI disabled.
- Exact field names, status codes (422/503/404), test IDs, env vars (`LLM_API_KEYS`, `DATABASE_URL`, `ALLOWED_ORIGINS`, `ENABLE_FAILURE_SIMULATION`), ports 8000/3000, README headings — see PRD.md / assignment PDF.
- Never write real keys anywhere (code, docs, this file).

## Phase 0 baseline
- User folder `take-home-assignment` was EMPTY (no git, no code, no tests). Baseline: 0 tests. Greenfield build.

## Current state (all local phases done; deployment pending)
- Phase 0–4: DONE and verified. Phase 5: DONE except an actual `docker compose build/up` (see blockers). Phase 6: README + DEPLOY_AND_DEMO.md written; deployment NOT done.
- Backend: `backend/app/{main.py, schemas.py, api/routes.py, core/{config,logging}.py, db/{connection,schema,repository}.py, llm/{gateway,cache,failure_simulation}.py, services/chat_service.py}`. Run: `uvicorn app.main:create_app --factory`.
- Frontend: Vite 8 + React 19 + TS 7; `src/app/App.tsx`, `src/components/*`, `src/services/chatApi.ts`, `src/utils/sessionId.ts`, `src/styles/global.css`.
- Root: docker-compose.yml (named volume `lyftr_data` at /data), Makefile (up/down/logs/ps/test), .env.example, .gitignore, README.md, DEPLOY_AND_DEMO.md.

## Verified LiteLLM 1.110.3 behavior (probed + regression-tested)
- One Router model group per key (`key_N`, `model_info.id=key_N`) + `fallbacks=[{"key_1": [...rest]}]`, `num_retries=0`, `disable_cooldowns=True` → deterministic in-order failover, no cross-request state.
- `_hidden_params["model_id"]` = answering deployment. `x-litellm-attempted-fallbacks` header is the INDEX of the fallback entry, NOT a failed-key count (key_3 after 2 failures → 1). We use the key's position in the chain.
- `CustomLogger.async_pre_call_check` is awaited before each deployment attempt; raising litellm exceptions there triggers fallback → X-Simulate-Failure via ContextVar.
- Router passes `caching=False` unless `Router(cache_responses=True)`.
- In Router calls the cache key uses the MODEL GROUP name as "model" → per-key partitioning. Fixed with `caching_groups=[(LLM_MODEL, key_1, key_2, ...)]` (documented "caching across model groups"); model id is part of the group string, so identity = model + messages + gen params.
- api_key/metadata are not in the cache key. Hit: `_hidden_params["cache_hit"] is True`; usage preserved. Writes are async (tests wait via `wait_for_cache_entries`).
- Cache-hit path imports `soundfile` (and `orjson`) → pinned in requirements.txt.
- Per-call bypass for simulation: `cache={"no-cache": True, "no-store": True}`.

## Decisions
- Default `LLM_MODEL=gemini/gemini-3.5-flash-lite`. Verified on user's real key 2026-11-24: gemini-3.5-flash-lite returns 404 "no longer available to new users" (still listed by ListModels); gemini-3.5-flash-lite works. Configurable.
- `litellm.drop_params = True` (set in gateway): gemini-3.5-flash-lite rejects `temperature` → UnsupportedParamsError on every key; dropping keeps max_tokens. Regression test in test_health.py.
- Cache: LiteLLM `local` (in-memory) — resets on backend restart; documented.
- Invalid/unknown X-Simulate-Failure when enabled → 422 with readable detail. Disabled → header ignored.
- <2 keys or empty entry: app starts; /health 503 with reason; /chat 503 "all providers unavailable".
- Empty provider reply → treated as failure (503), never returned as a 200.
- Validation 422 body = FastAPI shape minus echoed `input`.
- Keys redacted from all log records (root + LiteLLM loggers); LiteLLM loggers set to CRITICAL (we log one concise line per failover).
- Optional `LLM_API_BASE` (OpenAI-compatible endpoints) — used for HTTP e2e with a mock server.
- Frontend: no maxLength on textarea so a >4000-char 422 can be shown in the UI; metadata test-id elements contain only their values.
- Tests use a LiteLLM `CustomLLM` provider `mockllm/*` (real Router/cache/fallback paths, no network).

## Tests run (final)
- `cd backend && python -m pytest` → 57 passed (repeated 3x, stable).
- `cd frontend && npx vitest run` → 11 passed; `npm run build` (tsc + vite) OK.
- HTTP e2e (uvicorn + LiteLLM `openai/` provider → local mock OpenAI server): health, multi-turn, cache hit (~75–100 ms vs ~600 ms live), key_1=429/500 → key_2, *=429 → 503 + 404 history, 422, real provider 429 failover, history after restart, cache hit with dead key_1 (84 ms). No keys in logs.
- Headless Chrome against built frontend: exact test-id values, input cleared, new session on reload → LLM_CACHE, 422 inline alert w/ text preserved, no mobile overflow.
- `docker compose config` valid.

## Verified on user's Windows machine (Docker Desktop 29.6.1, Compose v5.2.0) — 2026-11-24
- `docker compose up -d --build` OK (MinGW `make` on that PC is broken; `docker compose` used directly — same as `make up`).
- Real Gemini keys (gemini-3.5-flash-lite): /health ok (2 keys, cache on); multi-turn context; cache hit in new session (4 ms vs ~1600 ms, same text/tokens); session isolation after reload.
- X-Simulate-Failure: key_1=429 → 200 key_2 fb=1; key_1=500 → 200 key_2 fb=1; *=429 → 503; failed session → 404.
- `docker compose down` keeps volume lyftr-ai_lyftr_data; history intact after `up`.
- One transient incident: two fallback calls to key_2 hit the 30 s read timeout (Gemini-side stall); not reproducible afterwards, correctly returned 503.

## Blockers / remaining
- Deployment (Render/Vercel or similar), public GitHub repo, 2 real Gemini keys, demo video, submission form — require user's accounts. Steps in DEPLOY_AND_DEMO.md. README "Live URLs" = Pending; README "Setup Used" editor = TODO for user.

## Next action
- User: push repo (delete `_to_delete/` first); deploy backend then frontend; set ALLOWED_ORIGINS; run DEPLOY_AND_DEMO.md §4; fill README Live URLs; record demo.
