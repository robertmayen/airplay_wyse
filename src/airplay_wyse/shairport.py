"""Shairport/NQPTP helpers."""
from __future__ import annotations

from dataclasses import dataclass

from . import packages, utils


@dataclass
class StackStatus:
    shairport_installed: bool
    nqptp_installed: bool
    has_airplay2: bool
    has_soxr: bool


SHairport_PKG = "shairport-sync"
NQPTP_PKG = "nqptp"


def ensure_stack() -> StackStatus:
    packages.ensure_packages([SHAirport_PKG, NQPTP_PKG])
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
