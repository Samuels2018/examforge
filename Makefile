.PHONY: install dev backend frontend test test-e2e lint build migrate backup backups restore docker-up docker-down clean

install:
	cd backend && uv sync --all-groups
	cd frontend && npm install

dev:
	@echo "Levanta dos terminales:"
	@echo "  make backend    # http://localhost:8000/docs"
	@echo "  make frontend   # http://localhost:5173"

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest

test-e2e:
	cd frontend && npm run test:e2e

lint:
	cd backend && uv run ruff check .
	cd backend && uv run mypy app
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

migrate:
	cd backend && uv run alembic upgrade head

backup:
	cd backend && uv run python -m app.cli backup

backups:
	cd backend && uv run python -m app.cli backups

restore:
	cd backend && uv run python -m app.cli restore $(FILE)

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

clean:
	rm -rf backend/.venv backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache frontend/node_modules frontend/dist frontend/test-results
