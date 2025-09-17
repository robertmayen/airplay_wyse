"""ALSA policy helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import state, utils

ASOUND_CONF = Path("/etc/asound.conf")


@dataclass
class AlsaPolicy:
    device: str
    anchor_hz: int
    requires_soxr: bool
    mixer: str | None = None
    card: int | None = None
    card_id: str | None = None
    dev_num: int | None = None
    is_usb: bool | None = None
    changed: bool = False

    def to_state(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "anchor_hz": self.anchor_hz,
            "requires_soxr": self.requires_soxr,
            "mixer": self.mixer,
            "card": self.card,
            "card_id": self.card_id,
            "dev_num": self.dev_num,
            "is_usb": self.is_usb,
        }


STATE_KEY = "alsa_policy"


_DEVICE_RE = re.compile(r"card\s+(\d+):\s+([^\s,]+).*device\s+(\d+):")
_RATE_RE = re.compile(r"Rates:\s*([^\n]+)")
_INT_RE = re.compile(r"(\d{4,6})")


def _list_playback_devices() -> list[dict[str, Any]]:
    try:
        result = utils.run_cmd(["aplay", "-l"], capture_output=True, check=False)
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    devices: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        match = _DEVICE_RE.search(line)
        if match:
            card = int(match.group(1))
            card_id = match.group(2)
            dev = int(match.group(3))
            devices.append({"card": card, "card_id": card_id, "dev": dev})
    return devices


def _is_usb_card(card: int) -> bool:
    path = Path(f"/sys/class/sound/card{card}/device")
    return (path / "idVendor").exists() and (path / "idProduct").exists()


def _read_rates(card: int) -> set[int]:
    rates: set[int] = set()
    base = Path(f"/proc/asound/card{card}")
    if not base.exists():
        return rates
    for stream in base.glob("stream*"):
        try:
            content = stream.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = _RATE_RE.search(content)
        if not match:
            continue
        for token in _INT_RE.findall(match.group(1)):
            try:
                rates.add(int(token))
            except ValueError:
                continue
    return rates


def _choose_device(manual_device: str | None = None) -> tuple[str, int | None, int | None, str | None, bool | None]:
    if manual_device:
        match = re.match(r"hw:(\d+),(\d+)", manual_device)
        if match:
            card = int(match.group(1))
            dev = int(match.group(2))
            card_id = _read_card_id(card)
            return manual_device, card, dev, card_id, _is_usb_card(card)
        return manual_device, None, None, None, None

    devices = _list_playback_devices()
    if not devices:
        return "hw:0,0", None, None, None, None

    # Prefer USB devices first
    usb_devices = [d for d in devices if _is_usb_card(d["card"])]
    preferred = usb_devices[0] if usb_devices else devices[0]
    card = preferred["card"]
    dev = preferred["dev"]
    card_id = preferred.get("card_id")
    return f"hw:{card},{dev}", card, dev, card_id, _is_usb_card(card)


def _read_card_id(card: int) -> str | None:
    path = Path(f"/proc/asound/card{card}/id")
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _ensure_asound(device: str, card: int | None, dev: int | None) -> bool:
    lines = [
        "# Managed by AirPlay Wyse",
        "pcm.airplay_wyse_hw {",
        "    type hw",
        f"    card {card if card is not None else 0}",
        f"    device {dev if dev is not None else 0}",
        "}",
        "",
        "pcm.!default {",
        "    type plug",
        "    slave.pcm airplay_wyse_hw",
        "}",
        "",
        "ctl.!default {",
        "    type hw",
        f"    card {card if card is not None else 0}",
        "}",
        "",
    ]
    content = "\n".join(lines)
    if ASOUND_CONF.exists():
        try:
            existing = ASOUND_CONF.read_text(encoding="utf-8")
            if existing == content:
                return False
        except OSError:
            pass
    tmp = ASOUND_CONF.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(ASOUND_CONF)
    return True


def ensure_policy(manual_device: str | None = None) -> AlsaPolicy:
    data = state.load_state()
    cached = data.get(STATE_KEY, {})

    device, card, dev, card_id, is_usb = _choose_device(manual_device)
    rates = _read_rates(card) if card is not None else set()
    anchor = 44100 if 44100 in rates else 48000 if 48000 in rates else 44100
    requires_soxr = anchor == 48000 and 44100 not in rates

    policy = AlsaPolicy(
        device=device,
        anchor_hz=anchor,
        requires_soxr=requires_soxr,
        mixer=None,
        card=card,
        card_id=card_id,
        dev_num=dev,
        is_usb=is_usb,
    )

    changed = _ensure_asound(device, card, dev)
    policy.changed = changed or policy.to_state() != cached

    state.update_state({STATE_KEY: policy.to_state()})
    return policy
