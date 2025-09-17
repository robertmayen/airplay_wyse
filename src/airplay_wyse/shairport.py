"""Shairport/NQPTP helpers."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import packages, utils


@dataclass
class StackStatus:
    shairport_installed: bool
    nqptp_installed: bool
    has_airplay2: bool
    has_soxr: bool


SHAIRPORT_PKG = "shairport-sync"
NQPTP_PKG = "nqptp"
NQPTP_REPO = "https://github.com/mikebrady/nqptp.git"

NQPTP_BUILD_DEPS = (
    "build-essential",
    "git",
    "autoconf",
    "automake",
    "libtool",
    "pkg-config",
)


def ensure_stack() -> StackStatus:
    packages.ensure_package(SHAIRPORT_PKG)
    try:
        packages.ensure_package(NQPTP_PKG)
    except utils.CommandError:
        _build_nqptp_from_source()
    has_airplay2 = False
    has_soxr = False
    try:
        result = utils.run_cmd(["shairport-sync", "-V"], capture_output=True)
        output = result.stdout or result.stderr
        if "AirPlay2" in output:
            has_airplay2 = True
        if "soxr" in output.lower():
            has_soxr = True
    except utils.CommandError:
        pass
    return StackStatus(
        shairport_installed=True,
        nqptp_installed=True,
        has_airplay2=has_airplay2,
        has_soxr=has_soxr,
    )


def _build_nqptp_from_source() -> None:
    packages.ensure_packages(NQPTP_BUILD_DEPS)
    with tempfile.TemporaryDirectory(prefix="aw-nqptp-") as tmpdir:
        workdir = Path(tmpdir)
        repo_dir = workdir / "nqptp"
        utils.run_cmd(["git", "clone", NQPTP_REPO, str(repo_dir)])
        utils.run_cmd(["autoreconf", "-fi"], cwd=repo_dir)
        utils.run_cmd(["./configure", "--with-systemd-startup"], cwd=repo_dir)
        jobs = str(max(os.cpu_count() or 1, 1))
        utils.run_cmd(["make", f"-j{jobs}"], cwd=repo_dir)
        utils.run_cmd(["make", "install"], cwd=repo_dir)
    utils.run_cmd(["systemctl", "daemon-reload"], check=False)
