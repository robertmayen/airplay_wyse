"""Identity management utilities."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import state, utils

IDENTITY_FILE = Path("/var/lib/airplay_wyse/instance.json")
SHAIRPORT_STATE_DIRS = [
    Path("/var/lib/shairport-sync"),
    Path("/var/cache/shairport-sync"),
    Path("/var/lib/shairport"),
    Path("/var/cache/shairport"),
]


@dataclass
class IdentityResult:
    mac: str
    interface: str | None
    changed: bool
    synthetic: bool


class IdentityError(RuntimeError):
    """Raised when identity cannot be ensured."""


ZERO_MAC = "00:00:00:00:00:00"


def _read_machine_id() -> str:
    try:
        return Path("/etc/machine-id").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise IdentityError("machine-id unavailable") from exc


def _hostname() -> str:
    return os.uname().nodename.split(".")[0]


def _interfaces() -> list[str]:
    sys_class = Path("/sys/class/net")
    if not sys_class.exists():
        return []
    return sorted(p.name for p in sys_class.iterdir() if p.is_dir())


def _read_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _iface_operstate(iface: str) -> str | None:
    return _read_file(Path(f"/sys/class/net/{iface}/operstate"))


def _iface_carrier(iface: str) -> str | None:
    return _read_file(Path(f"/sys/class/net/{iface}/carrier"))


def _iface_mac(iface: str) -> str | None:
    value = _read_file(Path(f"/sys/class/net/{iface}/address"))
    if value:
        return value.lower()
    return None


def _choose_iface(explicit: str | None = None) -> str | None:
    if explicit and Path(f"/sys/class/net/{explicit}").exists():
        return explicit
    # default route via ip route
    try:
        result = utils.run_cmd(["ip", "route"], capture_output=True)
        for line in result.stdout.splitlines():
            if line.startswith("default "):
                parts = line.split()
                if "dev" in parts:
                    idx = parts.index("dev")
                    cand = parts[idx + 1]
                    if Path(f"/sys/class/net/{cand}").exists():
                        return cand
    except utils.CommandError:
        pass
    # prefer up interfaces with carrier
    for iface in _interfaces():
        if iface == "lo":
            continue
        if _iface_operstate(iface) == "up" and _iface_carrier(iface) == "1":
            return iface
    # fallback to any up interface
    for iface in _interfaces():
        if iface == "lo":
            continue
        if _iface_operstate(iface) == "up":
            return iface
    # fallback to first non-loopback
    for iface in _interfaces():
        if iface != "lo":
            return iface
    return None


def _synthetic_mac(machine_id: str) -> str:
    digest = hashlib.sha256(machine_id.encode("utf-8")).hexdigest()
    first_byte = int(digest[:2], 16)
    first_byte = (first_byte | 0x02) & 0xFE
    rest = digest[2:12]
    mac_hex = f"{first_byte:02x}{rest}"
    return ":".join(mac_hex[i : i + 2] for i in range(0, 12, 2))


def _airplay_device_id_from_mac(mac: str) -> str:
    hex_mac = mac.replace(":", "").upper()
    return f"0x{hex_mac}L"


def _mac_suffix(mac: str) -> str:
    parts = mac.split(":")
    if len(parts) >= 2:
        return (parts[-2] + parts[-1]).upper()
    return mac.replace(":", "").upper()[-4:]


def _default_name(mac: str | None) -> str:
    if mac:
        return f"Wyse DAC-{_mac_suffix(mac)}"
    return "Wyse DAC"


def _clear_shairport_state() -> None:
    utils.run_cmd(["systemctl", "stop", "shairport-sync.service"], check=False)
    for directory in SHAIRPORT_STATE_DIRS:
        try:
            if directory.exists():
                shutil.rmtree(directory)
        except OSError:
            pass
    # Remove service user's XDG dirs if resolvable
    try:
        info = utils.run_cmd([
            "systemctl",
            "show",
            "-p",
            "User",
            "shairport-sync.service",
        ], capture_output=True, check=False)
        user_line = info.stdout.strip()
        if user_line.startswith("User="):
            user = user_line.split("=", 1)[1]
            home = Path("/home") / user
            if home.exists():
                for sub in [
                    home / ".config" / "shairport-sync",
                    home / ".local" / "share" / "shairport-sync",
                    home / ".cache" / "shairport-sync",
                ]:
                    try:
                        if sub.exists():
                            shutil.rmtree(sub)
                    except OSError:
                        pass
    except utils.CommandError:
        pass


def _load_identity_record() -> dict[str, Any]:
    if not IDENTITY_FILE.exists():
        return {}
    try:
        return json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_identity_record(data: dict[str, Any]) -> None:
    IDENTITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = IDENTITY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(IDENTITY_FILE)


def ensure_identity(force: bool = False) -> IdentityResult:
    data = state.load_state()
    config = data.get("config", {})

    env_iface = (
        os.environ.get("AIRPLAY_WYSE_IFACE")
        or os.environ.get("AIRPLAY_WYSE_INTERFACE")
        or os.environ.get("AVAHI_IFACE")
    )
    iface = _choose_iface(env_iface or config.get("interface"))

    machine_id = _read_machine_id()
    mac = config.get("hardware_address") or (iface and _iface_mac(iface)) or ZERO_MAC
    synthetic = False
    if not mac or mac == ZERO_MAC:
        mac = _synthetic_mac(machine_id)
        synthetic = True
    mac = mac.lower()

    airplay_id = _airplay_device_id_from_mac(mac)

    name = config.get("name") or _default_name(mac if not synthetic else None)
    if name.strip().lower() == "wyse dac":
        name = _default_name(mac if not synthetic else None)

    config_changed = False
    def _set(key: str, value: Any) -> None:
        nonlocal config_changed
        if config.get(key) != value:
            config[key] = value
            config_changed = True

    _set("interface", iface)
    _set("hardware_address", mac)
    _set("airplay_device_id", airplay_id)
    _set("name", name)

    identity_record = _load_identity_record()
    fingerprint = {
        "machine_id": machine_id,
        "host": _hostname(),
        "mac": mac,
    }
    previous_fp = {
        "machine_id": identity_record.get("machine_id"),
        "host": identity_record.get("host"),
        "mac": identity_record.get("mac"),
    }
    changed = force or fingerprint != previous_fp

    if changed:
        _clear_shairport_state()
        identity_record = {
            **fingerprint,
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        _save_identity_record(identity_record)

    if config_changed or changed:
        state.update_state({"config": config, "identity": identity_record})

    return IdentityResult(mac=mac, interface=iface, changed=changed, synthetic=synthetic)
