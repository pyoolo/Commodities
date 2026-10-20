.PHONY: install test quick run lint

install:
	pip install -e ".[dev]"

test:
	pytest -q

quick:          ## small world, ~1 min: the development set
	python -m agriyield run --quick --out reports/quick

run:            ## full experiment (~15 min first time, cached afterwards)
	python -m agriyield run

lint:
	ruff check src tests
