.PHONY: up down logs ps test test-backend test-frontend

# Start the whole stack: backend http://localhost:8000, frontend http://localhost:3000
up:
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example - put your real LLM_API_KEYS in it.")
	docker compose up -d --build
	@echo "Backend:  http://localhost:8000/health"
	@echo "Frontend: http://localhost:3000"

# Stop and remove containers/network. The named SQLite volume (lyftr_data) is kept.
down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

test: test-backend test-frontend

test-backend:
	cd backend && python -m pytest

test-frontend:
	cd frontend && npm test
