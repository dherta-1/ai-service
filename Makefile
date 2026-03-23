.PHONY: help install dev test lint format clean grpc-generate docker-up docker-down migrate seed

help:
	@echo "Available commands:"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install dependencies"
	@echo "  make dev              Install dev dependencies"
	@echo ""
	@echo "Database:"
	@echo "  make migrate          Run pending migrations"
	@echo "  make migrate-create   Create a new migration"
	@echo "  make migrate-status   Show migration status"
	@echo "  make migrate-rollback Rollback last migration"
	@echo "  make seed-run         Run pending seeds"
	@echo "  make seed-create      Create a new seed"
	@echo "  make seed-status      Show seed status"
	@echo "  make seed-cleanup     Clean up all seeds"
	@echo ""
	@echo "Code Quality:"
	@echo "  make test             Run tests"
	@echo "  make lint             Run linters"
	@echo "  make format           Format code with black"
	@echo "  make clean            Remove cache and temp files"
	@echo ""
	@echo "gRPC:"
	@echo "  make grpc-generate    Auto-discover and generate gRPC code from all proto files"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up        Start Docker Compose services"
	@echo "  make docker-down      Stop Docker Compose services"
	@echo "  make docker-logs      View Docker logs"
	@echo ""
	@echo "Running:"
	@echo "  make run              Run FastAPI server"
	@echo "  make run-worker       Run Kafka consumer worker"

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --cov=src

lint:
	flake8 src/
	mypy src/

format:
	black src/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache .coverage htmlcov dist build *.egg-info

migrate:
	python -m src.cli migrate run

migrate-create:
	@read -p "Enter migration description: " desc; \
	python -m src.cli migrate create "$$desc"

migrate-status:
	python -m src.cli migrate status

migrate-rollback:
	python -m src.cli migrate rollback

migrate-reset:
	python -m src.cli migrate reset --force

seed-run:
	python -m src.cli seed run

seed-create:
	@read -p "Enter seed description: " desc; \
	python -m src.cli seed create "$$desc"

seed-run-all:
	python -m src.cli seed run-all

seed-status:
	python -m src.cli seed status

seed-cleanup:
	python -m src.cli seed cleanup --force

grpc-generate:
	@command -v python >/dev/null 2>&1 || { echo "Python is not installed"; exit 1; }
	pip install grpcio-tools
	python scripts/generate_grpc.py

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f api

run:
	python main.py

run-worker:
	python -m src.worker

.DEFAULT_GOAL := help
