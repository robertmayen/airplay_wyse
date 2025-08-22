# Minimal convenience targets (documented only; keep logic light)

.PHONY: help format lint test vm-test package tag release health diag

help:
	@echo "Targets: format lint test vm-test package tag release health diag"

format:
	@echo "(no-op) formatting not configured"

lint:
	@bash ./tools/lints.sh || true

test:
	@bash ./tests/smoke.sh || true

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
	@echo "Documentation-only: install reconcile timer/service as root"
	@echo "  sudo install -m 0644 systemd/reconcile.service /etc/systemd/system/reconcile.service"
	@echo "  sudo install -m 0644 systemd/reconcile.timer /etc/systemd/system/reconcile.timer"
	@echo "  sudo systemctl daemon-reload"
	@echo "  sudo systemctl enable --now reconcile.timer"
	@echo "  sudo systemctl start reconcile.service"

release-notes:
	@echo "Reminder: releases are gated by signed, annotated tags."
	@echo "Devices must have the maintainer GPG public key installed for git verify-tag."
	@echo "Converge exits 5 (verify_failed) if tag verification fails."
