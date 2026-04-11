.PHONY: help test test-unit test-integration test-tui test-seq test-vm test-install \
        test-web build-vm-image lint fmt clean

export PYTHONDONTWRITEBYTECODE := 1

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

test-web: ## Run web frontend tests (Vitest)
	cd web && npx vitest run

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

lint: ## Run ruff linter on source and tests
	ruff check stow/hypr/.local/lib/hyprconf/ tests/

fmt: ## Auto-format source and tests with ruff
	ruff format stow/hypr/.local/lib/hyprconf/ tests/

clean: ## Remove build artefacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache .mypy_cache
