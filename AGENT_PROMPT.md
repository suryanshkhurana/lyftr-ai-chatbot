# Master Prompt for the Coding Agent

Copy the prompt below into your coding agent from the repository root. The agent must read the five planning documents before changing code.

---

## PROMPT START

You are the senior full-stack engineer responsible for completing the **Lyftr AI - LLM Chatbot with Key Failover and Response Caching** assignment.

Your task is to inspect the current repository, implement the application end to end, verify it against the assignment contract, and prepare it for public deployment and submission.

### 1. Read these files first

Before editing anything, read all of these files in full:

1. `PRD.md`
2. `Architecture.md`
3. `Rules.md`
4. `Phases.md`
5. `Design.md`

These files encode the uploaded six-page assignment PDF. Treat them as the source of truth for the implementation. Do not simplify, rename, omit, or reinterpret mandatory requirements. In particular, preserve the API paths, request/response field names, HTTP status codes, environment-variable names, frontend `data-testid` attributes, Docker ports, and README headings exactly.

### 2. Audit the existing repository before coding

- Start by listing the repository structure and inspecting relevant source files, dependency manifests, environment examples, tests, Docker configuration, Makefile, and README.
- Check Git status before modifying files.
- Run the existing test suite and record the baseline result.
- Compare the current code against the PRD and create a concise gap list.
- Reuse and improve working implementation where appropriate. Do not replace the project with a new scaffold merely because it is easier.
- Do not assume the README accurately reflects the implementation; inspect actual code and tests.
- Do not delete or overwrite user work without a clear requirement.

### 3. Create MEMORY.md when implementation begins

Do **not** create `MEMORY.md` during the initial planning/document-reading stage. Create it immediately before the first code change, when implementation actually begins.

Seed `MEMORY.md` with:

- assignment objective and non-negotiable constraints;
- repository structure and current implementation state;
- existing test baseline;
- environment variables and configuration status (never write real secrets);
- decisions already made and their reasons;
- phase currently in progress;
- files changed so far;
- tests/checks run and their results;
- known issues, blockers, and risks;
- the exact next action.

Update `MEMORY.md` at the end of every phase and whenever a significant architectural decision, test result, or blocker changes. Keep it factual and concise so a new agent or chat can resume without repeating repository discovery. Never put API keys or other secrets in it.

### 4. Implement in the prescribed phases

Follow `Phases.md` in order:

- Phase 0: repository audit and setup;
- Phase 1: FastAPI foundation, configuration, and SQLite;
- Phase 2: LiteLLM key pool, automatic fallback, and failure simulation;
- Phase 3: LiteLLM caching, multi-turn chat, and history endpoint;
- Phase 4: React frontend and metadata UI;
- Phase 5: Docker, Makefile, and local end-to-end verification;
- Phase 6: public deployment, README, and submission demo.

Do not move to the next phase merely because code has been generated. Run the phase tests and satisfy its exit gate first. At each phase boundary, update `MEMORY.md` with completed work, files changed, test commands/results, decisions, unresolved issues, and the next exact task.

### 5. Non-negotiable technical requirements

#### Stack

- React frontend.
- Python + FastAPI backend.
- LiteLLM as the LLM gateway.
- SQLite as the only application database.
- LiteLLM's built-in cache (in-memory or disk).
- Docker Compose, multi-stage frontend/backend Dockerfiles, and a Makefile.

Do not introduce Redis, PostgreSQL, MongoDB, a custom cache, or another LLM gateway.

#### Public backend API

Expose exactly these three application routes:

- `GET /health`
- `POST /chat`
- `GET /sessions/{session_id}/messages`

Disable FastAPI docs/redoc/OpenAPI routes if necessary so no extra public application routes are exposed.

`GET /health` must return the fields:

```json
{"status":"ok","keys_configured":2,"cache_enabled":true}
```

Use actual readiness checks and the actual key count; never hard-code readiness.

`POST /chat` request:

```json
{
  "session_id": "client-generated-id",
  "message": "The latest user message",
  "system_prompt": "Optional session override"
}
```

`system_prompt` is optional. `session_id` is required and 1-128 characters. `message` is required and must be 1-4000 characters after trimming. An unknown session ID on POST starts a new session. The frontend sends only the new message; the backend loads prior history from SQLite.

Successful response must include:

```json
{
  "session_id": "client-generated-id",
  "reply": "A non-empty real model response",
  "metadata": {
    "resolution_source": "LIVE_INFERENCE",
    "model": "provider/model-name",
    "latency_ms": 812,
    "input_tokens": 42,
    "output_tokens": 9,
    "key_id": "key_1",
    "fallback_attempts": 0
  }
}
```

All metadata fields are mandatory. Values above are illustrative only.

`GET /sessions/{session_id}/messages` returns the session's messages oldest first and excludes the system prompt. Unknown session returns HTTP 404 and `{"detail":"session not found"}`.

#### Key pool and automatic fallback

- Read `LLM_API_KEYS` as a comma-separated list containing at least two real keys in deployed configuration.
- Map keys by order to `key_1`, `key_2`, and so on.
- Configure LiteLLM Router/gateway deployments so 429, quota exhaustion, and provider 5xx/unavailable errors trigger fallback to another key.
- `fallback_attempts` is the count of failed keys before the key that answered.
- Never return, log, or expose real keys.
- If all keys fail, return HTTP 503 and exact body `{"detail":"all providers unavailable"}`.

#### LiteLLM cache

- Use LiteLLM's built-in cache; do not write a replacement cache.
- Cache identity must include model + complete ordered messages (system prompt + stored history + new user message).
- Do not include `session_id` in the LLM request/cache identity.
- The same first message in a different new session must be eligible for a cache hit and return identical reply text and stored token usage.
- Cache hit metadata must use `resolution_source="LLM_CACHE"`, `key_id=null`, and `fallback_attempts=0`.
- A cache hit should be faster than live inference because it avoids the provider call. Measure actual latency; do not fake it.
- Bypass the cache for an enabled `X-Simulate-Failure` request so the failure hook always exercises the key pool and cannot be masked by a cached answer.
- Pin the LiteLLM version and verify its actual Router, cache detection, cache usage, and deployment-identification behavior. Do not assume undocumented response fields.

#### SQLite

- SQLite only; no external data service.
- Store the Docker database under `/data`, configured through `DATABASE_URL`, e.g. `sqlite:////data/app.db`.
- Create schema automatically at startup.
- Preserve the required `messages` table columns: `id`, `session_id`, `role`, `content`, `metadata`, `created_at`.
- You may add a `sessions` table to persist a system prompt override.
- Store assistant metadata as a JSON string; user metadata is null.
- Use ISO-8601 server timestamps.
- Save user + assistant messages atomically only after successful inference.
- 422 and 503 failures must not be stored.
- The Docker named volume mounted at `/data` must preserve history across container restarts.

#### Failure simulation

Implement `X-Simulate-Failure` on `POST /chat` only when `ENABLE_FAILURE_SIMULATION=true`.

Accepted forms:

```text
key_1=429
key_1=429,key_2=500
*=429
```

Statuses are 429, 500, 502, 503. `*` targets all configured keys. Simulation is per request only and must not mutate the actual credentials.

- `key_1=429` with two healthy configured deployments: succeed using `key_2`, return a real answer, and show one fallback attempt.
- `key_1=500` with two healthy configured deployments: same expected behavior.
- `*=429`: return the exact 503 error and save no messages.

Automate these with mock/test deployments. Do not consume real provider quota to run tests.

#### Errors

- Every error is JSON and has a `detail` field.
- 422 for missing/empty required fields, malformed JSON, or message over 4000 characters.
- 503 for all provider keys unavailable, exact detail `all providers unavailable`.
- 404 for an unknown history session, exact detail `session not found`.
- No HTML errors or stack traces in API responses.
- Failed requests are not persisted.

#### Token and latency metadata

- `input_tokens` includes the system prompt, stored history, and new user message for this request only.
- `output_tokens` is the completion usage for this reply only.
- Never show conversation totals.
- Use actual provider/LiteLLM usage fields where available. If not available, implement and document a LiteLLM-supported token-counting fallback; do not invent values.
- `latency_ms` is an integer measured on the server.
- `model` is the model that actually answered.

#### Frontend contract

Implement the exact `data-testid` attributes:

- `chat-input`
- `send-button`
- `assistant-message`
- `meta-source`
- `meta-model`
- `meta-latency`
- `meta-input-tokens`
- `meta-output-tokens`
- `system-prompt-input` only if the optional system-prompt feature is built

Every assistant reply container must include all required metadata children. Generate a fresh session ID on every page load; do not persist it in browser storage. Send only the latest message. Show readable 422/503 errors without a blank screen. Clear the input after a successful send.

#### Docker / local ports

- `make up` starts the app.
- Backend: `http://localhost:8000`.
- Frontend: `http://localhost:3000`.
- Root `docker-compose.yml` runs both services.
- Both Dockerfiles must be multi-stage.
- Named volume mounts at `/data`.
- `make down` must not delete the named volume.
- All configuration is environment-driven.
- `.env.example` lists every variable with safe placeholders.

### 6. Required environment variables

At minimum:

```env
LLM_API_KEYS=placeholder-key-1,placeholder-key-2
DATABASE_URL=sqlite:////data/app.db
ALLOWED_ORIGINS=http://localhost:3000
ENABLE_FAILURE_SIMULATION=true
LLM_MODEL=<provider>/<model-name>
```

`LLM_MODEL` is an additional recommended setting. Include any other variables actually used in `.env.example`. Never commit real provider keys. For tests, use fake keys and mocked provider deployments.

### 7. Test requirements

Add and run tests for:

- automatic schema creation and health readiness;
- required routes, request validation, exact field names, data types, and error bodies;
- successful chat and request metadata;
- multi-turn context construction;
- session isolation;
- oldest-first history and unknown-session 404;
- 422/503 requests not being saved;
- simulated key_1 429/500 fallback to key_2;
- all-key simulated failure returning 503 without history changes;
- cache hit across two different session IDs for the same first message;
- identical cached reply and token usage;
- distinct prompt/history not reusing cache;
- correct cached metadata (`key_id=null`, `fallback_attempts=0`);
- frontend test IDs, input clearing, and readable error states;
- Docker persistence after a restart with the volume retained.

Tests must be deterministic and must not depend on real API keys. Run the entire backend test suite before final handoff and report the actual test command and result.

### 8. Docker, deployment, and repository deliverables

Required root files:

```text
backend/
frontend/
docker-compose.yml
Makefile
.env.example
README.md
```

The final `README.md` must contain these exact headings:

1. `Live URLs`
2. `Run locally: with Docker and without`
3. `Design decisions: key fallback, caching, SQLite session storage`
4. `Verification: how to see failover, cache hits and per-message token usage`
5. `Setup Used: your editor and AI tools`
6. `Bonus features (if any): what you added beyond the requirements and why`

Deployment is mandatory for assignment completion:

- deploy backend publicly;
- deploy frontend publicly;
- connect frontend to backend;
- configure CORS for the actual frontend origin;
- configure at least two real provider keys securely;
- set `ENABLE_FAILURE_SIMULATION=true` in deployed backend;
- verify all endpoints and browser interaction on public URLs.

Do not invent URLs, credentials, deployment results, video links, or test results. If hosting access or provider secrets are not available in the environment, finish all possible implementation work and state exactly what access or secrets are required for the remaining step. Never expose a secret in the final response.

Prepare a 2-3 minute voice-demo script/checklist showing the deployed app, multi-turn chat, a cache hit, and failover with `X-Simulate-Failure`. Do not claim to have recorded the video unless an actual video file exists.

### 9. Implementation workflow

For each phase:

1. Read the relevant documents and `MEMORY.md`.
2. State the current phase objective and the files likely to change.
3. Inspect the relevant code before editing.
4. Make the smallest coherent implementation change.
5. Run tests and relevant commands.
6. Inspect failures and fix them; do not suppress tests just to get a green run.
7. Verify acceptance criteria against the PRD.
8. Update `MEMORY.md` with exact progress and the next action.
9. Only then move to the next phase.

If a requirement cannot be implemented as written because of a verified library/platform limitation, do not silently change the contract. Explain the limitation, investigate a compliant workaround, and record the decision in `MEMORY.md`.

### 10. Final handoff format

When finished, report:

- what is implemented;
- the repository tree (important files only);
- exact commands used to test and the real results;
- local run commands and local URLs;
- public frontend URL, backend URL, and repository URL only if actually deployed and verified;
- cache-hit verification steps;
- failover verification steps, including the exact header to send;
- known limitations/blockers and exactly what remains;
- demo video status and submission checklist;
- confirmation that `MEMORY.md` reflects the final state.

Do not say "complete" if mandatory tests, deployment, failover, caching, SQLite persistence, Docker, or README requirements remain unverified.

Begin now with **Phase 0 repository audit**. Do not start coding until you have inspected the current repository and recorded the baseline. Create `MEMORY.md` immediately before the first code change, as instructed above.

## PROMPT END
