# AirPlay 2 GitOps Enhancement Patches Summary

This document contains all the patches needed to fully enable AirPlay 2 (RAOP2) support with nqptp integration in the GitOps repository.

## Overview

The current repository already has most of the infrastructure in place. These patches enhance and strengthen the existing implementation to ensure robust AirPlay 2 support.

## Files to Modify

### 1. `systemd/overrides/shairport-sync.service.d/override.conf`

**Change:** Strengthen the nqptp dependency from `Wants=` to `Requires=`

```diff
 [Unit]
-Wants=nqptp.service
+Requires=nqptp.service
 After=nqptp.service
```

### 2. `pkg/build-shairport-sync.sh`

**Change:** Add `--with-systemd` and `--with-convolution` flags, reorder for clarity

```diff
 ./configure \
-  --with-alsa \
-  --with-avahi \
   --with-ssl=openssl \
+  --with-avahi \
+  --with-alsa \
+  --with-systemd \
   --with-soxr \
   --with-metadata \
+  --with-convolution \
   --with-dbus \
   --with-raop2
```

### 3. `bin/converge` (minor enhancements)

**Change:** Add explicit logging for AP2 detection and improve degradation message

```diff
@@ -201,6 +201,7 @@ has_airplay2_build() {
   # Best-effort detection: look for "AirPlay 2" or RAOP2 in version output
   if ! command -v shairport-sync >/dev/null 2>&1; then return 1; fi
   local v
   v=$(shairport-sync -V 2>&1 || true)
+  log "Checking shairport-sync for AirPlay 2 support: $(echo "$v" | head -1)"
   echo "$v" | grep -Eqi 'AirPlay[[:space:]]*2|RAOP2' && return 0 || return 1
 }

@@ -469,7 +470,8 @@ main() {
     exit "$EXIT_DEGRADED"
   fi
   if ! has_airplay2_build; then
-    emit_health "degraded" "$EXIT_DEGRADED" "shairport-sync missing AirPlay 2 (RAOP2)" >/dev/null || true
+    log "WARN: shairport-sync lacks AirPlay 2 (RAOP2) support - install RAOP2-enabled build"
+    emit_health "degraded" "$EXIT_DEGRADED" "shairport-sync lacks AirPlay 2 (RAOP2); install RAOP2-enabled build" >/dev/null || true
     exit "$EXIT_DEGRADED"
   fi
```

### 4. `docs/runbook.md`

**Change:** Expand the AirPlay 2 Support section with detailed instructions

```diff
 ## AirPlay 2 Support
-- Install `nqptp` for multi‑room sync. The converge path now enables/starts `nqptp.service` automatically when present and orders `shairport-sync` after it via a unit override.
-- The Debian `shairport-sync` package may not include AirPlay 2 (RAOP2). To enable AirPlay 2, attach a locally built `pkg/shairport-sync_*.deb` compiled with `--with-raop2` to a signed tag. Devices will install/upgrade it automatically during converge.
-- Helper: use `pkg/build-shairport-sync.sh` on a Debian build host to produce a RAOP2‑enabled `.deb`.
-- Health: if `shairport-sync` lacks AirPlay 2 support, converge marks the system degraded with reason `shairport-sync missing AirPlay 2 (RAOP2)`.
-- No local manual steps are required — the broker installs packages and converge deploys configs and restarts services.
+- **Multi-room sync:** Install `nqptp` for AirPlay 2 time synchronization. The converge path enables/starts `nqptp.service` automatically when present and orders `shairport-sync` after it via a systemd override (`Requires=nqptp.service`).
+- **RAOP2-enabled builds:** Debian's stock `shairport-sync` package may lack AirPlay 2 (RAOP2) support. To enable AirPlay 2:
+  1. Build a RAOP2-enabled package: Run `pkg/build-shairport-sync.sh` on a Debian build host (produces `pkg/shairport-sync_*.deb` with `--with-raop2`, `--with-convolution`, and all required features).
+  2. Attach the `.deb` to your signed release tag or let CI attach it.
+  3. The updater (`bin/update`) automatically runs `dpkg -i` for any `pkg/*.deb` files found in the repo.
+- **Health monitoring:** If `shairport-sync -V` doesn't report "AirPlay 2" or "RAOP2", converge marks the system degraded with reason `shairport-sync lacks AirPlay 2 (RAOP2); install RAOP2-enabled build`.
+- **Verification:** Check AP2 status with `shairport-sync -V | grep -E 'AirPlay 2|RAOP2'` and nqptp with `systemctl status nqptp`.
+- **Zero touch:** No manual steps required on devices — the broker installs packages and converge deploys configs and restarts services automatically.
```

### 5. `README.md`

**Change:** Add AirPlay 2 enablement section and update highlights

```diff
 - ALSA auto‑detect: validates devices, finds a sensible mixer, unmute/80% volume.
-- AirPlay 2 ready: ensure `nqptp` is installed and attach a RAOP2‑enabled `shairport-sync` `.deb` to your release tag; converge installs it automatically and orders it after `nqptp`.
+- **AirPlay 2 (RAOP2) support:** Automatically installs attached `nqptp` and RAOP2-enabled `shairport-sync` packages from `pkg/` directory. Converge detects missing AP2 capability and degrades health appropriately. Systemd overrides ensure proper service ordering with `nqptp` for multi-room sync.

 ## Quick Start
 - Provision devices (controller scripts): `scripts/ops/provision-hosts.sh`
 - Tag a release: `git tag -s vX.Y.Z && git push --tags`
 - Devices auto‑update via `update.timer` and converge via `converge.service`.
 - Health snapshot: `./bin/health` on device; logs via `journalctl -u converge`.

+## AirPlay 2 Enablement
+- Build RAOP2-enabled package: `pkg/build-shairport-sync.sh` (requires Debian build host)
+- Build nqptp package: `pkg/build-nqptp.sh` (if not available via apt)
+- Attach `.deb` files in `pkg/` to your release tag
+- Devices automatically install packages and configure service dependencies
+- Verify: `shairport-sync -V | grep -E 'AirPlay 2|RAOP2'` and `systemctl status nqptp`
+
```

## Implementation Notes

1. **No changes needed for `bin/update`** - It already handles systemd override syncing and package installation correctly.

2. **The systemd override file already exists** - We're just strengthening the dependency from `Wants=` to `Requires=`.

3. **Health checks are already in place** - We're enhancing the logging and messaging for clarity.

4. **Package installation is automated** - The broker and update scripts already handle `.deb` files in the `pkg/` directory.

## Testing Checklist

After applying these patches:

1. [ ] Verify `shairport-sync -V` shows AirPlay 2 or RAOP2
2. [ ] Check `systemctl status nqptp` shows service active
3. [ ] Confirm systemd override is applied: `systemctl cat shairport-sync | grep Requires=nqptp`
4. [ ] Run `bin/health` and verify no degradation
5. [ ] Test multi-room playback between devices

## Commit and Tag Messages

See `patches/commit-message.txt` and `patches/tag-message.txt` for the recommended commit and tag messages.
