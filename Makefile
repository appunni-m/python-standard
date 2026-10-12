.PHONY: install check lint type test test-unit test-e2e bench docs-install docs-serve docs-build clean

install:
	python -m pip install -e '.[fastapi,aws]' -r requirements-test.txt -r requirements-docs.txt 'tox>=4,<5' 'mypy>=1.18,<2' 'ruff>=0.14,<1'

check:
	tox run

lint:
	tox run -e lint

type:
	tox run -e type

test:
	pytest

test-unit:
	pytest -m 'not e2e'

test-e2e:
	tox run -e e2e

bench:
	PYTHONPATH=src python benchmarks/configuration.py

docs-install:
	python -m pip install --requirement requirements-docs.txt

docs-serve:
	zensical serve

docs-build:
	zensical build --clean

clean:
	rm -rf build dist site .coverage htmlcov
