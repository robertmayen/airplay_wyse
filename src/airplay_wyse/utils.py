"""Utility helpers shared across commands."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


class CommandError(RuntimeError):
    """Raised when a subprocess exits unexpectedly."""


DEFAULT_ENV_PATH = [
    "/usr/local/sbin",
    "/usr/local/bin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
]


def ensure_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("this command must be run as root")


def run_cmd(
    cmd: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        check=False,
        text=True,
        capture_output=capture_output,
        env=env,
        cwd=str(cwd) if cwd is not None else None,
    )
    if check and result.returncode != 0:
        raise CommandError(f"command {' '.join(cmd)} failed with {result.returncode}")
    return result


def default_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PATH", ":".join(DEFAULT_ENV_PATH))
    if extra:
        env.update(extra)
    return env
