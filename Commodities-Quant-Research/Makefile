.PHONY: help install test lint figures clean

help:
	@echo "install  - install dependencies (dev extras included)"
	@echo "test     - run the full test suite"
	@echo "lint     - ruff check"
	@echo "figures  - regenerate every project's figures"
	@echo "clean    - remove caches and generated outputs"

install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

figures:
	@for d in projects/*/; do \
		if [ -f "$$d/run_analysis.py" ]; then \
			echo ">> $$d"; \
			( cd "$$d" && python run_analysis.py ) || exit 1; \
		fi \
	done

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
