# Product Requirements Document (PRD)

## 1. Product overview

**Product name:** Lyftr AI - LLM Chatbot with Key Failover and Response Caching  
**Product type:** Full-stack web application  
**Primary objective:** Build, test, and deploy a reliable multi-turn AI chatbot that continues working when an LLM API key is rate-limited, out of quota, or temporarily unavailable, while reducing repeat-request latency and cost through LiteLLM response caching.

This PRD is derived from the six-page *Full-Stack Assignment: LLM Chatbot with Key Failover and Response Caching*. Where this document says **must**, it is an assignment requirement. The implementation must preserve the API and UI contracts exactly.

## 2. Problem statement

A basic chatbot can fail when its configured provider key reaches a rate limit, quota limit, or provider outage. Repeating the same request can also waste time and API cost. The application must provide a stable chat experience by:

- retaining conversation history separately for each chat session;
- trying another configured key when a key fails with a supported transient/provider error;
- caching complete LLM requests through LiteLLM;
- showing the resolution source, model, latency, and per-request token usage beside every assistant response;
- preserving history in SQLite across backend/container restarts.

## 3. Target users

1. **End user / evaluator:** Opens the public frontend, chats across multiple turns, and sees useful response metadata and readable errors.
2. **Technical evaluator:** Calls the three backend endpoints, checks exact response fields, validates cache hits, triggers failover through the simulation header, and checks SQLite-backed session history.
3. **Developer / maintainer:** Configures provider keys through environment variables, runs the complete stack with Docker Compose, runs tests, and deploys the two tiers.

## 4. Goals and success criteria

The application is successful only when all mandatory behaviors below work. Visual polish does not compensate for a broken API contract.

- A user can send messages and receive non-empty AI responses in a multi-turn chat.
- A new browser page load starts a new session with a new client-generated `session_id`.
- The backend reconstructs the full message list from SQLite and sends only the new message from the client.
- At least two LLM API keys are configured and identified as `key_1`, `key_2`, etc., in the order supplied.
- A supported failure on one key causes automatic use of another configured key.
- A request for which all configured keys fail returns the specified JSON 503 response and is not saved to history.
- LiteLLM's built-in cache is enabled. An identical first message in a different new session can return `LLM_CACHE` with identical reply text and cached token usage.
- A different full message list must not incorrectly reuse a cached answer.
- A cache hit has lower measured latency than the corresponding live inference in the verification flow.
- Each assistant reply displays request-level metadata, not conversation totals.
- SQLite data survives backend/container restarts when the named Docker volume is retained.
- The stack starts with `make up`, with the backend on port 8000 and frontend on port 3000.
- Frontend and backend are deployed to public, reachable URLs and are connected to each other.

## 5. Scope

### 5.1 Mandatory features

#### A. Chat interface

- Provide a clean web interface for sending messages and viewing a multi-turn conversation.
- Display user messages and assistant replies in order.
- Show metadata beside/under **each** assistant reply:
  - `resolution_source`: exactly `LLM_CACHE` or `LIVE_INFERENCE`;
  - `model`: model name that produced the reply;
  - `latency_ms`: server-measured integer milliseconds;
  - `input_tokens`: prompt tokens for this request only;
  - `output_tokens`: completion tokens for this reply only.
- Provide a readable inline error state for backend errors. Never leave the page blank or crash because a request failed.
- The optional system-prompt control may be implemented. When implemented, it must use `data-testid="system-prompt-input"` and behave as a session-level override.

#### B. Multi-turn session state

- The frontend creates a `session_id` (1-128 characters) on each page load.
- The client sends only the new message to `POST /chat`; it does not submit the full transcript.
- The backend reads prior user/assistant messages for that `session_id` from SQLite and includes them in the LLM prompt.
- Sessions remain isolated from each other.
- A `system_prompt` supplied on a chat request overrides the default system prompt for that session. Persist the override so subsequent turns in the same session continue using it. The system prompt is not returned in the messages history endpoint.

#### C. Key pool and automatic failover

- Use LiteLLM as the model gateway.
- Configure at least two API keys through `LLM_API_KEYS`, a comma-separated list.
- Derive safe key identifiers from list order: `key_1`, `key_2`, and so on. Never expose or return the raw key.
- Attempt another configured key when a provider request fails because of HTTP 429, quota exhaustion, or a 5xx/provider-unavailable error.
- `fallback_attempts` is the count of keys that failed before the successful key. It is `0` when the first key succeeds and also `0` for a cache hit.
- If every key fails, return HTTP 503 with `{"detail":"all providers unavailable"}`.

#### D. Built-in response caching

- Enable LiteLLM's built-in in-memory or disk cache. Do not replace it with a hand-written response cache.
- The effective cache identity must include the model and the complete ordered message list sent to the LLM: system prompt, stored history, and the new user message. Any generation options that affect the answer must also remain consistent in the cache identity.
- Do not include `session_id` in the LLM request/cache identity. Otherwise identical first messages in different sessions would not share a cache entry.
- A cache hit returns the identical reply text and the token usage stored with the cached response.
- On `LLM_CACHE`, `key_id` is `null` and `fallback_attempts` is `0`.
- Do not label a live response as a cache hit or a cache hit as live inference.
- A failover simulation must actually exercise the key pool, not be short-circuited by an existing cache entry. Therefore, bypass caching for a request carrying an enabled `X-Simulate-Failure` header; do not let the simulation result mask subsequent failover demonstrations.

#### E. SQLite storage

- SQLite is the only application database. Do not use Redis, PostgreSQL, or another external database.
- Store the database file under `/data` in Docker, configured with `DATABASE_URL` (recommended container value: `sqlite:////data/app.db`).
- Create the schema automatically at application startup.
- Implement the required `messages` table fields:
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `session_id TEXT NOT NULL`
  - `role TEXT NOT NULL` (`user` or `assistant`)
  - `content TEXT NOT NULL`
  - `metadata TEXT` (JSON string, assistant messages only)
  - `created_at TEXT NOT NULL` (server time in ISO-8601)
- Additional tables, columns, and indexes are allowed. A `sessions` table is recommended to persist a session-level system prompt and reliably distinguish an unknown session from a known session.
- Save a user message and its assistant response only after the LLM request succeeds. A 422/503 request must not be added to session history.

#### F. Failover test hook

`POST /chat` must support the `X-Simulate-Failure` header when `ENABLE_FAILURE_SIMULATION=true`.

Supported header examples:

```text
X-Simulate-Failure: key_1=429
X-Simulate-Failure: key_1=429,key_2=500
X-Simulate-Failure: *=429
```

- Format: comma-separated `<key_id>=<status>` pairs; `*` means every key.
- Supported statuses: `429`, `500`, `502`, `503`.
- The effect is request-scoped only. It must not mutate real credentials or persist to future requests.
- `key_1=429` with at least two keys must return 200 using `key_2` (assuming the second key is healthy).
- `key_1=500` with at least two keys must return 200 using `key_2` (assuming the second key is healthy).
- `*=429` must return 503 with the exact all-providers-unavailable detail and must save no messages.
- A simulated request that succeeds through fallback must return a real model answer, not an error message wrapped in HTTP 200.
- The simulation switch must be enabled on the deployed backend so the evaluator can demonstrate the behavior.

#### G. Backend endpoints

The backend exposes exactly these three application endpoints under its base URL. Do not add custom routes that expand this public API.

##### `GET /health`

Return HTTP 200 only when the application is running, SQLite is reachable, the key pool is loaded, and the cache is enabled.

Required JSON shape:

```json
{
  "status": "ok",
  "keys_configured": 2,
  "cache_enabled": true
}
```

`keys_configured` must report the actual configured key count and be at least 2 for a valid deployment.

##### `POST /chat`

Request JSON:

```json
{
  "session_id": "s-7f3a",
  "message": "What is the capital of France?"
}
```

Optional field:

```json
{
  "session_id": "s-7f3a",
  "message": "What is the capital of France?",
  "system_prompt": "Answer clearly and briefly."
}
```

Validation:

| Field | Type | Rule |
|---|---|---|
| `session_id` | string | Required; 1-128 characters; generated by client. An unknown ID starts a new session. |
| `message` | string | Required; after trimming whitespace it must contain 1-4000 characters. |
| `system_prompt` | string | Optional; overrides the default system prompt for this session. |

Required successful response shape:

```json
{
  "session_id": "s-7f3a",
  "reply": "The capital of France is Paris.",
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

The metadata values above are illustrative. The implementation must return actual values. `key_id` is a safe identifier or `null` on a cache hit.

Required metadata fields and meanings:

| Field | Type | Meaning |
|---|---|---|
| `resolution_source` | string | Exactly `LIVE_INFERENCE` or `LLM_CACHE`. |
| `model` | string | LiteLLM model name that produced the reply. |
| `latency_ms` | integer | Server-measured duration in milliseconds. |
| `input_tokens` | integer | Prompt tokens for this request: system prompt + stored history + new message. |
| `output_tokens` | integer | Completion tokens for this reply. |
| `key_id` | string or null | Safe key ID (`key_1`, `key_2`, ...); `null` on cache hit. Never return the API key. |
| `fallback_attempts` | integer | Number of failed keys before success; `0` on cache hit. |

##### `GET /sessions/{session_id}/messages`

- Return stored history for one session from SQLite, oldest message first.
- Exclude the system prompt.
- Return HTTP 404 for an unknown session with `{"detail":"session not found"}`.

Required response shape:

```json
{
  "session_id": "s-7f3a",
  "messages": [
    {"role": "user", "content": "What is the capital of France?"},
    {
      "role": "assistant",
      "content": "The capital of France is Paris.",
      "metadata": {
        "resolution_source": "LIVE_INFERENCE",
        "input_tokens": 42,
        "output_tokens": 9
      }
    }
  ]
}
```

Assistant metadata may contain the complete stored metadata object. User history entries must not contain assistant metadata.

#### H. Error contract

Every error response must be JSON and contain a `detail` field. Never expose a stack trace or return an HTML error page.

| Case | HTTP status | Required body/behavior |
|---|---:|---|
| Missing/empty `session_id` or `message`, malformed JSON, or message over 4000 characters | 422 | JSON with a `detail` field. FastAPI's standard validation body is acceptable. |
| Every configured key fails due to rate limit, quota, or 5xx/provider unavailability | 503 | `{"detail":"all providers unavailable"}`. No chat messages saved. |
| Unknown session in history endpoint | 404 | `{"detail":"session not found"}`. |

#### I. Frontend test hooks

Implement these exact `data-testid` values:

| `data-testid` | Element | Required content/behavior |
|---|---|---|
| `chat-input` | Text input or textarea | User message input; empty after a successful send. |
| `send-button` | Send button | Sends the message. Enter may also send. |
| `assistant-message` | Each assistant reply container | Reply text plus all metadata elements below. |
| `meta-source` | Inside each assistant message | Exactly `LIVE_INFERENCE` or `LLM_CACHE`. |
| `meta-model` | Inside each assistant message | The returned model value. |
| `meta-latency` | Inside each assistant message | Latency, e.g. `812 ms`. |
| `meta-input-tokens` | Inside each assistant message | The returned `input_tokens` integer. |
| `meta-output-tokens` | Inside each assistant message | The returned `output_tokens` integer. |
| `system-prompt-input` | Optional system prompt field | Only required if that feature is implemented. |

Frontend behavior:

- A new session starts on each page load.
- Errors (422 and 503) appear as readable messages in the chat UI; they must not cause a blank screen.
- The deployed frontend must call the deployed backend, and backend CORS must allow the frontend origin.
- The user sends only the new message, never the full transcript.

### 5.2 Mandatory local development and deployment

- Root `docker-compose.yml` starts the frontend and backend services.
- `make up` starts backend at `http://localhost:8000` and frontend at `http://localhost:3000`.
- `make down` stops the stack without deleting the named SQLite volume.
- Both backend and frontend use multi-stage Dockerfiles with small runtime images.
- A named Docker volume is mounted at `/data` for the SQLite file.
- All configuration is through environment variables.
- Frontend and backend must be separately deployed to public URLs and connected.
- The public URLs must be reachable without a login.

### 5.3 Required repository layout

The repository root must contain at least:

```text
/backend
/frontend
docker-compose.yml
Makefile
.env.example
README.md
```

Organize code inside `/backend` and `/frontend` as appropriate. Include backend tests.

### 5.4 Required backend environment variables

| Variable | Meaning |
|---|---|
| `LLM_API_KEYS` | Comma-separated key pool; at least two keys. IDs follow order: `key_1`, `key_2`, ... |
| `DATABASE_URL` | SQLite location, e.g. `sqlite:////data/app.db`. |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins. |
| `ENABLE_FAILURE_SIMULATION` | `true` enables the failover test hook. |

Additional variables are allowed when needed, such as `LLM_MODEL`, provider base URL, cache settings, and default system prompt. `.env.example` must list every required variable with placeholders. Real keys must never be committed.

### 5.5 Required README headings

The final `README.md` must use these sections:

1. **Live URLs**
2. **Run locally: with Docker and without**
3. **Design decisions: key fallback, caching, SQLite session storage**
4. **Verification: how to see failover, cache hits and per-message token usage**
5. **Setup Used: your editor and AI tools**
6. **Bonus features (if any): what you added beyond the requirements and why**

### 5.6 Required submission deliverables

- Public frontend URL.
- Public backend URL.
- Public GitHub repository.
- A 2-3 minute demo video with voice.
- Demo video must show the deployed application and all endpoints working, including a cache hit and failover using `X-Simulate-Failure`.
- Submission must be completed within 24 hours of receiving the assignment.

## 6. Non-functional requirements

- **Reliability:** Expected provider failures are handled and converted into fallback or the defined 503 response.
- **Security:** API keys stay in environment variables and are never returned to the frontend, logs, Git history, or metadata.
- **Data durability:** SQLite is stored on the named Docker volume mounted at `/data`.
- **Observability:** Log useful request/fallback diagnostics without logging secrets or full sensitive provider headers.
- **Maintainability:** Separate API routes, business logic, provider gateway, persistence, schemas, and frontend API/UI concerns.
- **Usability:** Loading and failure states are understandable, and metadata is readable on desktop and mobile.
- **Contract stability:** Exact endpoint paths, required JSON names, status codes, and test IDs are preserved.

## 7. Out of scope

Unless explicitly needed to satisfy a requirement, do not add:

- user accounts, sign-up, authentication, or authorization;
- Redis, PostgreSQL, MongoDB, or another database;
- a vector database, retrieval-augmented generation, or document uploads;
- streaming responses;
- conversation search, session management dashboards, or admin panels;
- billing, payments, or analytics dashboards;
- additional public backend endpoints.

## 8. Acceptance checklist

The project is ready for submission only when all applicable items are checked.

- [ ] `GET /health` returns the required fields and confirms SQLite, at least two keys, and cache are ready.
- [ ] `POST /chat` accepts the exact request fields and returns the exact required response fields.
- [ ] Missing/invalid request values produce JSON 422 errors.
- [ ] A successful first chat creates a session and stores user and assistant messages.
- [ ] A second turn in the same session uses the earlier messages as context.
- [ ] A different session does not see another session's messages.
- [ ] The history endpoint returns oldest-first messages and excludes system prompts.
- [ ] Unknown history session returns the required 404 JSON body.
- [ ] First-key simulated 429 and 500 failures fall back to the next key and return a real answer.
- [ ] All-keys simulated failure returns exact 503 JSON and saves no messages.
- [ ] The deployed backend has `ENABLE_FAILURE_SIMULATION=true`.
- [ ] Repeating an identical first message in a new session yields the identical reply with `LLM_CACHE`.
- [ ] A different prompt/history produces a cache miss.
- [ ] Cache-hit metadata has `key_id: null` and `fallback_attempts: 0`.
- [ ] Token usage is per request and appears next to every assistant reply.
- [ ] Every required frontend `data-testid` is present and correctly scoped.
- [ ] Frontend starts a new session on each page load and shows readable errors.
- [ ] `make up` starts both services at the required local ports.
- [ ] `make down` stops services while retaining the named database volume.
- [ ] Both Dockerfiles are multi-stage.
- [ ] `.env.example` contains placeholders, and no real key is committed.
- [ ] Backend tests pass.
- [ ] Public frontend, backend, and GitHub URLs work without login.
- [ ] README has the six required headings.
- [ ] 2-3 minute voice demo covers the live app, cache hit, and failover.

## 9. Source of truth

The uploaded assignment PDF remains authoritative. If implementation details are ambiguous, preserve the explicit requirements in this PRD and the API/UI contracts above. Do not rename fields, routes, test IDs, or required environment variables.
