#!/usr/bin/env python3
"""airplay-doctor — health checks for one AirPlay 2 endpoint (stdlib only).

  airplay-doctor           human-readable report; exit 1 if any check fails
  airplay-doctor --json    the same report as JSON
  airplay-doctor --deep    also prove the DAC is usable (held by shairport, or openable)

Every check only reads state. Run it as root for the complete picture: socket
owners (`ss -p`) and the journal are hidden from unprivileged users, and those
checks then report "unknown" instead of failing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass

CONF_PATH = "/etc/shairport-sync.conf"
CORE_SERVICES = ("shairport-sync", "nqptp", "avahi-daemon")
METADATA_SERVICES = ("airplay-nowplaying", "airplay-dashboard")
PROBE_TIMEOUT = 20  # seconds; `avahi-browse -r` on a busy LAN is the slowest probe
JOURNAL_FAIL = 30  # xrun/sync lines per hour that turn a warning into a failure

OK, WARN, FAIL, UNKNOWN = "ok", "warn", "fail", "unknown"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""

    def as_dict(self) -> dict:
        # "ok" stays for consumers of the original format (dashboard, doctor.yml).
        # Only a hard failure makes a check not-ok; warn/unknown are informational.
        return {"name": self.name, "ok": self.status != FAIL, "status": self.status, "detail": self.detail}


# --- pure parsers (unit-tested) ---------------------------------------------


def parse_shairport_version(text: str) -> dict:
    """Parse `shairport-sync -V`, e.g. '5.6.2-AirPlay2-smi11-OpenSSL-Avahi-ALSA-soxr-metadata-dbus'.

    Token-tolerant: whitespace is collapsed and case ignored, so 'AirPlay 2'
    and 'AirPlay2' both count.
    """
    compact = re.sub(r"\s+", "", text).lower()
    version = re.match(r"\s*([0-9][0-9A-Za-z.~+]*)", text)
    smi = re.search(r"smi(\d+)", compact)
    return {
        "version": version.group(1) if version else "",
        "airplay2": "airplay2" in compact,
        "soxr": "soxr" in compact,
        "alac": "alac" in compact,
        "metadata": "metadata" in compact,
        "dbus": "dbus" in compact,
        "smi": int(smi.group(1)) if smi else None,
    }


def parse_nqptp_version(text: str) -> dict:
    """'Version: 1.2.9. Shared Memory Interface Version: smi11.' -> version + smi."""
    version = re.search(r"Version:\s*(.+?)\.\s+Shared", text) or re.match(r"\s*(\S+)", text)
    smi = re.search(r"smi(\d+)", text)
    return {
        "version": version.group(1) if version else "",
        "smi": int(smi.group(1)) if smi else None,
    }


def parse_listening_ports(ss_output: str, ports=(319, 320)) -> dict:
    """From `ss -Hulnp`, report which target UDP ports are bound and whether by nqptp."""
    result = {p: {"bound": False, "nqptp": False} for p in ports}
    for line in ss_output.splitlines():
        for p in ports:
            if re.search(rf"[:.]{p}\b", line):
                result[p]["bound"] = True
                if "nqptp" in line:
                    result[p]["nqptp"] = True
    return result


def _avahi_unescape(value: str) -> str:
    # avahi-browse -p escapes service names: '\032' (decimal) for ' ', '\.' for '.'.
    return re.sub(
        r"\\(\d{3}|.)", lambda m: chr(int(m.group(1))) if m.group(1).isdigit() else m.group(1), value
    )


def parse_avahi(output: str) -> list[dict]:
    """Resolved ('=') records of `avahi-browse -tpr` as {name, type, host, txt}."""
    records = []
    for line in output.splitlines():
        if not line.startswith("="):
            continue
        fields = line.split(";", 9)
        if len(fields) < 9:
            continue
        txt = {}
        if len(fields) == 10:
            for item in re.findall(r'"((?:[^"\\]|\\.)*)"', fields[9]):
                key, _, value = item.partition("=")
                txt[key.lower()] = value
        records.append({"name": _avahi_unescape(fields[3]), "type": fields[4], "host": fields[6], "txt": txt})
    return records


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


def parse_output_device(conf_text: str) -> str:
    m = re.search(r'output_device\s*=\s*"([^"]+)"', conf_text)
    return m.group(1) if m else ""


def parse_output_card(conf_text: str) -> tuple[str, int] | None:
    """('Device', 0) from output_device = "hw:CARD=Device,DEV=0" (hw: or plughw:)."""
    m = re.search(r'output_device\s*=\s*"(?:plug)?hw:CARD=([^,"]+)(?:,DEV=(\d+))?', conf_text)
    return (m.group(1), int(m.group(2) or 0)) if m else None


def parse_conf_name(conf_text: str) -> str:
    m = re.search(r'^\s*name\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', conf_text, re.M)
    return re.sub(r"\\(.)", r"\1", m.group(1)) if m else ""


def normalize_device_id(value: str) -> str:
    """Any spelling ('0x5CAAFD112233L', '5c:aa:fd:11:22:33') -> '5C:AA:FD:11:22:33'."""
    digits = re.sub(r"[^0-9A-Fa-f]", "", re.sub(r"^\s*0x|L\s*$", "", value.strip()))
    if not digits:
        return ""
    digits = digits.upper().zfill(12)[-12:]
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def parse_device_id(conf_text: str) -> str:
    """The pinned general.airplay_device_id, normalized; '' when not pinned."""
    m = re.search(r'^\s*airplay_device_id\s*=\s*"?([0-9A-Fa-fxX:]+L?)"?\s*;', conf_text, re.M)
    return normalize_device_id(m.group(1)) if m else ""


def is_zero_device_id(dev_id: str) -> bool:
    digits = re.sub(r"[^0-9A-Fa-f]", "", dev_id)
    return digits == "" or set(digits) <= {"0"}


def parse_pcm_status(text: str) -> dict:
    """/proc/asound/<card>/pcm<N>p/sub0/status -> {state, owner_pid}."""
    if text.strip() == "closed":
        return {"state": "closed", "owner_pid": None}
    state = re.search(r"state:\s*(\S+)", text)
    owner = re.search(r"owner_pid\s*:\s*(\d+)", text)
    return {
        "state": state.group(1) if state else "unknown",
        "owner_pid": int(owner.group(1)) if owner else None,
    }


def metadata_enabled(conf_text: str) -> bool:
    return bool(re.search(r'^\s*metadata\s*=\s*\{[^}]*\benabled\s*=\s*"yes"', conf_text, re.M | re.S))


# --- system probes (replaced by a fake in tests) ----------------------------


class Probes:
    """Every read the doctor makes of the live system, each with a timeout.

    A method returns None when its tool is missing, times out or the file
    cannot be read, so the check can say so instead of crashing.
    """

    def __init__(self, timeout: float = PROBE_TIMEOUT):
        self.timeout = timeout

    def _run(self, cmd: list[str], merge_stderr: bool = False) -> str | None:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout + r.stderr if merge_stderr else r.stdout

    @staticmethod
    def _read(path: str) -> str | None:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return None

    def is_root(self) -> bool:
        return os.geteuid() == 0

    def config(self) -> str | None:
        return self._read(CONF_PATH)

    def service_states(self, names) -> dict:
        lines = (self._run(["systemctl", "is-active", *names]) or "").split()
        return {n: lines[i] if i < len(lines) else "unknown" for i, n in enumerate(names)}

    def shairport_version(self) -> str | None:
        return self._run(["shairport-sync", "-V"], merge_stderr=True)

    def nqptp_version(self) -> str | None:
        return self._run(["nqptp", "-V"], merge_stderr=True)

    def udp_sockets(self) -> str | None:
        return self._run(["ss", "-Hulnp"])

    def mdns(self, service_type: str) -> str | None:
        return self._run(["avahi-browse", "-tpr", "--no-db-lookup", service_type])

    def alsa_pcms(self) -> str | None:
        return self._run(["aplay", "-L"])

    def journal(self) -> str | None:
        # Current boot, last hour: a historical xrun must not fail health forever.
        return self._run(
            ["journalctl", "-u", "shairport-sync", "-b", "--since", "-1h", "-n", "500", "-q", "--no-pager"]
        )

    def pcm_status(self, card: str, device: int) -> str | None:
        return self._read(f"/proc/asound/{card}/pcm{device}p/sub0/status")

    def process_name(self, pid: int) -> str:
        return (self._read(f"/proc/{pid}/comm") or "?").strip()

    def open_device(self, device: str) -> str:
        # aplay prints the hw params to stderr; merged so the caller sees them.
        return self._run(["aplay", "-D", device, "--dump-hw-params", "-d", "1", "/dev/zero"], True) or ""


# --- the report ---------------------------------------------------------------


def _same_name(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


def _mdns_checks(p, name: str) -> tuple[list[Check], dict, str]:
    raw = {t: p.mdns(t) for t in ("_airplay._tcp", "_raop._tcp")}
    if any(v is None for v in raw.values()):
        missing = [Check("mdns:airplay", FAIL, "avahi-browse unavailable"), Check("mdns:raop", FAIL, "")]
        return missing, {"airplay": False, "raop": False}, ""
    records = parse_avahi(raw["_airplay._tcp"]) + parse_avahi(raw["_raop._tcp"])
    airplay = [r for r in records if r["type"] == "_airplay._tcp" and _same_name(r["name"], name)]
    # RAOP instance names are '<device-id-hex>@<name>'.
    raop = [r for r in records if r["type"] == "_raop._tcp" and _same_name(r["name"].split("@", 1)[-1], name)]
    advertised = normalize_device_id(airplay[0]["txt"].get("deviceid", "")) if airplay else ""
    checks = [
        Check(
            "mdns:airplay",
            OK if airplay else FAIL,
            f"'{name}' advertised" if airplay else f"'{name}' not found",
        ),
        Check("mdns:raop", OK if raop else FAIL, f"'{name}' advertised" if raop else f"'{name}' not found"),
    ]
    return checks, {"airplay": bool(airplay), "raop": bool(raop)}, advertised


def _identity_check(pinned: str, advertised: str) -> Check:
    if pinned and is_zero_device_id(pinned):
        return Check("identity:device-id", FAIL, "pinned device-id is all zeros")
    if advertised:
        if is_zero_device_id(advertised):
            return Check("identity:device-id", FAIL, "advertised device-id is all zeros")
        if pinned and pinned != advertised:
            return Check("identity:device-id", FAIL, f"advertised {advertised}, pinned {pinned}")
        return Check("identity:device-id", OK, advertised + (" (pinned)" if pinned else " (from MAC)"))
    return Check(
        "identity:device-id", UNKNOWN, f"pinned {pinned}, not seen on mDNS" if pinned else "not advertised"
    )


def _deep_check(p, conf: str) -> Check:
    target = parse_output_card(conf)
    if not target:
        return Check("deep:device", FAIL, "no output_device in config")
    card, device = target
    status = p.pcm_status(card, device)
    if status is None:
        return Check("deep:device", FAIL, f"card {card} device {device} not present")
    pcm = parse_pcm_status(status)
    if pcm["state"] == "closed":
        out = p.open_device(parse_output_device(conf))
        if "HW Params of device" in out:
            return Check("deep:device", OK, f"{card}: opened and released")
        return Check("deep:device", FAIL, (out.strip().splitlines() or ["open failed"])[-1])
    owner = p.process_name(pcm["owner_pid"]) if pcm["owner_pid"] else "?"
    if owner == "shairport-sync":
        return Check("deep:device", OK, f"{card}: held by shairport-sync ({pcm['state']})")
    return Check("deep:device", FAIL, f"{card}: held by {owner} (pid {pcm['owner_pid']})")


def build_report(p, deep: bool = False, journal_fail: int = JOURNAL_FAIL) -> dict:
    checks: list[Check] = []
    conf = p.config() or ""
    root = p.is_root()

    services = CORE_SERVICES + (METADATA_SERVICES if metadata_enabled(conf) else ())
    states = p.service_states(services)
    for svc in services:
        checks.append(
            Check(f"service:{svc}", OK if states.get(svc) == "active" else FAIL, states.get(svc, ""))
        )

    sps = parse_shairport_version(p.shairport_version() or "")
    nq = parse_nqptp_version(p.nqptp_version() or "")
    checks.append(
        Check("feature:airplay2", OK if sps["airplay2"] else FAIL, sps["version"] or "no -V output")
    )
    checks.append(Check("feature:soxr", OK if sps["soxr"] else FAIL))
    if metadata_enabled(conf):
        has = sps["metadata"] and sps["dbus"]
        checks.append(
            Check("feature:metadata", OK if has else FAIL, "metadata+dbus" if has else "build lacks them")
        )
    if sps["smi"] is None or nq["smi"] is None:
        checks.append(Check("nqptp:interface", UNKNOWN, "smi version not reported"))
    elif sps["smi"] == nq["smi"]:
        checks.append(Check("nqptp:interface", OK, f"smi{nq['smi']}"))
    else:
        checks.append(
            Check("nqptp:interface", FAIL, f"shairport speaks smi{sps['smi']}, nqptp smi{nq['smi']}")
        )

    ss = p.udp_sockets()
    if ss is None:
        checks.append(Check("ports:319/320", FAIL, "ss unavailable"))
    else:
        ports = parse_listening_ports(ss)
        bound = all(v["bound"] for v in ports.values())
        owned = all(v["nqptp"] for v in ports.values())
        if bound and owned:
            checks.append(Check("ports:319/320", OK, "owned by nqptp"))
        elif bound and not root:
            checks.append(Check("ports:319/320", UNKNOWN, "bound; owner hidden (run as root)"))
        else:
            checks.append(Check("ports:319/320", FAIL, "bound by another process" if bound else "not bound"))

    name = parse_conf_name(conf)
    mdns_checks, mdns, advertised = _mdns_checks(p, name)
    checks.extend(mdns_checks)
    pinned = parse_device_id(conf)
    checks.append(_identity_check(pinned, advertised))

    cards = parse_alsa_cards(p.alsa_pcms() or "")
    target = parse_output_card(conf)
    want = target[0] if target else None
    checks.append(
        Check("alsa:card", OK if want and want in cards else FAIL, want or "no output_device in config")
    )

    if not root:
        checks.append(Check("journal:errors", UNKNOWN, "needs root"))
    else:
        errs = parse_journal_errors(p.journal() or "")
        total = errs["xruns"] + errs["sync"]
        status = FAIL if total >= journal_fail else WARN if total else OK
        checks.append(
            Check("journal:errors", status, f"last hour: {errs['xruns']} xruns, {errs['sync']} sync")
        )

    if deep:
        checks.append(_deep_check(p, conf))

    return {
        "host": socket.gethostname(),
        "name": name,
        "ok": all(c.status != FAIL for c in checks),
        "device_id": advertised or pinned,
        "versions": {"shairport": sps["version"], "nqptp": nq["version"]},
        "mdns": mdns,
        "generated": time.time(),
        "checks": [c.as_dict() for c in checks],
    }


MARKS = {OK: " ok ", WARN: "WARN", FAIL: "FAIL", UNKNOWN: " ?? "}


def main(argv=None, probes=None) -> int:
    parser = argparse.ArgumentParser(prog="airplay-doctor", description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="non-invasive checks (the default)")
    parser.add_argument("--deep", action="store_true", help="also prove the DAC is usable")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--journal-fail",
        type=int,
        default=JOURNAL_FAIL,
        metavar="N",
        help="xrun/sync lines per hour that fail",
    )
    args = parser.parse_args(argv)
    report = build_report(probes or Probes(), deep=args.deep, journal_fail=args.journal_fail)
    if args.json:
        print(json.dumps(report))
    else:
        print(f"airplay-doctor: {report['host']} '{report['name']}' {'OK' if report['ok'] else 'FAIL'}")
        for c in report["checks"]:
            print(f"  [{MARKS[c['status']]}] {c['name']}: {c['detail']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
