.PHONY: run lint type test

run:
	uvicorn --factory example_app.main:create_app --reload

lint:
	python -m ruff format --check src tests
	python -m ruff check src tests

type:
	python -m mypy src/example_app

test:
	python -m pytest -q
