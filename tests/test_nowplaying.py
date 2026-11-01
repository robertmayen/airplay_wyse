import base64
import json
import os
import threading
import time

from _load import load

np = load("roles/airplay/files/airplay_nowplaying.py", "airplay_nowplaying")


def _item(tag_type: str, tag_code: str, payload: bytes = b"") -> bytes:
    """Exactly what shairport-sync writes (pipe.c / rtsp.c)."""
    head = f"<item><type>{tag_type.encode().hex()}</type><code>{tag_code.encode().hex()}</code>"
    head += f"<length>{len(payload)}</length>"
    data = f'\n<data encoding="base64">\n{base64.b64encode(payload).decode()}</data>' if payload else ""
    return f"{head}{data}</item>\n".encode()


def _feed_in_chunks(parser, stream: bytes, size: int):
    items = []
    for i in range(0, len(stream), size):
        items += parser.feed(stream[i : i + size])
    return items


def test_code_to_str():
    assert np.code_to_str(0x6D696E6D) == "minm"
    assert np.code_to_str(0x50494354) == "PICT"


def test_parser_splits_stream_and_keeps_partial_item():
    p = np.ItemParser()
    items = p.feed(_item("core", "minm", b"Song A") + _item("core", "asar", b"Artist B") + b"<item><typ")
    assert [(t, c, d) for t, c, d in items] == [
        (np.CORE, 0x6D696E6D, b"Song A"),
        (np.CORE, 0x61736172, b"Artist B"),
    ]
    assert bytes(p.buf) == b"\n<item><typ"


def test_parser_handles_tags_split_across_reads():
    stream = b"".join(_item("core", "minm", f"Song {i}".encode()) for i in range(50))
    for size in (1, 3, 7, 64):
        items = _feed_in_chunks(np.ItemParser(), stream, size)
        assert [d for _, _, d in items] == [f"Song {i}".encode() for i in range(50)]


def test_parser_skips_garbage_and_malformed_items():
    p = np.ItemParser()
    junk = b"\x00garbage</item><item><type>zz</type></item>"
    items = p.feed(junk + _item("ssnc", "pvol", b"-15.00,-20.00,-30.00,0.00"))
    assert [np.code_to_str(c) for _, c, _ in items] == ["pvol"]


def test_parser_drops_runaway_buffer():
    p = np.ItemParser(max_item=1000)
    p.feed(b"<item>" + b"A" * 2000)
    assert len(p.buf) == 0


def test_large_cover_is_linear_time():
    # Regression: the regex parser took ~6 s for a 1 MB cover and ~1 min for 3 MB.
    cover = os.urandom(3 * 1024 * 1024)
    stream = _item("ssnc", "PICT", cover)
    t0 = time.perf_counter()
    items = _feed_in_chunks(np.ItemParser(), stream, 4096)
    assert time.perf_counter() - t0 < 1.0
    assert items[0][2] == cover


def test_parse_pvol_percent_and_mute():
    assert np.parse_pvol(b"0.00,-0.00,-30.00,0.00")["percent"] == 100
    assert np.parse_pvol(b"-30.00,-30.00,-30.00,0.00")["percent"] == 0
    half = np.parse_pvol(b"-15.00,-20.00,-30.00,0.00")
    assert half["percent"] == 50 and half["muted"] is False
    assert np.parse_pvol(b"-144.00,-144.00,-30.00,0.00")["muted"] is True


def test_cover_ext_detects_format():
    assert np.cover_ext(b"\xff\xd8\xff\xe0rest") == "jpg"
    assert np.cover_ext(b"\x89PNG\r\n\x1a\nrest") == "png"
    assert np.cover_ext(b"garbage") == "bin"


def test_apply_item_track_and_session(tmp_path):
    state = np.empty_state()
    assert np.apply_item(state, np.CORE, 0x6D696E6D, b"My Song", str(tmp_path)) is True
    assert state["title"] == "My Song"
    assert state["active"] is True  # track metadata implies a session, even without pbeg
    assert np.apply_item(state, np.CORE, 0x6D696E6D, b"My Song", str(tmp_path)) is False
    assert np.apply_item(state, np.SSNC, 0x70656E64, b"", str(tmp_path)) is True  # pend
    assert state["active"] is False and state["title"] == ""


def test_apply_item_volume_marks_active(tmp_path):
    state = np.empty_state()
    assert np.apply_item(state, np.SSNC, 0x70766F6C, b"-15.00,-20.00,-30.00,0.00", str(tmp_path)) is True
    assert state["volume_percent"] == 50 and state["active"] is True


def test_cover_written_atomically_and_replaced(tmp_path):
    state = np.empty_state()
    jpg = b"\xff\xd8\xff" + b"J" * 100
    png = b"\x89PNG\r\n\x1a\n" + b"P" * 100
    assert np.apply_item(state, np.SSNC, 0x50494354, jpg, str(tmp_path)) is True
    assert state["cover"] == "cover.jpg"
    assert (tmp_path / "cover.jpg").read_bytes() == jpg
    # Same format again is still a change (new image under the same name).
    assert np.apply_item(state, np.SSNC, 0x50494354, jpg, str(tmp_path)) is True
    np.apply_item(state, np.SSNC, 0x50494354, png, str(tmp_path))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cover.png"]  # stale jpg removed, no tmp left


def test_new_track_clears_previous_cover(tmp_path):
    state = np.empty_state()
    np.apply_item(state, np.CORE, 0x6D696E6D, b"Track 1", str(tmp_path))
    np.apply_item(state, np.SSNC, 0x50494354, b"\xff\xd8\xff" + b"x" * 10, str(tmp_path))
    np.apply_item(state, np.CORE, 0x6D696E6D, b"Track 2", str(tmp_path))
    assert state["cover"] is None


def test_pump_reads_fifo_until_writer_closes(tmp_path):
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    fd = np.open_fifo(str(fifo))  # non-blocking: succeeds with no writer yet
    assert fd is not None

    def writer():
        with open(fifo, "wb") as w:
            w.write(_item("core", "minm", b"Live") + _item("ssnc", "pvol", b"-30.00,0,0,0"))

    threading.Thread(target=writer).start()
    state = np.empty_state()
    state_file = tmp_path / "np.json"
    np.pump(fd, str(fifo), np.ItemParser(), state, 1.0, str(tmp_path), str(state_file))
    os.close(fd)
    assert json.loads(state_file.read_text())["title"] == "Live"


def test_pump_returns_when_fifo_is_replaced(tmp_path):
    # shairport's RuntimeDirectory being recreated leaves the reader on an
    # orphaned FIFO; it must notice and return so the caller reopens the new one.
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    fd = np.open_fifo(str(fifo))
    os.unlink(fifo)
    os.mkfifo(fifo)
    t0 = time.perf_counter()
    np.pump(fd, str(fifo), np.ItemParser(), np.empty_state(), 0.1, str(tmp_path), str(tmp_path / "s"))
    os.close(fd)
    assert time.perf_counter() - t0 < 2


def test_open_fifo_missing_returns_none(tmp_path):
    assert np.open_fifo(str(tmp_path / "nope")) is None
