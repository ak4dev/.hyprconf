.PHONY: test test-unit test-integration test-tui test-vm test-install build-vm-image

test-unit:
	pytest tests/unit/ -q

test-integration:
	pytest tests/integration/ -q

test-tui:
	pytest tests/tui/ -q

test: test-unit test-integration test-tui

test-vm: ## Requires running VM (bash tests/vm/run_vm.sh first)
	bash tests/vm/run_vm.sh --wait
	pytest tests/vm/ --run-vm -v

test-install: ## Requires packer-built image and running VM (bash tests/vm/run_vm.sh first)
	bash tests/vm/run_vm.sh --wait
	pytest tests/install/ --run-install -v

build-vm-image:
	bash tests/install/build_image.sh
