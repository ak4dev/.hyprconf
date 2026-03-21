.PHONY: test test-unit test-integration test-tui test-seq test-vm test-install build-vm-image

test-unit:
	pytest tests/unit/ -q -n auto

test-integration:
	pytest tests/integration/ -q -n auto

test-tui:
	pytest tests/tui/ -q -n auto

test: test-unit test-integration test-tui

# Sequential mode — lower resource use, clearer output (no parallelism)
test-seq:
	pytest tests/unit/ tests/integration/ tests/tui/ -q

test-vm: ## Requires running VM (bash tests/vm/run_vm.sh first)
	bash tests/vm/run_vm.sh --wait
	pytest tests/vm/ --run-vm -v

test-install: ## Requires packer-built image and running VM (bash tests/vm/run_vm.sh first)
	bash tests/vm/run_vm.sh --wait
	pytest tests/install/ --run-install -v

build-vm-image:
	bash tests/install/build_image.sh
