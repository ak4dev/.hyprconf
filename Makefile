.PHONY: check test shellcheck lint fmt

export PYTHONDONTWRITEBYTECODE := 1

test:
	pytest -q -n auto -rs

# The three gates scripts/publish and CI run. `make` alone is the suites only.
check: lint shellcheck test

shellcheck:
	@files=$$(find . -path ./.git -prune -o -type f \
	    -exec awk 'FNR==1{if(/bash/)print FILENAME; nextfile}' {} +); \
	[ -n "$$files" ] || { echo "shellcheck: no bash scripts found" >&2; exit 1; }; \
	printf '%s\n' "$$files" | xargs -d '\n' shellcheck --severity=warning
	@# The two root-writing files also gate SC2086 (info-level, below the
	@# main pass's --severity=warning): an unquoted word there splits into an
	@# extra argument to a root command. SC2068 is error-level and already
	@# caught everywhere by the main pass.
	shellcheck --include=SC2086 install.sh bin/hyprconf-yubikey
	@echo "shellcheck: clean"

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff format .
	ruff check --fix .
