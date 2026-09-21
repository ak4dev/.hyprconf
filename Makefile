.PHONY: check test shellcheck lint fmt

export PYTHONDONTWRITEBYTECODE := 1

test:
	pytest -q -n auto -rs

# The three gates scripts/publish and CI run. `make` alone is the suites only.
check: lint shellcheck test

shellcheck:
	@# Every bash script in the tree, by SHEBANG (the rule conftest.py::shipped_bash states);
	@# anchored, since a bare `/bash/` also matches a first-line comment naming the shell.
	@files=$$(find . -path ./.git -prune -o -type f \
	    -exec awk 'FNR==1{if(/^#!.*bash/)print FILENAME; nextfile}' {} +); \
	[ -n "$$files" ] || { echo "shellcheck: no bash scripts found" >&2; exit 1; }; \
	printf '%s\n' "$$files" | xargs -d '\n' shellcheck --severity=warning
	@# The root writers also gate SC2086 (info-level, so below the main pass's
	@# --severity=warning): an unquoted word there splits into an extra argument
	@# to a root command. The same three tests/test_scans.py::SUDO_CALLERS pins.
	shellcheck --include=SC2086 \
	    modules/firefox/install modules/keychron/install \
	    modules/yubikey/bin/hyprconf-yubikey
	@echo "shellcheck: clean"

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff format .
	ruff check --fix .
