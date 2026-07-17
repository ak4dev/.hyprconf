.PHONY: help test test-unit test-integration test-tui test-seq test-vm test-install \
        build-vm-image shellcheck lint typecheck fmt clean

export PYTHONDONTWRITEBYTECODE := 1

# All shipped + test Python: the library, the two standalone scripts, and tests.
PYSRC := stow/hypr/.local/lib/hyprconf/ \
         stow/hypr/.config/hypr/scripts/theme-switcher/switch_theme.py \
         stow/hypr/.config/hypr/scripts/hyprconf-tui/main.py \
         tests/

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	    awk -F':.*?## ' '{printf "  %-20s %s\n", $$1, $$2}'

test: test-unit test-integration test-tui ## Run unit + integration + TUI suites (parallel)

test-unit: ## Run unit tests in parallel
	pytest tests/unit/ -q -n auto

test-integration: ## Run integration tests in parallel
	pytest tests/integration/ -q -n auto

test-tui: ## Run TUI tests in parallel
	pytest tests/tui/ -q -n auto

# Sequential mode — lower resource use, clearer output (no parallelism)
test-seq: ## Run all tests sequentially (clearer output)
	pytest tests/unit/ tests/integration/ tests/tui/ -q

test-vm: ## Requires running VM (bash tests/vm/run_vm.sh first)
	bash tests/vm/run_vm.sh --wait
	pytest tests/vm/ --run-vm -v

test-install: ## Requires packer-built image and running VM (bash tests/vm/run_vm.sh first)
	bash tests/vm/run_vm.sh --wait
	pytest tests/install/ --run-install -v

build-vm-image: ## Build the QEMU/KVM VM image via Packer
	bash tests/install/build_image.sh

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

typecheck: ## Run mypy on the Python library (informational — not yet a CI gate)
	mypy stow/hypr/.local/lib/hyprconf/

clean: ## Remove build artefacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage
