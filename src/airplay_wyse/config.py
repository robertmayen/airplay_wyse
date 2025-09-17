"""Configuration rendering utilities."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = REPO_ROOT / "cfg" / "shairport-sync.minimal.conf.tmpl"
SHAIRPORT_CONF = Path("/etc/shairport-sync.conf")


@dataclass
class ShairportConfig:
    name: str
    device: str
    mixer: str | None = None
    interface: str | None = None
    hardware_address: str | None = None
    output_rate: int | None = None
    statistics: bool = False
    interpolation: str | None = None
    airplay_device_id: str | None = None

    def to_context(self) -> dict[str, Any]:
        return {
            "AIRPLAY_NAME": self.name,
            "ALSA_DEVICE": self.device,
            "ALSA_MIXER": self.mixer or "",
            "AVAHI_IFACE": self.interface or "",
            "HW_ADDR": self.hardware_address or "",
            "ALSA_OUTPUT_RATE": self.output_rate or "",
            "STATISTICS": "yes" if self.statistics else "",
            "INTERPOLATION": self.interpolation or "",
            "AIRPLAY_DEVICE_ID": self.airplay_device_id or "",
        }


OPTIONAL_KEYS = {
    "ALSA_MIXER": re.compile(r"^[\t ]*mixer_control_name"),
    "ALSA_OUTPUT_RATE": re.compile(r"^[\t ]*output_rate"),
    "INTERPOLATION": re.compile(r"^[\t ]*interpolation"),
    "AVAHI_IFACE": re.compile(r"^[\t ]*interface"),
    "HW_ADDR": re.compile(r"^[\t ]*hardware_address"),
    "STATISTICS": re.compile(r"^[\t ]*statistics"),
    "AIRPLAY_DEVICE_ID": re.compile(r"^[\t ]*airplay_device_id"),
}


def _strip_optional_lines(rendered: str, context: dict[str, Any]) -> str:
    lines = rendered.splitlines()
    filtered: list[str] = []
    for line in lines:
        drop = False
        for key, pattern in OPTIONAL_KEYS.items():
            if not context.get(key):
                if pattern.search(line):
                    drop = True
                    break
        if not drop:
            filtered.append(line)
    return "\n".join(filtered) + "\n"


def render_config(cfg: ShairportConfig, template: Path = DEFAULT_TEMPLATE) -> str:
    text = template.read_text(encoding="utf-8")
    context = cfg.to_context()
    for key, value in context.items():
        placeholder = f"{{{{{key}}}}}"
        text = text.replace(placeholder, str(value))
    return _strip_optional_lines(text, context)


def write_config(text: str, target: Path = SHAIRPORT_CONF) -> None:
    tmp = target.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
