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


def parse_listening_ports(ss_output: str, ports=(319, 320)) -> dict:
    """From `ss -ulnp`, report which target UDP ports are bound and by nqptp."""
    result = {p: {"bound": False, "nqptp": False} for p in ports}
    for line in ss_output.splitlines():
        for p in ports:
            if re.search(rf"[:.]{p}\b", line):
                result[p]["bound"] = True
                if "nqptp" in line:
                    result[p]["nqptp"] = True
    return result


def parse_mdns(avahi_output: str) -> dict:
    return {
        "airplay": "_airplay._tcp" in avahi_output,
        "raop": "_raop._tcp" in avahi_output,
    }


def parse_alsa_cards(aplay_l_output: str) -> set:
    cards = set()
    for line in aplay_l_output.splitlines():
        m = re.match(r"\s*hw:CARD=([^,\s]+)", line)
        if m:
            cards.add(m.group(1))
    return cards


def parse_journal_errors(journal_text: str) -> dict:
    counts = {"xruns": 0, "sync": 0}
    for line in journal_text.splitlines():
        low = line.lower()
        if "underrun" in low or "overrun" in low or "xrun" in low:
            counts["xruns"] += 1
        if "lost sync" in low or "resync" in low or "out of sync" in low or "sync error" in low:
            counts["sync"] += 1
    return counts


def parse_device_id(conf_text: str) -> str:
    m = re.search(r'airplay_device_id\s*=\s*"?([0-9A-Fa-fx:]+)"?', conf_text)
    return m.group(1) if m else ""


def is_zero_device_id(dev_id: str) -> bool:
    digits = re.sub(r"[^0-9A-Fa-f]", "", dev_id)
    return digits == "" or set(digits) <= {"0"}
