"""Filters for the airplay role's templates: correct quoting for each target
format, and the AirPlay device-id / version-pin helpers.

Plain functions, so tests can exercise them without Ansible.
"""

from __future__ import annotations

import re

try:
    from ansible.errors import AnsibleFilterError
except ImportError:  # pragma: no cover - only when imported outside Ansible
    AnsibleFilterError = ValueError


def airplay_libconfig(value) -> str:
    """Escape for a libconfig double-quoted string (shairport-sync.conf)."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def airplay_systemd_quoted(value) -> str:
    """Escape for a double-quoted systemd value, e.g. Environment="K=<here>".

    Inside quotes systemd applies C escapes; specifiers (%x) are expanded in
    both quoted and unquoted values.
    """
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")


def airplay_systemd_plain(value) -> str:
    """Escape for an unquoted systemd value such as Description=."""
    return str(value).replace("%", "%%")


def airplay_device_id(value) -> str:
    """Any spelling of a 48-bit id -> shairport's libconfig int64 '0x5CAAFD112233L'.

    Accepts '5C:AA:FD:11:22:33', '5caafd112233', '0x5CAAFD112233' or '0x5CAAFD112233L'.
    """
    raw = re.sub(r"^\s*0[xX]|[lL]\s*$", "", str(value).strip())
    digits = re.sub(r"[:\-\s]", "", raw)
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", digits):
        raise AnsibleFilterError(f"airplay_device_id must be 12 hex digits (a MAC), got {value!r}")
    return f"0x{digits.upper()}L"


def airplay_is_pinned(output, version, commit="") -> bool:
    """True if a `-V` output names the pinned build.

    shairport-sync prints '<version>-AirPlay2-...', nqptp 'Version: <version>. ...'.
    Builds from a git checkout may print a `git describe` string instead, which
    still carries the commit as 'g<sha7>'.
    """
    text = str(output).strip()
    m = re.search(r"Version:\s*(\S+?)\.?\s", text + " ")
    first = m.group(1) if m else (text.split() or [""])[0]
    if first == version or first.startswith(f"{version}-"):
        return True
    return bool(commit) and f"g{str(commit)[:7]}" in text


class FilterModule:
    def filters(self):
        return {
            "airplay_libconfig": airplay_libconfig,
            "airplay_systemd_quoted": airplay_systemd_quoted,
            "airplay_systemd_plain": airplay_systemd_plain,
            "airplay_device_id": airplay_device_id,
            "airplay_is_pinned": airplay_is_pinned,
        }
