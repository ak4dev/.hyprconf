.PHONY: check test test-unit test-integration shellcheck lint fmt clean

export PYTHONDONTWRITEBYTECODE := 1

# All shipped + test Python: the library and the tests.
PYSRC := lib/hyprconf/ \
         tests/

test: test-unit test-integration

test-unit:
	pytest tests/unit/ -q -n auto

test-integration:
	pytest tests/integration/ -q -n auto

# The three gates scripts/publish and CI run. `make` alone is the suites only.
check: lint shellcheck test

shellcheck:
	@files=$$(find . -path ./.git -prune -o -type f -print | while IFS= read -r f; do \
	    head -n1 "$$f" | grep -q bash && printf '%s\n' "$$f"; done); \
	[ -n "$$files" ] || { echo "shellcheck: no bash scripts found" >&2; exit 1; }; \
	printf '%s\n' "$$files" | xargs -d '\n' shellcheck --severity=warning
	@echo "shellcheck: clean"

lint:
	ruff check $(PYSRC)
	ruff format --check $(PYSRC)

fmt:
	ruff format $(PYSRC)
	ruff check --fix $(PYSRC)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache
