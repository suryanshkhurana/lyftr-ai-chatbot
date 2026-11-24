# Rules for the Coding Agent

These rules are mandatory while implementing the assignment. They protect the exact contract, security, and reliability requirements.

## 1. Source-of-truth rules

1. Treat `PRD.md`, `Architecture.md`, `Phases.md`, and the uploaded assignment PDF as the product contract.
2. `Design.md` controls visual direction, but visual choices must never change required behavior or test IDs.
3. Do not rename endpoints, JSON fields, environment variables, `data-testid` values, or status codes.
4. Do not silently replace a required technology with an alternative.
5. If the repository already contains code, inspect the full relevant implementation and tests before changing it. Preserve working behavior unless it conflicts with an explicit assignment requirement.
6. Do not rely on an outdated README in place of the actual source code. Verify behavior in implementation and tests.

## 2. Technology rules

### Required

- Frontend: React.
- Backend: Python + FastAPI.
- LLM gateway: LiteLLM.
- Persistence: SQLite only.
- Cache: LiteLLM built-in cache (in-memory or disk).
- Local stack: Docker Compose, multi-stage Dockerfiles, and Makefile.
- Backend tests: pytest.

### Do not use

- Redis, PostgreSQL, MongoDB, or an external database.
- A custom dictionary/database cache instead of LiteLLM's built-in cache.
- Another LLM gateway/library in place of LiteLLM.
- LangChain or other orchestration libraries unless a concrete required feature cannot be implemented with LiteLLM directly. Prefer the smallest dependency set.
- A frontend/backend contract that differs from the PDF.

Use Python's standard `sqlite3` module unless another thin approach is genuinely simpler. Prefer plain React components and CSS over adding a large UI framework.

## 3. API contract rules

The only application endpoints are:

1. `GET /health`
2. `POST /chat`
3. `GET /sessions/{session_id}/messages`

Do not add custom backend routes. Disable FastAPI docs, redoc, and OpenAPI routes if they would make additional endpoints publicly available.

### `GET /health`

Must return HTTP 200 only when the database is reachable, the key pool is loaded, and the cache is enabled. Required fields:

```json
{"status":"ok","keys_configured":2,"cache_enabled":true}
```

Use the real configured key count. Do not return a hard-coded count.

### `POST /chat`

- Required request fields: `session_id` and `message`.
- `session_id`: string, 1-128 characters, generated in the browser.
- `message`: trim whitespace; require 1-4000 characters.
- `system_prompt`: optional; session-level override.
- Unknown session ID on POST starts a new session.
- Client sends only the new message. Backend loads history.
- Successful response must include `session_id`, non-empty `reply`, and `metadata` with all seven required fields.
- Do not rename `resolution_source`, `model`, `latency_ms`, `input_tokens`, `output_tokens`, `key_id`, or `fallback_attempts`.

### History endpoint

- Oldest message first.
- System prompt is never included.
- User messages contain `role` and `content` only.
- Assistant messages contain `role`, `content`, and metadata.
- Unknown session returns status 404 and exact detail `session not found`.

## 4. Provider and key-pool rules

1. Read real provider keys only from `LLM_API_KEYS`.
2. Split the comma-separated value, trim whitespace, and reject missing/empty entries.
3. Require at least two configured keys for a valid deployment.
4. Assign IDs by order: `key_1`, `key_2`, `key_3`, etc.
5. Use LiteLLM Router/gateway facilities to configure the key-specific deployments and automatic fallback.
6. Trigger fallback for rate limit/429, quota exhaustion, and provider 5xx/unavailable failures.
7. Count only keys that failed before the successful key in `fallback_attempts`.
8. `key_id` is a safe identifier only. It is never the real key or a substring of the real key.
9. If every key fails, return status 503 with exactly:

```json
{"detail":"all providers unavailable"}
```

10. Never return a fake assistant response or a provider error string as a successful model answer.
11. Never log API keys, authorization headers, or secret-bearing provider configuration.
12. Never hard-code, commit, or expose real keys in code, frontend variables, tests, screenshots, or documentation.

## 5. Caching rules

1. Enable LiteLLM's built-in cache; cache state must be reflected by `/health`.
2. Cache identity must include the model and the entire ordered LLM message list: system prompt + prior history + current user message.
3. Do not include `session_id`, per-request timestamps, random identifiers, or request IDs in the LLM input/cache identity.
4. Same model + same full message list + same generation settings should be eligible for a cache hit.
5. Different full message lists must not reuse a cached completion.
6. A cache hit must return identical reply text and the original usage data from the cached completion.
7. On `LLM_CACHE`, set `key_id` to `null` and `fallback_attempts` to `0`.
8. Do not claim a response is cached merely because the prompt is repeated. Detect cache hits using the pinned LiteLLM version's supported metadata and verify it with tests.
9. Keep the cache in-memory or disk. Do not add Redis.
10. Bypass cache lookup for an enabled `X-Simulate-Failure` request so simulation reliably tests the provider/key path. Do not let a prior cached result skip the simulated failure.
11. Measure actual request latency. Never subtract time or hard-code a lower duration to make cache appear faster.
12. Do not use `session_id` as a cache key because equivalent first messages in different sessions are required to reuse the cache.

## 6. Token and metadata rules

- `input_tokens` is the usage for the current LLM request: system prompt + all prior messages in the session + the new message.
- `output_tokens` is the usage for the current assistant completion.
- Never return running conversation totals.
- Prefer the provider/LiteLLM response's actual usage fields.
- If a provider does not expose usage, use a documented LiteLLM-supported token-counting fallback; do not invent values or silently return zeros.
- Preserve cached token usage on a cache hit.
- `latency_ms` must be an integer measured on the server.
- `model` must be the actual LiteLLM model name that generated the answer.
- `resolution_source` must be exactly `LIVE_INFERENCE` or `LLM_CACHE`.
- Include all metadata fields for every assistant response.

## 7. Failure-simulation rules

The `X-Simulate-Failure` hook is honored only when `ENABLE_FAILURE_SIMULATION=true`.

Supported examples:

```text
key_1=429
key_1=429,key_2=500
*=429
```

- Parse comma-separated `<key_id>=<status>` pairs.
- Supported statuses: 429, 500, 502, 503.
- A `*` target means every configured key.
- Simulated errors apply for one request only.
- Never mutate, disable, or overwrite actual credentials.
- `key_1=429` and `key_1=500` should fail over to `key_2` when that key is healthy.
- `*=429` must exhaust the pool, return the required 503, and persist no messages.
- A successful simulated failover returns a real model answer from the healthy key.
- Test this behavior with two or more configured mock deployments; do not rely on intentionally exhausting real API quota.

## 8. SQLite and persistence rules

1. SQLite is the only database.
2. The container database file must live under `/data` and be configured through `DATABASE_URL` (recommended: `sqlite:////data/app.db`).
3. Create tables automatically on startup.
4. Implement the assignment's `messages` table fields without renaming them.
5. `metadata` is JSON text for assistant messages and `NULL` for user messages.
6. Use server time in ISO-8601 format for `created_at`.
7. Store only roles `user` and `assistant` in the chat history.
8. Save the new user message and assistant response atomically after successful inference.
9. A 422 or 503 request must not be added to history. It must not leave a half-created session.
10. Keep the named Docker volume when running `make down`.
11. Do not store system prompts in the public messages list or return them from the history endpoint.
12. If using an additional `sessions` table to persist the system prompt, keep the required `messages` table intact.

## 9. Error-handling and validation rules

- All errors are JSON objects with a `detail` field.
- No HTML error pages.
- No stack traces in API responses.
- Use HTTP 422 for invalid/missing fields, malformed JSON, and messages over 4000 characters.
- Use HTTP 503 and the exact all-providers-unavailable detail when the key pool is exhausted.
- Use HTTP 404 and exact detail `session not found` for an unknown history session.
- Do not save failed requests.
- Handle provider exceptions at the gateway/service boundary and return a stable user-facing error.
- Log enough information to debug failures without exposing secrets or dumping sensitive request headers.

## 10. Frontend rules

All required test IDs must be exact and must remain present:

- `chat-input`
- `send-button`
- `assistant-message`
- `meta-source`
- `meta-model`
- `meta-latency`
- `meta-input-tokens`
- `meta-output-tokens`
- `system-prompt-input` only if the optional system prompt field is implemented

Additional UI rules:

1. Generate a new session ID on each page load.
2. Do not persist the session ID to localStorage or sessionStorage.
3. Send only the new message to the backend.
4. Every assistant reply container has all required metadata values inside it.
5. Empty the chat input after a successful send.
6. Show a visible loading state while awaiting the server.
7. Show 422/503 errors in readable inline UI; a failed request is not an assistant reply.
8. Prevent accidental duplicate sends while a request is pending.
9. Backend URL must be configurable through an environment variable; do not hard-code deployment URLs.
10. Keep the interface responsive and keyboard-accessible.

## 11. Docker, configuration, and repository rules

- Root `docker-compose.yml` must run backend and frontend.
- `make up` must make the app available at `http://localhost:8000` and `http://localhost:3000`.
- `make down` must stop the stack without deleting the database volume.
- Both Dockerfiles must be multi-stage and use small runtime images.
- Mount a named volume to backend `/data`.
- Configure services through environment variables.
- `.env.example` must list all required and additional variables with safe placeholders.
- Add `.env`, provider secrets, SQLite database files, build output, and Python/Node virtual environments to `.gitignore` as appropriate.
- Never COPY a developer's local `.env` or real credentials into a Docker image.

## 12. Testing rules

Before completing a phase:

1. Run the tests relevant to the phase.
2. Add regression tests for any bug fixed.
3. Test API response field names and types, not just HTTP success.
4. Test that failure cases do not write messages to SQLite.
5. Test cache behavior across different session IDs.
6. Test that separate sessions do not share history.
7. Verify the required test IDs in the rendered frontend/component tests.
8. Run the entire backend test suite before declaring completion.
9. Run `make up` and `make down` from a clean environment before final handoff.

Tests must be deterministic and must not require real API keys. Use mocked provider transports/deployments for automated tests; separately run a live smoke test when real keys are configured.

## 13. Code-quality rules

- Keep route handlers thin; place orchestration in services.
- Use typed Pydantic models for backend request/response contracts.
- Use typed TypeScript API models on the frontend.
- Keep provider error normalization in one place.
- Avoid broad `except Exception` blocks unless they log safely and map to a generic JSON error at the application boundary.
- Avoid unused dependencies, dead code, duplicated prompt-building logic, and undocumented magic values.
- Add comments for non-obvious LiteLLM integration behavior, not for self-explanatory code.
- Pin dependencies to compatible versions; make the cache/fallback tests prove the selected LiteLLM version works.
- Never claim deployment, tests, or external operations succeeded unless actually verified.

## 14. Documentation and handoff rules

- Final `README.md` must include the six exact headings required by the PRD.
- Document local setup with and without Docker.
- Explain key fallback, LiteLLM cache, SQLite session storage, token accounting, and failover simulation.
- Include real live URLs only after they have been deployed and checked. Use `Pending deployment` rather than inventing a URL.
- List editor and AI tools actually used; do not fabricate tool usage.
- List bonus features only if implemented and tested.
- Keep `MEMORY.md` updated after each implementation phase as specified in `Phases.md` and `AGENT_PROMPT.md`.
