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


def test_bind_defaults_to_all_interfaces():
    assert db.BIND == "0.0.0.0"


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
