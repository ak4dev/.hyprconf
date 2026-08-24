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

shellcheck: ## Run shellcheck on all bash scripts (severity=warning)
	@git ls-files -z | while IFS= read -r -d '' f; do \
	    [ -f "$$f" ] && head -n1 "$$f" | grep -q bash && printf '%s\0' "$$f"; \
	done | xargs -0 -r shellcheck --severity=warning
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
