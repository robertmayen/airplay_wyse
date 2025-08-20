# Minimal convenience targets (documented only; keep logic light)

.PHONY: help format lint test vm-test package tag release health diag

help:
	@echo "Targets: format lint test vm-test package tag release health diag"

format:
	@echo "(no-op) formatting not configured"

lint:
	@echo "(no-op) linting not configured"

test:
	@./tests/smoke.sh || true

vm-test:
	@echo "Run tests in local Debian 12/13 VM (see tests/vm/)"

package:
	@echo "Build artifacts off-box if needed; place in pkg/artifacts/"

tag:
	@echo "Create signed annotated tag from VERSION (off-box)"

release:
	@echo "Push signed tag; devices verify-only on-box"

health:
	@./bin/health || true

diag:
	@./bin/diag || true
.PHONY: install-units release-notes

install-units:
	@echo "Documentation-only: install systemd unit as root"
	@echo "  sudo install -m 0644 systemd/converge.service /etc/systemd/system/converge.service"
	@echo "  sudo systemctl daemon-reload"
	@echo "  sudo systemctl enable converge.service"
	@echo "  sudo systemctl start converge.service"

release-notes:
	@echo "Reminder: releases are gated by signed, annotated tags."
	@echo "Devices must have the maintainer GPG public key installed for git verify-tag."
	@echo "Converge exits 5 (verify_failed) if tag verification fails."
