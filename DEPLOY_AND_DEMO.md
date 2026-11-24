# Deployment + demo checklist

Nothing below has been done yet. It needs your accounts and keys.

## 0. Keys
Create **two** Gemini API keys in Google AI Studio (ideally in two different Google Cloud projects, so their quotas are independent). Never commit them.

## 1. GitHub (public repo)
```bash
git init && git add . && git commit -m "Lyftr AI chatbot"
git branch -M main
git remote add origin https://github.com/<you>/lyftr-ai-chatbot.git
git push -u origin main
```
Check that `.env` is **not** in the commit (`git ls-files | grep -i env` should show only `.env.example`).

## 2. Backend on Render (Docker)
1. New → Web Service → connect the repo. Root directory: `backend`. Runtime: Docker. Instance: Free.
2. Environment variables:
   - `LLM_API_KEYS` = `key1,key2` (the real keys)
   - `DATABASE_URL` = `sqlite:////data/app.db`
   - `ALLOWED_ORIGINS` = your frontend origin, e.g. `https://lyftr-ai.vercel.app` (no trailing slash; set it after step 3 and redeploy)
   - `ENABLE_FAILURE_SIMULATION` = `true`
   - `LLM_MODEL` = `gemini/gemini-3.5-flash-lite`
3. Health check path: `/health`. Render injects `PORT`; the image honors it.
4. Note: Render's free tier has no persistent disk, so `/data` resets on redeploy or idle restart, and free instances also sleep. For durable history, attach a paid Render Disk at `/data`, or use Railway with a volume mounted at `/data`. Local Docker persistence (the assignment's volume requirement) is unaffected.

Alternatives: Railway (Dockerfile, add a volume at `/data`), Fly.io (`fly launch` in `backend/`, volume at `/data`), or Hugging Face Spaces (Docker Space; set `PORT=7860`).

## 3. Frontend on Vercel
1. New Project → import the repo. Root directory: `frontend`. Framework: Vite.
2. Environment variable: `VITE_API_BASE_URL` = the backend URL from step 2 (e.g. `https://lyftr-ai-backend.onrender.com`).
3. Deploy, then put the Vercel origin into the backend's `ALLOWED_ORIGINS` and redeploy the backend.

## 4. Verify on the public URLs
```bash
B=https://<backend>
curl -s $B/health
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -d '{"session_id":"live-1","message":"What is the capital of France?"}'
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -d '{"session_id":"live-2","message":"What is the capital of France?"}'   # LLM_CACHE
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: key_1=429' -d '{"session_id":"live-3","message":"Fun fact?"}'  # key_2
curl -s -XPOST $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: *=429' -d '{"session_id":"live-4","message":"hi"}' -w ' %{http_code}\n'  # 503
curl -s $B/sessions/live-1/messages
curl -s $B/sessions/nope/messages -w ' %{http_code}\n'   # 404
```
Open the frontend, send a message, and confirm in DevTools → Network that the request goes to the backend URL with no CORS error. Then fill in the README's **Live URLs** table.

## 5. Demo video script (2–3 min, with voice)
1. **(0:00–0:15) Intro.** "This is Lyftr AI: React frontend on Vercel, FastAPI and LiteLLM backend on Render, SQLite storage, two Gemini keys with automatic failover, and LiteLLM's response cache." Show both URLs.
2. **(0:15–0:30) Health.** Open `<backend>/health`: `keys_configured: 2`, `cache_enabled: true`.
3. **(0:30–1:05) Multi-turn.** In the UI ask "What is the capital of France?", then "What about Spain?". Point at the metadata row: `LIVE_INFERENCE`, model, latency, and In/Out tokens for that request only. Note that the second input count is larger because it includes history.
4. **(1:05–1:25) History endpoint.** Get the session id from DevTools (request payload) and open `<backend>/sessions/<id>/messages`: oldest first, no system prompt.
5. **(1:25–1:50) Cache hit.** Reload the page (new session) and ask "What is the capital of France?" again. The reply shows `LLM_CACHE`: same text, same tokens, far lower latency. Mention that the cache key is model + full message list, which is why a new session hits.
6. **(1:50–2:30) Failover.** In a terminal, run the `X-Simulate-Failure: key_1=429` curl to get 200 with `key_id: key_2` and `fallback_attempts: 1`. Repeat with `key_1=500`. Then run `*=429` to get 503 `all providers unavailable`, and show that `GET /sessions/<that id>/messages` is 404 (nothing saved).
7. **(2:30–2:50) Wrap.** Validation: send an empty body or more than 4000 characters to get a 422 JSON error, shown inline in the UI. Mention the 56 backend and 11 frontend tests and `make up`.

## 6. Submission form
Frontend URL · backend URL · GitHub URL · video link.
