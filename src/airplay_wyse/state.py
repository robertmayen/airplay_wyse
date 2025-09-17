"""Persistent state helpers for AirPlay Wyse."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_DIR = Path("/var/lib/airplay_wyse")
CONFIG_STATE_FILE = STATE_DIR / "config.json"

DEFAULT_STATE: dict[str, Any] = {
    "config": {
        "name": None,
        "device": None,
        "mixer": None,
        "interface": None,
        "hardware_address": None,
        "airplay_device_id": None,
        "output_rate": None,
        "statistics": False,
        "interpolation": None,
    },
    "alsa_policy": {},
    "pipewire_policy": {},
    "identity": {},
}


def _merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result


def load_state(default: dict[str, Any] | None = None) -> dict[str, Any]:
    baseline = _merge(DEFAULT_STATE, default or {})
    if not CONFIG_STATE_FILE.exists():
        return baseline
    try:
        raw = CONFIG_STATE_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return _merge(baseline, data)
    except (json.JSONDecodeError, OSError):
        pass
    return baseline


def save_state(data: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(CONFIG_STATE_FILE)


def update_state(updates: dict[str, Any]) -> dict[str, Any]:
    current = load_state()
    merged = _merge(current, updates)
    save_state(merged)
    return merged
