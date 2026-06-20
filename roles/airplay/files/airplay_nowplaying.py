#!/usr/bin/env python3
"""airplay-nowplaying — consume the shairport-sync metadata pipe and maintain a
small JSON snapshot of what is currently playing, for the dashboard to read.

Stdlib only. Reads the pipe forever (reopening across shairport restarts) and
writes /run/airplay/nowplaying.json (+ a cover-art file) whenever state changes.

Metadata wire format (one item):
  <item><type>HHHHHHHH</type><code>HHHHHHHH</code><length>N</length>
  <data encoding="base64">BASE64</data></item>
type/code are 4-char tags as 8 hex digits. 'core' items are DMAP track fields
(minm=title, asar=artist, asal=album); 'ssnc' items are shairport events
(pbeg/pend session, pvol volume, PICT cover art).
"""
from __future__ import annotations

import base64
import json
import os
import re
import time

PIPE = os.environ.get("AIRPLAY_METADATA_PIPE", "/run/shairport-sync/metadata-pipe")
STATE_DIR = os.environ.get("AIRPLAY_STATE_DIR", "/run/airplay")
STATE_FILE = os.path.join(STATE_DIR, "nowplaying.json")
COVER_FILE = os.path.join(STATE_DIR, "cover")

CORE = 0x636F7265
SSNC = 0x73736E63

# Upper bound on the read buffer. Cover-art PICT items carry a full JPEG/PNG
# base64-encoded inside a single <item>, which is routinely several MB, so the
# cap must sit well above any real cover (a 1 MB guard would drop them mid-stream).
MAX_BUF = 16 * 1024 * 1024

_ITEM_RE = re.compile(
    rb"<item><type>([0-9a-fA-F]{8})</type><code>([0-9a-fA-F]{8})</code>"
    rb"<length>(\d+)</length>"
    rb"(?:\s*<data encoding=\"base64\">\s*([A-Za-z0-9+/=\s]*?)</data>)?\s*</item>",
    re.S,
)


def code_to_str(code: int) -> str:
    """0x6d696e6d -> 'minm'."""
    return code.to_bytes(4, "big").decode("latin-1")


def trim_buffer(buf: bytes, max_bytes: int = MAX_BUF) -> bytes:
    """Bound buffer growth on a corrupt/garbage stream without discarding a
    legitimately large partial <item> still arriving (e.g. a multi-MB cover).

    Once the buffer exceeds the cap, drop everything before the last <item>
    start so a real in-progress item is preserved; if there is no <item> marker
    at all, the buffer is pure garbage and is dropped entirely.
    """
    if len(buf) <= max_bytes:
        return buf
    cut = buf.rfind(b"<item>")
    return buf[cut:] if cut != -1 else b""


def parse_items(buf: bytes):
    """Parse complete <item>..</item> records from buf.

    Returns (items, leftover) where items is a list of (type, code, payload)
    and leftover is the unparsed tail (a partial item still arriving).
    """
    items = []
    last = 0
    for m in _ITEM_RE.finditer(buf):
        typ = int(m.group(1), 16)
        code = int(m.group(2), 16)
        b64 = m.group(4)
        payload = base64.b64decode(re.sub(rb"\s", b"", b64)) if b64 else b""
        items.append((typ, code, payload))
        last = m.end()
    return items, buf[last:]


def parse_pvol(payload: bytes) -> dict:
    """'airplay_vol,actual_db,low_db,high_db' -> {percent, muted}.

    AirPlay volume is 0.0 (full) .. -30.0 (min); -144.0 means muted.
    """
    try:
        ap = float(payload.decode("utf-8", "replace").split(",")[0])
    except (ValueError, IndexError):
        return {"percent": 0, "muted": True}
    if ap <= -144.0:
        return {"percent": 0, "muted": True}
    pct = max(0, min(100, round((ap + 30.0) / 30.0 * 100)))
    return {"percent": pct, "muted": False}


def cover_ext(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return "bin"


def empty_state() -> dict:
    return {
        "active": False,
        "title": "",
        "artist": "",
        "album": "",
        "volume_percent": 0,
        "muted": False,
        "cover": None,
        "updated": 0.0,
    }


def apply_item(state: dict, typ: int, code: int, payload: bytes) -> bool:
    """Update state in place for one item. Returns True if state changed.

    Side effect: writes the cover-art file when a PICT item arrives.
    """
    changed = False
    if typ == CORE:
        tag = code_to_str(code)
        field = {"minm": "title", "asar": "artist", "asal": "album"}.get(tag)
        if field is not None:
            value = payload.decode("utf-8", "replace")
            if state.get(field) != value:
                state[field] = value
                changed = True
    elif typ == SSNC:
        tag = code_to_str(code)
        if tag == "pbeg":
            if not state["active"]:
                state["active"] = True
                changed = True
        elif tag == "pend":
            state.update(empty_state())
            changed = True
        elif tag == "pvol":
            vol = parse_pvol(payload)
            if (vol["percent"], vol["muted"]) != (state["volume_percent"], state["muted"]):
                state["volume_percent"] = vol["percent"]
                state["muted"] = vol["muted"]
                changed = True
        elif tag == "PICT" and payload:
            path = f"{COVER_FILE}.{cover_ext(payload)}"
            try:
                with open(path, "wb") as fh:
                    fh.write(payload)
                state["cover"] = os.path.basename(path)
                changed = True
            except OSError:
                pass
    return changed


def write_state(state: dict) -> None:
    state["updated"] = time.time()
    tmp = f"{STATE_FILE}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATE_FILE)


def run(pipe_path: str = PIPE) -> None:  # pragma: no cover - I/O loop
    os.makedirs(STATE_DIR, exist_ok=True)
    state = empty_state()
    write_state(state)
    buf = b""
    while True:
        try:
            with open(pipe_path, "rb") as pipe:
                while True:
                    chunk = pipe.read(4096)
                    if not chunk:
                        break  # writer (shairport) closed; reopen
                    buf += chunk
                    items, buf = parse_items(buf)
                    buf = trim_buffer(buf)  # runaway guard, cover-art safe
                    dirty = False
                    for typ, code, payload in items:
                        dirty |= apply_item(state, typ, code, payload)
                    if dirty:
                        write_state(state)
        except FileNotFoundError:
            time.sleep(2)  # pipe not created yet (shairport starting)
        except OSError:
            time.sleep(2)


if __name__ == "__main__":  # pragma: no cover
    run()
