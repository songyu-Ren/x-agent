.PHONY: dev up down lint test migrate

dev:
	docker compose up --build

up:
	docker compose up --build -d

down:
	docker compose down -v

lint:
	python -m ruff check .
	python -m ruff format --check .
	python -m black --check .
	python -m mypy app tests
	cd frontend && npm run lint

test:
	python -m pytest -q

migrate:
	alembic upgrade head

