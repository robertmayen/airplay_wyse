# Minimal convenience targets (documented only; keep logic light)

.PHONY: help format lint test setup apply units

help:
	@echo "Targets: format lint test setup apply"

format:
	@echo "(no-op) formatting not configured"

lint:
	@bash ./tools/lints.sh || true

test:
	@./bin/test-airplay2 --no-strict || true

setup:
	@sudo ./bin/setup

apply:
	@sudo ./bin/apply

units:
	@sudo ./bin/install-units
