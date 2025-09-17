"""PipeWire policy helpers."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import state

CONF_DIR = Path("/etc/pipewire/pipewire.conf.d")
CONF_FILE = CONF_DIR / "90-airplay_wyse.conf"
ALLOWED_RATES = (44100, 48000, 88200, 96000)


@dataclass
class PipeWirePolicy:
    present: bool
    changed: bool
    force_rate: int | None

    def to_state(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "changed": self.changed,
            "force_rate": self.force_rate,
        }


def _pipewire_present() -> bool:
    for candidate in ("pw-cli", "pw-dump", "pipewire"):
        if shutil.which(candidate):
            return True
    return Path("/etc/pipewire").exists()


def _render(force_rate: int | None) -> str:
    lines = [
        "# Managed by AirPlay Wyse",
        "context.properties = {",
        "  default.clock.allowed-rates = [" + " ".join(str(r) for r in ALLOWED_RATES) + " ]",
    ]
    if force_rate is not None:
        lines.append(f"  default.clock.force-rate = {force_rate}")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def ensure_policy(force_rate: int | None = None) -> PipeWirePolicy:
    present = _pipewire_present()
    changed = False

    if not present:
        policy = PipeWirePolicy(present=False, changed=False, force_rate=None)
        state.update_state({"pipewire_policy": policy.to_state()})
        return policy

    if force_rate is not None and force_rate not in ALLOWED_RATES:
        raise ValueError("force_rate must be one of 44100, 48000, 88200, 96000")

    CONF_DIR.mkdir(parents=True, exist_ok=True)
    content = _render(force_rate)
    if CONF_FILE.exists():
        try:
            existing = CONF_FILE.read_text(encoding="utf-8")
            if existing == content:
                policy = PipeWirePolicy(present=True, changed=False, force_rate=force_rate)
                state.update_state({"pipewire_policy": policy.to_state()})
                return policy
        except OSError:
            pass

    tmp = CONF_FILE.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(CONF_FILE)
    changed = True

    policy = PipeWirePolicy(present=True, changed=changed, force_rate=force_rate)
    state.update_state({"pipewire_policy": policy.to_state()})
    return policy
