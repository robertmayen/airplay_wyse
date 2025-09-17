"""Package management helpers."""
from __future__ import annotations

from typing import Iterable

from . import utils


def ensure_package(name: str) -> None:
    dpkg = utils.run_cmd(["dpkg", "-s", name], check=False)
    if dpkg.returncode == 0:
        return
    env = utils.default_env({"DEBIAN_FRONTEND": "noninteractive"})
    utils.run_cmd(["apt-get", "update", "-y"], env=env)
    utils.run_cmd([
        "apt-get",
        "install",
        "-y",
        name,
    ], env=env)


def ensure_packages(names: Iterable[str]) -> None:
    for name in names:
        ensure_package(name)
