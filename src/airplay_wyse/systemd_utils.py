"""Systemd helper utilities."""
from __future__ import annotations

import shutil
from pathlib import Path

from . import utils


SYSTEMD_DIR = Path("/etc/systemd/system")


def install_unit(src: Path, dest_name: str) -> Path:
    dest = SYSTEMD_DIR / dest_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def daemon_reload() -> None:
    utils.run_cmd(["systemctl", "daemon-reload"])


def enable(service: str, *, now: bool = False, ignore_failure: bool = False) -> None:
    cmd = ["systemctl", "enable"]
    if now:
        cmd.append("--now")
    cmd.append(service)
    try:
        utils.run_cmd(cmd)
    except utils.CommandError:
        if not ignore_failure:
            raise


def restart(service: str) -> None:
    utils.run_cmd(["systemctl", "restart", service])
