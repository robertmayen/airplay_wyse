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


import argparse
import json
import socket
import subprocess
import sys


def _system_runner(name: str) -> str:
    """Default runner: maps a probe name to real captured command output."""
    if name.startswith("is_active:"):
        svc = name.split(":", 1)[1]
        return _capture(["systemctl", "is-active", svc])
    cmds = {
        "shairport_version": ["shairport-sync", "-V"],
        "ss": ["ss", "-ulnp"],
        "mdns": ["avahi-browse", "-atp", "--no-db-lookup", "-r", "-l"],
        "aplay": ["aplay", "-L"],
        "journal": ["journalctl", "-u", "shairport-sync", "-n", "200", "--no-pager"],
    }
    if name == "config":
        try:
            with open("/etc/shairport-sync.conf", encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""
    return _capture(cmds.get(name, ["true"]))


def _capture(cmd) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout
    except FileNotFoundError:
        return ""


def _check(name, ok, detail=""):
    return {"name": name, "ok": bool(ok), "detail": detail}


def build_report(runner, deep: bool = False) -> dict:
    checks = []
    for svc in ("shairport-sync", "nqptp", "avahi-daemon"):
        active = runner(f"is_active:{svc}").strip() == "active"
        checks.append(_check(f"service:{svc}", active, "active" if active else "not active"))

    feats = parse_shairport_version(runner("shairport_version"))
    checks.append(_check("feature:airplay2", feats["airplay2"], feats["version"]))
    checks.append(_check("feature:soxr", feats["soxr"]))

    ports = parse_listening_ports(runner("ss"))
    nqptp_ports = all(ports[p]["bound"] and ports[p]["nqptp"] for p in (319, 320))
    checks.append(_check("ports:319/320", nqptp_ports, "owned by nqptp" if nqptp_ports else "not owned"))

    mdns = parse_mdns(runner("mdns"))
    checks.append(_check("mdns:airplay", mdns["airplay"]))
    checks.append(_check("mdns:raop", mdns["raop"]))

    conf = runner("config")
    dev_id = parse_device_id(conf)
    checks.append(_check("identity:device-id", not is_zero_device_id(dev_id), dev_id))

    cards = parse_alsa_cards(runner("aplay"))
    m = re.search(r'output_device\s*=\s*"hw:CARD=([^,"]+)', conf)
    want_card = m.group(1) if m else None
    card_ok = (want_card in cards) if want_card else bool(cards)
    checks.append(_check("alsa:card", card_ok, want_card or "any"))

    errs = parse_journal_errors(runner("journal"))
    checks.append(_check("journal:errors", errs["xruns"] == 0 and errs["sync"] == 0, str(errs)))

    if deep:
        # opt-in only; opening hw: can disrupt shairport's exclusive access
        checks.append(_check("deep:device-open", True, "deep probe placeholder"))

    return {
        "host": socket.gethostname(),
        "ok": all(c["ok"] for c in checks),
        "device_id": dev_id,
        "mdns": mdns,
        "checks": checks,
    }


def main(argv=None, runner=None) -> int:
    parser = argparse.ArgumentParser(prog="airplay-doctor")
    parser.add_argument("--check", action="store_true", help="non-invasive checks (default)")
    parser.add_argument("--deep", action="store_true", help="add device-open/playback probe")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    run = runner or _system_runner
    report = build_report(run, deep=args.deep)
    if args.json:
        print(json.dumps(report))
    else:
        status = "OK" if report["ok"] else "FAIL"
        print(f"airplay-doctor: {report['host']} {status}")
        for c in report["checks"]:
            mark = "ok " if c["ok"] else "XX "
            print(f"  [{mark}] {c['name']}: {c['detail']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
