"""Runtime and systemd deployment helpers."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable

LIBEXEC_ROOT = Path("/usr/local/libexec/airplay_wyse")

WRAPPER_COMMANDS = {
    "identity-ensure": ["identity", "ensure"],
    "alsa-policy-ensure": ["policy-alsa", "--json"],
    "pw-policy-ensure": ["policy-pipewire", "--json"],
    "health-probe": ["health"],
    "setup": ["setup"],
    "apply": ["apply"],
    "install-units": ["systemd", "install"],
}


def _copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def install_runtime(source_root: Path) -> None:
    src_dir = source_root / "src" / "airplay_wyse"
    cfg_dir = source_root / "cfg"
    if not src_dir.exists():
        raise FileNotFoundError(f"missing module sources at {src_dir}")
    LIBEXEC_ROOT.mkdir(parents=True, exist_ok=True)
    (LIBEXEC_ROOT / "src").mkdir(parents=True, exist_ok=True)
    _copytree(src_dir, LIBEXEC_ROOT / "src" / "airplay_wyse")
    if cfg_dir.exists():
        _copytree(cfg_dir, LIBEXEC_ROOT / "cfg")
    _write_aw_launcher()
    _write_wrappers()


def _write_aw_launcher() -> None:
    aw_path = LIBEXEC_ROOT / "aw"
    content = """#!/usr/bin/env bash
set -euo pipefail
BASE="$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)"
export PYTHONPATH="${BASE}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec python3 -m airplay_wyse.cli "$@"
"""
    aw_path.write_text(content, encoding="utf-8")
    os.chmod(aw_path, 0o755)


def _write_wrappers() -> None:
    for name, command in WRAPPER_COMMANDS.items():
        path = LIBEXEC_ROOT / name
        args = " ".join(command)
        content = f"""#!/usr/bin/env bash
set -euo pipefail
BASE="$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)"
exec "$BASE/aw" {args} "$@"
"""
        path.write_text(content, encoding="utf-8")
        os.chmod(path, 0o755)


def install_systemd_units(source_root: Path, *, install_override: bool = True) -> Iterable[Path]:
    systemd_dir = source_root / "systemd"
    if not systemd_dir.exists():
        raise FileNotFoundError("systemd directory missing")
    installed: list[Path] = []
    target_dir = Path("/etc/systemd/system")

    for unit in systemd_dir.glob("*.service"):
        dest = target_dir / unit.name
        shutil.copy2(unit, dest)
        installed.append(dest)

    overrides = systemd_dir / "overrides"
    if install_override and overrides.exists():
        for dropin in overrides.rglob("*.conf"):
            rel = dropin.relative_to(overrides)
            dest = target_dir / "shairport-sync.service.d" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dropin, dest)
            installed.append(dest)

    return installed
