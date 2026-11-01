import http.client
import json
import threading
import time

import pytest
from _load import load

db = load("roles/airplay/files/airplay_dashboard.py", "airplay_dashboard")


def test_percent_to_db_endpoints_and_clamps():
    assert db.percent_to_db(100) == 0.0
    assert db.percent_to_db(0) == -144.0  # mute
    assert db.percent_to_db(50) == -15.0
    assert db.percent_to_db(150) == 0.0
    assert db.percent_to_db(-5) == -144.0


def test_bind_defaults_to_loopback():
    # safe-by-default: LAN reach is an explicit opt-in via the role var
    assert db.BIND == "127.0.0.1"


def test_volume_cmd_uses_remotecontrol_iface_and_dashdash():
    cmd = db.volume_cmd(50)
    i = cmd.index("/org/gnome/ShairportSync")
    assert cmd[i + 1 : i + 3] == ["org.gnome.ShairportSync.RemoteControl", "SetAirplayVolume"]
    # '--' must precede the (negative) dB value so busctl doesn't parse it as a flag
    assert cmd[-3:] == ["d", "--", "-15.0"]


def test_disconnect_cmd_uses_main_iface():
    cmd = db.disconnect_cmd()
    i = cmd.index("/org/gnome/ShairportSync")
    assert cmd[i + 1 : i + 3] == ["org.gnome.ShairportSync", "DropSession"]


def test_read_doctor_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DOCTOR_FILE", str(tmp_path / "nope.json"))
    assert db.read_doctor() == {"ok": None, "failed": [], "updated": 0, "stale": True}


def test_read_doctor_parses_report_and_staleness(tmp_path, monkeypatch):
    f = tmp_path / "doctor.json"
    f.write_text('{"ok": false, "checks": [{"name": "mdns:raop", "ok": false}, {"name": "x", "ok": true}]}')
    monkeypatch.setattr(db, "DOCTOR_FILE", str(f))
    d = db.read_doctor()
    assert (d["ok"], d["failed"], d["stale"]) == (False, ["mdns:raop"], False)
    assert db.read_doctor(now=time.time() + 3 * db.HEALTH_INTERVAL)["stale"] is True


def test_service_states_single_call(monkeypatch):
    calls = []

    class R:
        stdout = "active\ninactive\nactive\n"

    monkeypatch.setattr(db.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or R())
    assert db.service_states() == {"shairport-sync": True, "nqptp": False, "avahi-daemon": True}
    assert len(calls) == 1 and calls[0][:2] == ["systemctl", "is-active"]


def test_service_cache_limits_spawns(monkeypatch):
    n = []
    monkeypatch.setattr(db, "service_states", lambda: n.append(1) or {"x": True})
    cache = db._ServiceCache(ttl=60)
    cache.get()
    cache.get()
    assert len(n) == 1


def test_page_escapes_name():
    page = db.render_page("<script>alert(1)</script>")
    assert "<script>alert(1)" not in page
    assert "&lt;script&gt;alert(1)" in page


@pytest.mark.parametrize(
    ("host", "ok"),
    [
        ("192.168.1.10:8080", True),
        ("[::1]:8080", True),
        ("localhost:8080", True),
        ("wyse:8080", True),
        ("wyse.local", True),
        ("evil.example.com:8080", False),
        ("", False),
    ],
)
def test_host_allowed(host, ok):
    assert db.host_allowed(host, hostname="wyse") is ok


def test_origin_allowed():
    assert db.origin_allowed(None, "wyse.local:8080")
    assert db.origin_allowed("http://wyse.local:8080", "wyse.local:8080")
    assert not db.origin_allowed("https://evil.example.com", "wyse.local:8080")


# --- HTTP-level tests against a real server on an ephemeral port ------------


@pytest.fixture
def server(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(db, "set_volume", lambda pct: calls.append(("volume", pct)) or True)
    monkeypatch.setattr(db, "disconnect", lambda: calls.append(("disconnect",)) or True)
    monkeypatch.setattr(db, "service_states", lambda: {"shairport-sync": True})
    monkeypatch.setattr(db, "_services", db._ServiceCache())
    monkeypatch.setattr(db, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(db, "STATE_FILE", str(tmp_path / "nowplaying.json"))
    srv = db.make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    yield srv.server_address[1], calls, tmp_path
    srv.shutdown()


def request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    hdrs = {"Host": f"127.0.0.1:{port}"} | (headers or {})
    conn.request(method, path, body=body, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp, data


def test_http_status_and_page(server):
    port, _, _ = server
    resp, data = request(port, "GET", "/api/status")
    assert resp.status == 200 and json.loads(data)["services"] == {"shairport-sync": True}
    resp, data = request(port, "GET", "/")
    assert resp.status == 200 and b"AirPlay" in data


def test_http_volume_happy_path(server):
    port, calls, _ = server
    resp, data = request(
        port, "POST", "/api/volume", b'{"percent": 40}', {"Content-Type": "application/json"}
    )
    assert resp.status == 200 and json.loads(data) == {"ok": True}
    assert calls == [("volume", 40)]


@pytest.mark.parametrize(
    ("body", "headers", "status"),
    [
        (b'{"percent": 40}', {"Content-Type": "text/plain"}, 415),  # CSRF via simple request
        (b'{"percent": 40}', {"Content-Type": "application/json", "Origin": "https://evil.example"}, 403),
        (b"[1, 2]", {"Content-Type": "application/json"}, 400),
        (b'{"percent": 1e309}', {"Content-Type": "application/json"}, 400),
        (b"x" * 2000, {"Content-Type": "application/json"}, 413),
        (b"{}", {"Content-Type": "application/json", "Content-Length": "nan"}, 400),
    ],
)
def test_http_volume_rejects(server, body, headers, status):
    port, calls, _ = server
    resp, _ = request(port, "POST", "/api/volume", body, headers)
    assert resp.status == status
    assert calls == []


def test_http_rejects_rebinding_host(server):
    port, calls, _ = server
    resp, _ = request(port, "GET", "/api/status", headers={"Host": "evil.example.com"})
    assert resp.status == 421
    resp, _ = request(port, "POST", "/api/disconnect", b"{}", {"Host": "evil.example.com"})
    assert resp.status == 421 and calls == []


def test_http_cover_serves_only_known_names(server):
    port, _, tmp_path = server
    (tmp_path / "cover.jpg").write_bytes(b"\xff\xd8\xffJPEG")
    (tmp_path / "nowplaying.json").write_text(json.dumps({"cover": "cover.jpg"}))
    resp, data = request(port, "GET", "/cover?r=1")
    assert resp.status == 200 and data == b"\xff\xd8\xffJPEG"
    assert resp.getheader("Content-Type") == "image/jpeg"
    (tmp_path / "nowplaying.json").write_text(json.dumps({"cover": "../../etc/passwd"}))
    assert request(port, "GET", "/cover")[0].status == 404
