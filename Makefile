.PHONY: check test shellcheck lint fmt

export PYTHONDONTWRITEBYTECODE := 1

test:
	pytest -q -n auto -rs

# The three gates scripts/publish and CI run. `make` alone is the suites only.
check: lint shellcheck test

shellcheck:
	@# Every bash script in the tree, selected by SHEBANG — the rule
	@# tests/unit/test_omarchy_install.py::_overlay_scripts states. Anchored:
	@# a plain `/bash/` also matched prose — any first-line comment that
	@# merely mentions bash, as a config header naming a shell does.
	@files=$$(find . -path ./.git -prune -o -type f \
	    -exec awk 'FNR==1{if(/^#!.*bash/)print FILENAME; nextfile}' {} +); \
	[ -n "$$files" ] || { echo "shellcheck: no bash scripts found" >&2; exit 1; }; \
	printf '%s\n' "$$files" | xargs -d '\n' shellcheck --severity=warning
	@# The root-writing files also gate SC2086 (info-level, below the main
	@# pass's --severity=warning): an unquoted word there splits into an extra
	@# argument to a root command. SC2068 is error-level and already caught
	@# everywhere by the main pass. modules/{firefox,keychron}/install are the
	@# two module installs that call sudo; modules/yubikey's tool writes root
	@# files through its own run_root.
	shellcheck --include=SC2086 install.sh \
	    modules/firefox/install modules/keychron/install \
	    modules/yubikey/bin/hyprconf-yubikey
	@echo "shellcheck: clean"

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff format .
	ruff check --fix .
