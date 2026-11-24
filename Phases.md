# Implementation Phases

Build and verify the project in small phases. Do not attempt to generate the full application in one pass. Each phase has a concrete output and an exit gate.

## Phase 0 - Repository audit and implementation setup

**Goal:** Understand the current workspace before changing code.

### Tasks

- Inspect the repository tree, existing frontend/backend code, configuration, tests, Docker files, and Git status.
- Run the existing tests and record the baseline result.
- Identify what is already implemented and what is missing against `PRD.md`.
- Preserve working code; do not replace the project with a fresh scaffold without first proving it is necessary.
- Confirm the required stack and environment variables.
- When the first code change is about to begin, create `MEMORY.md` (not before coding starts) and record the baseline, current state, decisions, and first implementation task.

### Exit gate

- A concise gap analysis exists.
- Existing tests have been run and their baseline is recorded.
- `MEMORY.md` has been created at the start of implementation, not during initial planning.
- No unrelated or destructive project changes have been made.

## Phase 1 - Backend foundation, configuration, and SQLite

**Goal:** Establish a reliable FastAPI application and persistent storage.

### Tasks

- Configure the Python project and dependency versions.
- Implement environment loading and validation for `LLM_API_KEYS`, `DATABASE_URL`, `ALLOWED_ORIGINS`, and `ENABLE_FAILURE_SIMULATION`.
- Add any required model/cache settings such as `LLM_MODEL` and a default system prompt.
- Require at least two non-empty configured key values for a valid application configuration; assign safe IDs by order.
- Implement SQLite connection handling using `DATABASE_URL`.
- Create the required `messages` table and recommended `sessions` table at startup.
- Add the session/message repository and ISO-8601 timestamps.
- Configure FastAPI CORS.
- Implement `GET /health` with real database/key-pool/cache readiness checks. If the LLM/cache wiring is not ready yet, the health endpoint should remain incomplete until it is truthful; do not hard-code readiness.
- Disable unnecessary FastAPI docs/OpenAPI routes so the public backend exposes only the required routes.

### Tests

- Schema is created automatically.
- Required columns and indexes exist.
- Database can be queried through the configured URL.
- Health returns the exact required field names when all dependencies are ready.
- Missing or insufficient key configuration fails startup/readiness cleanly.

### Exit gate

The backend starts with valid placeholder/test configuration, SQLite schema is created automatically, and health/readiness tests pass.

## Phase 2 - LiteLLM gateway, key pool, and failover

**Goal:** Make real provider calls resilient to a failing key.

### Tasks

- Configure LiteLLM Router/gateway with one deployment per configured key or an equivalent LiteLLM-supported setup.
- Keep the `key_1`, `key_2`, ... mapping deterministic and secret-safe.
- Configure automatic retry/fallback for HTTP 429, quota exhaustion, and provider 5xx/unavailable errors.
- Capture the identity of the deployment/key that actually answered.
- Calculate `fallback_attempts` as the number of keys that failed before the successful key.
- Normalize exhausted-key errors to HTTP 503 with `{"detail":"all providers unavailable"}`.
- Implement `X-Simulate-Failure` parsing, gated by `ENABLE_FAILURE_SIMULATION`.
- Make simulation request-scoped. Ensure it reaches the provider/fallback path rather than a cache hit.
- Use mock/test deployments for tests; never exhaust real provider quotas to test fallback.

### Tests

- `key_1=429` uses key_2 and returns a real mocked completion.
- `key_1=500` uses key_2 and returns a real mocked completion.
- `*=429` returns the exact 503 JSON and no completion.
- `fallback_attempts` is correct.
- Raw keys never appear in API output or logs.
- Disabled simulation does not apply simulated errors.

### Exit gate

The gateway proves automatic key failover and clean exhaustion behavior with deterministic tests.

## Phase 3 - LiteLLM cache, multi-turn chat, and history API

**Goal:** Deliver the complete backend chat contract.

### Tasks

- Enable LiteLLM's built-in cache (in-memory or disk); do not implement a custom cache.
- Pin and verify the selected LiteLLM version's cache-hit detection and cache usage preservation.
- Ensure the cache identity uses model + full ordered messages (system prompt, prior history, new message), not session ID.
- Implement `POST /chat` validation and service flow.
- Load stored history from SQLite and build the full LLM prompt on the server.
- Support session-level `system_prompt` override and persist it for later turns in that session.
- Send only the latest user message from the client; never trust client-submitted history.
- Extract actual model, latency, input/output token usage, cache/live source, key ID, and fallback count.
- Save user + assistant messages atomically only after successful completion.
- Implement `GET /sessions/{session_id}/messages`, oldest first, without system prompt.
- Implement required 422, 503, and 404 JSON errors.
- Ensure cache hits return the exact cached reply and cached token counts, with `key_id=null` and `fallback_attempts=0`.

### Tests

- Valid first turn returns exact response structure and stores both messages.
- Second turn includes earlier messages in the model prompt.
- Two sessions remain isolated.
- A different session with the same first message can hit cache.
- Cache hit reply and token counts match the original completion.
- A different message/full prompt does not hit the previous cache entry.
- Cache hit is measured faster than the live call in the deterministic test strategy; production latency is always measured, never faked.
- Unknown history session returns exact 404.
- Failed 422/503 request writes no history.
- History is oldest first and excludes system prompts.
- Token counts are per request, not cumulative.

### Exit gate

All three backend endpoints satisfy the exact contract and backend tests pass without requiring real provider credentials.

## Phase 4 - React frontend and metadata UI

**Goal:** Build a polished, usable chat UI that consumes the backend contract exactly.

### Tasks

- Set up/verify React and Vite; TypeScript is recommended.
- Generate a new `session_id` on each page load and keep it in memory for that page only.
- Implement a typed API client that sends only `session_id`, new `message`, and optional `system_prompt`.
- Build transcript, user/assistant message, metadata, composer, loading, and error components.
- Render all exact test IDs required by the PRD.
- Place all metadata test IDs inside each assistant reply container.
- Show `resolution_source`, model, latency, input token count, and output token count for each assistant message.
- Clear the input after a successful send.
- Show readable 422/503 errors without a blank screen; do not represent a failed request as a valid assistant reply.
- Add the optional system-prompt input only if it can be implemented cleanly as a session-level override.
- Apply `Design.md`, including responsive and accessible behavior.

### Tests / checks

- Test IDs are exact and present.
- Every assistant message renders all five metadata values.
- Successful send clears the input.
- Enter sends; Shift+Enter inserts a newline if using a textarea.
- Errors are readable and do not crash the UI.
- A page reload creates a new session ID.
- Frontend sends only the latest message, not the transcript.

### Exit gate

The frontend works against the local API and satisfies the required UI contract.

## Phase 5 - Docker, Makefile, and end-to-end local verification

**Goal:** Make the whole stack reproducible locally.

### Tasks

- Add a multi-stage backend Dockerfile.
- Add a multi-stage frontend Dockerfile with a small static runtime image.
- Add root `docker-compose.yml` with frontend and backend services.
- Publish backend on `localhost:8000` and frontend on `localhost:3000`.
- Mount a named Docker volume at backend `/data` and configure `DATABASE_URL` accordingly.
- Ensure browser requests use `http://localhost:8000` when the frontend is opened in the host browser; do not use an internal Compose hostname in browser-side API configuration.
- Add `Makefile` targets `up` and `down`.
- Add `.env.example` with every variable and placeholder values.
- Ensure `.env` and real secrets are gitignored and never copied into images.
- Confirm `make down` keeps the named database volume.

### Verification

- Run `make up` from the repository root.
- Verify frontend at `http://localhost:3000` and backend at `http://localhost:8000/health`.
- Send a multi-turn chat from the UI.
- Verify cache hit in a second new session.
- Verify failover with `X-Simulate-Failure`.
- Restart containers and verify history persistence for an existing session through the history endpoint.
- Run backend test suite and any frontend tests.
- Run `make down` and confirm data volume is retained.

### Exit gate

A clean local Docker run works exactly at the specified ports and all automated tests pass.

## Phase 6 - Deployment, README, and submission demo

**Goal:** Deliver a public, testable application and all submission materials.

### Tasks

- Prepare a public GitHub repository with no secrets, local database files, or build artifacts.
- Deploy backend to a public hosting platform.
- Configure backend environment variables, including at least two real LLM keys, SQLite `DATABASE_URL`, correct `ALLOWED_ORIGINS`, and `ENABLE_FAILURE_SIMULATION=true`.
- Deploy frontend publicly and set its API base URL to the deployed backend.
- Verify public CORS and live connectivity.
- Verify `GET /health`, `POST /chat`, and `GET /sessions/{session_id}/messages` on the deployed services.
- Run the cache-hit and failover demonstrations against the deployed app/API.
- Write `README.md` with the six exact headings from the PRD and accurate live URLs.
- Record a 2-3 minute demo video with voice. Show the deployed app, a multi-turn exchange, cache hit, failover, and relevant endpoint behavior.
- Complete the assignment submission form with the actual URLs and video.

### If credentials or hosting access are unavailable

Do not invent deployment URLs or claim deployment is complete. Finish all local work, prepare deployment instructions and a demo script, and list exactly which user-provided credentials or access are still required.

### Exit gate

Public frontend, backend, and repository are verifiably reachable; README is complete; demo video and submission details are ready.

## Phase completion protocol

At the end of every phase:

1. Run the relevant tests and checks.
2. Compare the implementation against the phase's exit gate and the requirements in `PRD.md`.
3. Fix failures before moving on where practical; clearly record any blocker that cannot be fixed.
4. Update `MEMORY.md` with completed work, changed files, test results, key decisions, known issues, and the exact next task.
5. Do not mark a phase complete merely because code was generated. It is complete only when its exit gate is verified.
