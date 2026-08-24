.PHONY: help test test-unit test-integration test-seq shellcheck lint fmt clean

export PYTHONDONTWRITEBYTECODE := 1

# All shipped + test Python: the library and the tests.
PYSRC := lib/hyprconf/ \
         tests/

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	    awk -F':.*?## ' '{printf "  %-20s %s\n", $$1, $$2}'

test: test-unit test-integration ## Run unit + integration suites (parallel)

test-unit: ## Run unit tests in parallel
	pytest tests/unit/ -q -n auto

test-integration: ## Run integration tests in parallel
	pytest tests/integration/ -q -n auto

# Sequential mode — lower resource use, clearer output (no parallelism)
test-seq: ## Run all tests sequentially (clearer output)
	pytest tests/unit/ tests/integration/ -q

shellcheck: ## Run shellcheck on every bash script in the tree (severity=warning)
	@files=$$(find . -path ./.git -prune -o -type f -print | while IFS= read -r f; do \
	    head -n1 "$$f" | grep -q bash && printf '%s\n' "$$f"; done); \
	[ -n "$$files" ] || { echo "shellcheck: no bash scripts found" >&2; exit 1; }; \
	printf '%s\n' "$$files" | xargs -d '\n' shellcheck --severity=warning
	@echo "shellcheck: clean"

lint: ## Run ruff lint + format check on all Python (the CI gate)
	ruff check $(PYSRC)
	ruff format --check $(PYSRC)

fmt: ## Auto-format all Python with ruff (format + safe lint fixes)
	ruff format $(PYSRC)
	ruff check --fix $(PYSRC)

clean: ## Remove build artefacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache .coverage
