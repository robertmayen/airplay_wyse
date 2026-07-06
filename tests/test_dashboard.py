import importlib.util
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "roles/airplay/files/airplay_dashboard.py"
_spec = importlib.util.spec_from_file_location("airplay_dashboard", SRC)
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)


def test_percent_to_db_endpoints():
    assert db.percent_to_db(100) == 0.0
    assert db.percent_to_db(0) == -144.0  # mute
    assert db.percent_to_db(50) == -15.0


def test_percent_to_db_clamps():
    assert db.percent_to_db(150) == 0.0
    assert db.percent_to_db(-5) == -144.0


def test_bind_defaults_to_loopback():
    # safe-by-default: LAN reach is an explicit opt-in via the role var
    assert db.BIND == "127.0.0.1"


def test_volume_cmd_uses_remotecontrol_iface_and_dashdash():
    cmd = db.volume_cmd(50)
    # interface must be the RemoteControl one, method SetAirplayVolume
    i = cmd.index("/org/gnome/ShairportSync")
    assert cmd[i + 1] == "org.gnome.ShairportSync.RemoteControl"
    assert cmd[i + 2] == "SetAirplayVolume"
    # '--' must precede the (negative) dB value so busctl doesn't parse it as a flag
    assert cmd[-3:] == ["d", "--", "-15.0"]


def test_disconnect_cmd_uses_main_iface():
    cmd = db.disconnect_cmd()
    i = cmd.index("/org/gnome/ShairportSync")
    assert cmd[i + 1] == "org.gnome.ShairportSync"
    assert cmd[i + 2] == "DropSession"


def test_read_doctor_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DOCTOR_FILE", str(tmp_path / "nope.json"))
    d = db.read_doctor()
    assert d == {"ok": None, "failed": [], "updated": 0}


def test_read_doctor_parses_report(tmp_path, monkeypatch):
    f = tmp_path / "doctor.json"
    f.write_text('{"ok": false, "checks": [{"name": "mdns:raop", "ok": false},'
                 ' {"name": "service:nqptp", "ok": true}]}')
    monkeypatch.setattr(db, "DOCTOR_FILE", str(f))
    d = db.read_doctor()
    assert d["ok"] is False
    assert d["failed"] == ["mdns:raop"]
    assert d["updated"] > 0


def test_status_includes_doctor(monkeypatch):
    monkeypatch.setattr(db, "read_doctor", lambda: {"ok": True, "failed": [], "updated": 1.0})
    monkeypatch.setattr(db, "service_active", lambda name: True)
    s = db.build_status()
    assert s["doctor"] == {"ok": True, "failed": [], "updated": 1.0}
