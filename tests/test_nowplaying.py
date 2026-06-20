import base64
import importlib.util
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "roles/airplay/files/airplay_nowplaying.py"
_spec = importlib.util.spec_from_file_location("airplay_nowplaying", SRC)
np = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(np)


def _item(tag_type: str, tag_code: str, payload: bytes = b"") -> bytes:
    th = tag_type.encode().hex()
    ch = tag_code.encode().hex()
    if payload:
        data = f'<data encoding="base64">\n{base64.b64encode(payload).decode()}</data>'
    else:
        data = ""
    return f"<item><type>{th}</type><code>{ch}</code><length>{len(payload)}</length>{data}</item>".encode()


def test_code_to_str():
    assert np.code_to_str(0x6D696E6D) == "minm"
    assert np.code_to_str(0x50494354) == "PICT"


def test_parse_items_splits_stream_and_keeps_leftover():
    buf = _item("core", "minm", b"Song A") + _item("core", "asar", b"Artist B") + b"<item><typ"
    items, leftover = np.parse_items(buf)
    assert len(items) == 2
    assert items[0][0] == np.CORE
    assert items[0][2] == b"Song A"
    assert leftover == b"<item><typ"  # partial item retained


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


def test_apply_item_updates_track_and_session():
    state = np.empty_state()
    assert np.apply_item(state, np.CORE, 0x6D696E6D, b"My Song") is True
    assert state["title"] == "My Song"
    # same value again -> no change
    assert np.apply_item(state, np.CORE, 0x6D696E6D, b"My Song") is False
    # session begin sets active
    assert np.apply_item(state, np.SSNC, 0x70626567, b"") is True
    assert state["active"] is True
    # session end clears everything
    assert np.apply_item(state, np.SSNC, 0x70656E64, b"") is True
    assert state["active"] is False and state["title"] == ""


def test_apply_item_volume():
    state = np.empty_state()
    assert np.apply_item(state, np.SSNC, 0x70766F6C, b"-15.00,-20.00,-30.00,0.00") is True
    assert state["volume_percent"] == 50


def test_trim_buffer_under_cap_unchanged():
    buf = b"<item><type>" + b"x" * 100
    assert np.trim_buffer(buf, max_bytes=10_000) is buf


def test_trim_buffer_keeps_large_partial_item():
    # A partial item bigger than the OLD 1 MB guard but under the cap must survive
    # whole (a multi-MB cover still arriving), not get wiped.
    partial = b"<item><type>50494354</type>" + b"A" * 2_000_000
    assert np.trim_buffer(partial, max_bytes=16_000_000) is partial


def test_trim_buffer_trims_to_last_item_start():
    garbage = b"\x00" * 5_000
    tail = b"<item><type>50494354</type>" + b"B" * 100
    out = np.trim_buffer(garbage + tail, max_bytes=4_000)
    assert out == tail  # leading garbage dropped, partial item preserved


def test_trim_buffer_drops_oversized_garbage_without_item():
    garbage = b"\x00" * 5_000  # no <item> marker at all
    assert np.trim_buffer(garbage, max_bytes=4_000) == b""
