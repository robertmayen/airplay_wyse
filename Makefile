# Minimal convenience targets (documented only; keep logic light)

.PHONY: help format lint test vm-test tag release health diag setup apply

help:
	@echo "Targets: format lint test vm-test tag release health diag setup apply"

format:
	@echo "(no-op) formatting not configured"

lint:
	@bash ./tools/lints.sh || true

test:
	@bash ./tests/smoke.sh || true

vm-test:
	@echo "Run tests in local Debian 12/13 VM (see tests/vm/)"

tag:
	@echo "Creating annotated tag v$$(cat VERSION)"
	@git tag -a v$$(cat VERSION) -m "release v$$(cat VERSION)"

release:
	@echo "Pushing branch and tags"
	@git push origin HEAD --tags

health:
	@./bin/health || true

diag:
	@./bin/diag || true

setup:
	@sudo ./bin/setup

apply:
	@sudo ./bin/apply
