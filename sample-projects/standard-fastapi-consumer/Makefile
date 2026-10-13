.PHONY: test lint type check run

test:
	python -m pytest

lint:
	python -m ruff format --check src tests
	python -m ruff check src tests

type:
	python -m mypy --explicit-package-bases src/consumer_app

check: test lint type

run:
	uvicorn consumer_app.main:create_app --factory --host 127.0.0.1 --port 8000
