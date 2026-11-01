#!/usr/bin/env python3
"""airplay-nowplaying — consume the shairport-sync metadata pipe and keep a
small JSON snapshot of what is playing, for the dashboard to read.

Stdlib only. Reads the FIFO forever (reopening across shairport restarts) and
writes /run/airplay/nowplaying.json (+ a cover-art file) whenever state changes.

Metadata wire format (one item; identical in shairport-sync 4.x and 5.x):
  <item><type>HHHHHHHH</type><code>HHHHHHHH</code><length>N</length>
  <data encoding="base64">BASE64</data></item>
type/code are 4-char tags as 8 hex digits. 'core' items are DMAP track fields
(minm=title, asar=artist, asal=album); 'ssnc' items are shairport events
(pbeg/pend session, prsm resume, pvol volume, PICT cover art).
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import os
import re
import select
import time

PIPE = os.environ.get("AIRPLAY_METADATA_PIPE", "/run/shairport-sync/metadata-pipe")
STATE_DIR = os.environ.get("AIRPLAY_STATE_DIR", "/run/airplay")
STATE_FILE = os.path.join(STATE_DIR, "nowplaying.json")
COVER_EXTS = ("jpg", "png", "bin")

CORE = 0x636F7265
SSNC = 0x73736E63

READ_SIZE = 64 * 1024
# Largest single item buffered. Cover art arrives as ONE base64 item that is
# routinely several MB; anything beyond this without a closing tag is garbage.
MAX_ITEM = 32 * 1024 * 1024

_HEAD_RE = re.compile(
    rb"<item><type>([0-9a-fA-F]{8})</type><code>([0-9a-fA-F]{8})</code><length>(\d+)</length>"
)
_END = b"</item>"
_DATA_OPEN = b'<data encoding="base64">'


def code_to_str(code: int) -> str:
    """0x6d696e6d -> 'minm'."""
    return code.to_bytes(4, "big").decode("latin-1")


def parse_item(raw: bytes) -> tuple[int, int, bytes] | None:
    """One complete '<item>...</item>' -> (type, code, payload), or None if malformed."""
    head = _HEAD_RE.match(raw)
    if not head:
        return None
    payload = b""
    start = raw.find(_DATA_OPEN, head.end())
    if start != -1:
        end = raw.rfind(b"</data>")
        try:
            # b64decode (non-validating) skips the newlines shairport inserts.
            payload = base64.b64decode(raw[start + len(_DATA_OPEN) : end])
        except (binascii.Error, ValueError):
            return None
    return int(head.group(1), 16), int(head.group(2), 16), payload


class ItemParser:
    """Incremental parser for the metadata stream, linear in the input size.

    The closing tag is searched only from where the previous search stopped,
    so a multi-MB cover arriving in small reads is scanned once — not once per
    read, as a regex over the whole buffer would (quadratic: ~1 min per 3 MB).
    """

    def __init__(self, max_item: int = MAX_ITEM):
        self.max_item = max_item
        self.reset()

    def reset(self) -> None:
        self.buf = bytearray()
        self.scan_from = 0

    def feed(self, chunk: bytes) -> list[tuple[int, int, bytes]]:
        self.buf += chunk
        items = []
        while True:
            end = self.buf.find(_END, self.scan_from)
            if end == -1:
                # A closing tag may straddle two reads: re-scan its length-1 tail.
                self.scan_from = max(0, len(self.buf) - len(_END) + 1)
                break
            stop = end + len(_END)
            start = self.buf.rfind(b"<item>", 0, end)
            if start != -1:
                item = parse_item(bytes(self.buf[start:stop]))
                if item:
                    items.append(item)
            del self.buf[:stop]
            self.scan_from = 0
        if len(self.buf) > self.max_item:  # runaway: no closing tag in sight
            self.reset()
        return items


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
        "cover_rev": 0,  # changes per image; the dashboard's cache-buster
        "updated": 0.0,
    }


def save_cover(payload: bytes, state_dir: str = STATE_DIR) -> str:
    """Write cover art atomically (readers never see a half-written image) and
    drop covers of the other formats so a stale one can't be served."""
    ext = cover_ext(payload)
    name = f"cover.{ext}"
    path = os.path.join(state_dir, name)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(payload)
    os.replace(tmp, path)
    for other in COVER_EXTS:
        if other != ext:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(os.path.join(state_dir, f"cover.{other}"))
    return name


TRACK_FIELDS = {"minm": "title", "asar": "artist", "asal": "album"}


def apply_item(state: dict, typ: int, code: int, payload: bytes, state_dir: str = STATE_DIR) -> bool:
    """Update state in place for one item. Returns True if state changed.

    Side effect: writes the cover-art file when a PICT item arrives.
    """
    before = dict(state)
    tag = code_to_str(code)
    if typ == CORE and tag in TRACK_FIELDS:
        field = TRACK_FIELDS[tag]
        value = payload.decode("utf-8", "replace")
        if state[field] != value:
            state[field] = value
            # New track: its art (if any) follows; never show the previous cover.
            state["cover"] = None
        # Track metadata only flows during a session: also covers a reader that
        # (re)started mid-session and missed 'pbeg'.
        state["active"] = True
    elif typ == SSNC:
        if tag in ("pbeg", "prsm"):
            state["active"] = True
        elif tag == "pend":
            state.update(empty_state())
        elif tag == "pvol":
            vol = parse_pvol(payload)
            state["volume_percent"], state["muted"] = vol["percent"], vol["muted"]
            state["active"] = True
        elif tag == "PICT" and payload:
            try:
                state["cover"] = save_cover(payload, state_dir)
            except OSError:
                return state != before
            # Same file name, new image. Time-based so it stays unique across
            # sessions and reader restarts (browsers cache by URL).
            state["cover_rev"] = time.time_ns() // 1_000_000
            return True
    return state != before


def write_state(state: dict, state_file: str = STATE_FILE) -> None:
    state["updated"] = time.time()
    tmp = f"{state_file}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    os.replace(tmp, state_file)


def open_fifo(path: str) -> int | None:
    """Open the FIFO without blocking for a writer (None if it doesn't exist yet).

    Holding a non-blocking read end open means shairport's own non-blocking
    open-for-write always finds a reader.
    """
    try:
        return os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except FileNotFoundError:
        return None


def _same_fifo(path: str, ino: int) -> bool:
    try:
        return os.stat(path).st_ino == ino
    except OSError:
        return False


def pump(
    fd: int,
    path: str,
    parser: ItemParser,
    state: dict,
    idle_timeout: float = 5.0,
    state_dir: str = STATE_DIR,
    state_file: str = STATE_FILE,
) -> None:
    """Read items from fd until the writer goes away or the FIFO at `path` is
    replaced (shairport recreated it), then return so the caller reopens."""
    ino = os.fstat(fd).st_ino
    while True:
        ready, _, _ = select.select([fd], [], [], idle_timeout)
        if not ready:
            if not _same_fifo(path, ino):
                return  # we hold an orphaned FIFO; the live one is a new inode
            continue
        try:
            chunk = os.read(fd, READ_SIZE)
        except BlockingIOError:
            continue
        if not chunk:
            return  # all writers closed: shairport stopped or restarted
        dirty = False
        for typ, code, payload in parser.feed(chunk):
            dirty |= apply_item(state, typ, code, payload, state_dir)
        if dirty:
            write_state(state, state_file)


def run(pipe_path: str = PIPE) -> None:  # pragma: no cover - I/O loop
    os.makedirs(STATE_DIR, exist_ok=True)
    state = empty_state()
    write_state(state)
    parser = ItemParser()
    while True:
        fd = open_fifo(pipe_path)
        if fd is None:
            time.sleep(2)  # pipe not created yet (shairport starting)
            continue
        parser.reset()
        try:
            pump(fd, pipe_path, parser, state)
        except OSError:
            time.sleep(2)
        finally:
            os.close(fd)
        time.sleep(0.2)  # writer just left; don't spin while shairport restarts


if __name__ == "__main__":  # pragma: no cover
    run()
