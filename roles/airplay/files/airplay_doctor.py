#!/usr/bin/env python3
"""airplay-doctor — diagnostics/health for an AirPlay 2 endpoint (stdlib only)."""
from __future__ import annotations

import re


def parse_shairport_version(text: str) -> dict:
    """Parse `shairport-sync -V` into a version string + feature flags.

    Token-tolerant: collapses whitespace and lowercases before matching, so
    'AirPlay2' and 'AirPlay 2' both register, regardless of feature casing.
    """
    compact = re.sub(r"\s+", "", text).lower()
    m = re.match(r"\s*([0-9][0-9A-Za-z.~+]*)", text)
    return {
        "version": m.group(1) if m else "",
        "airplay2": "airplay2" in compact,
        "soxr": "soxr" in compact,
        "alac": "alac" in compact,
    }
