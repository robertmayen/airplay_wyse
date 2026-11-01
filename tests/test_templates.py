"""Render the role's templates exactly as Ansible does: Ansible's own templar,
the real role defaults (lazily templated) and the role's filter plugins."""

import pathlib

import pytest
from _load import load
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.loader import filter_loader
from ansible.template import Templar, trust_as_template

ROLE = pathlib.Path(__file__).resolve().parents[1] / "roles/airplay"
filter_loader.add_directory(str(ROLE / "filter_plugins"))
DEFAULTS = DataLoader().load_from_file(str(ROLE / "defaults/main.yml"))
filters = load("roles/airplay/filter_plugins/airplay_filters.py", "airplay_filters")

HOST = {"airplay_name": "Living Room", "airplay_alsa_card": "Device", "airplay_alsa_device": 0}


def render(name, **overrides):
    variables = {**DEFAULTS, **HOST, **overrides}
    templar = Templar(loader=DataLoader(), variables=variables)
    return templar.template(trust_as_template((ROLE / "templates" / name).read_text()))


def section(conf: str, name: str) -> str:
    """The body of one libconfig group, e.g. section(conf, 'general')."""
    start = conf.index(f"{name} = {{")
    return conf[start : conf.index("};", start)]


# --- shairport-sync.conf ---------------------------------------------------------


def test_config_renders_card_and_dev():
    out = render("shairport-sync.conf.j2")
    assert 'name = "Living Room"' in out
    assert 'output_device = "hw:CARD=Device,DEV=0"' in out
    assert 'disable_standby_mode = "always"' in out


def test_interpolation_lives_in_general_not_alsa():
    # shairport reads general.interpolation; in the alsa group it was ignored.
    out = render("shairport-sync.conf.j2")
    assert 'interpolation = "soxr"' in section(out, "general")
    assert "interpolation" not in section(out, "alsa")


def test_config_omits_device_id_by_default():
    assert "airplay_device_id" not in render("shairport-sync.conf.j2")


@pytest.mark.parametrize(
    "spelling", ["5C:AA:FD:11:22:33", "5caafd112233", "0x5CAAFD112233", "0x5CAAFD112233L"]
)
def test_device_id_rendered_as_libconfig_int64(spelling):
    # libconfig needs 0x...L; the colon-MAC form made shairport refuse the config.
    out = render("shairport-sync.conf.j2", airplay_device_id=spelling)
    assert "airplay_device_id = 0x5CAAFD112233L;" in section(out, "general")


def test_device_id_rejects_garbage():
    with pytest.raises(Exception, match="12 hex digits"):  # AnsibleFilterError
        filters.airplay_device_id("not-a-mac")


def test_name_is_escaped_for_libconfig():
    out = render("shairport-sync.conf.j2", airplay_name='Bob\'s "Den" \\ 100%')
    assert 'name = "Bob\'s \\"Den\\" \\\\ 100%";' in out


def test_config_output_rate_only_when_set():
    assert "output_rate" not in render("shairport-sync.conf.j2")
    assert "output_rate = 48000;" in render("shairport-sync.conf.j2", airplay_output_rate=48000)


def test_config_alsa_prefix_override():
    out = render("shairport-sync.conf.j2", airplay_alsa_card="AUDIO", airplay_alsa_prefix="plughw")
    assert 'output_device = "plughw:CARD=AUDIO,DEV=0"' in out


def test_config_output_format_only_on_5x():
    assert 'output_format = "auto"' in render("shairport-sync.conf.j2", shairport_major="5")
    assert "output_format" not in render("shairport-sync.conf.j2", shairport_major="4")


def test_config_metadata_block_when_enabled():
    out = render("shairport-sync.conf.j2", airplay_metadata_enabled=True)
    assert 'pipe_name = "/run/shairport-sync/metadata-pipe"' in section(out, "metadata")
    assert 'dbus_service_bus = "system"' in section(out, "general")
    assert "pipe_timeout" not in out  # read by no shairport version


@pytest.mark.parametrize("off", [False, "false", "no", 0])
def test_config_metadata_off_for_any_false_spelling(off):
    # `-e airplay_metadata_enabled=false` arrives as a string; it must still mean off.
    out = render("shairport-sync.conf.j2", airplay_metadata_enabled=off)
    assert "metadata = {" not in out and "dbus_service_bus" not in out


# --- systemd units -------------------------------------------------------------


def test_override_has_state_and_device_directives():
    out = render("shairport-override.conf.j2")
    for directive in (
        "ProtectSystem=strict",
        "StateDirectory=shairport-sync",
        "DeviceAllow=char-alsa rw",
        "DevicePolicy=closed",
        "Requires=nqptp.service",
        "After=nqptp.service avahi-daemon.service",
    ):
        assert directive in out
    assert "PrivateDevices" not in out


def test_shairport_unit_runs_as_user_and_preserves_fifo_dir():
    out = render("shairport-sync.service.j2", airplay_name="living room")
    assert "User=shairport-sync" in out
    assert "ExecStart=/usr/local/bin/shairport-sync -c /etc/shairport-sync.conf" in out
    assert "Description=Shairport Sync (living room)" in out
    # Without this the metadata FIFO vanished on every restart.
    assert "RuntimeDirectoryPreserve=yes" in out
    assert "udev-settle" not in out


def test_units_escape_name_specifiers_and_quotes():
    name = 'Den 100% "Hi-Fi"'
    unit = render("shairport-sync.service.j2", airplay_name=name)
    assert 'Description=Shairport Sync (Den 100%% "Hi-Fi")' in unit
    dash = render("airplay-dashboard.service.j2", airplay_name=name)
    assert 'Environment="AIRPLAY_NAME=Den 100%% \\"Hi-Fi\\""' in dash


def test_dashboard_unit_has_bind_env_and_hardening():
    out = render("airplay-dashboard.service.j2")
    assert "Environment=AIRPLAY_DASHBOARD_BIND=127.0.0.1" in out
    assert "Environment=AIRPLAY_HEALTH_INTERVAL=1800" in out
    for directive in ("NoNewPrivileges=yes", "ProtectSystem=strict", "SystemCallFilter=@system-service"):
        assert directive in out


def test_nowplaying_unit_is_networkless_and_follows_shairport():
    out = render("airplay-nowplaying.service.j2")
    assert "RestrictAddressFamilies=AF_UNIX" in out
    assert "AF_INET" not in out
    assert "PartOf=shairport-sync.service" in out


def test_nqptp_override_grants_bind_capability():
    out = render("nqptp-override.conf.j2")
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in out


def test_health_service_is_bounded_and_atomic():
    out = render("airplay-health.service.j2")
    assert "TimeoutStartSec=" in out
    assert "mv /run/airplay-doctor.json.tmp /run/airplay-doctor.json" in out


def test_health_timer_interval_and_no_dead_persistent():
    out = render("airplay-health.timer.j2", airplay_health_interval_minutes=15)
    assert "OnUnitActiveSec=15min" in out
    assert "Persistent" not in out  # only meaningful for OnCalendar= timers


# --- filters -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("output", "version", "commit", "expected"),
    [
        ("4.3.7-OpenSSL-Avahi-ALSA-soxr-AirPlay2", "4.3.7", "0b1c4391", True),
        ("5.6.2-AirPlay2-smi11-OpenSSL", "5.6.2", "", True),
        ("5.6.20-AirPlay2", "5.6.2", "", False),
        ("4.3.7-OpenSSL", "5.0.4", "abcdef12", False),  # the silent-downgrade case
        ("4.3.6-12-g0b1c439-AirPlay2", "4.3.7", "0b1c4391ffd3", True),  # git describe
        ("Version: 1.2.9. Shared Memory Interface Version: smi11.", "1.2.9", "", True),
        ("Version: 1.2.8. Shared Memory Interface Version: smi10.", "1.2.9", "c925f27c", False),
        ("", "1.2.9", "", False),
    ],
)
def test_is_pinned(output, version, commit, expected):
    assert filters.airplay_is_pinned(output, version, commit) is expected
