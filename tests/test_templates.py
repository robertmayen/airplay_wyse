import pathlib
from jinja2 import Environment, FileSystemLoader

TPL = pathlib.Path(__file__).resolve().parents[1] / "roles/airplay/templates"
env = Environment(loader=FileSystemLoader(str(TPL)), keep_trailing_newline=True)


def render(name, **ctx):
    return env.get_template(name).render(**ctx)


def test_config_renders_card_and_dev():
    out = render("shairport-sync.conf.j2", airplay_name="Living Room",
                 airplay_alsa_card="Device", airplay_alsa_device=0)
    assert 'name = "Living Room"' in out
    assert 'output_device = "hw:CARD=Device,DEV=0"' in out
    assert 'interpolation = "soxr"' in out
    assert 'disable_standby_mode = "always"' in out


def test_config_omits_device_id_by_default():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="Device", airplay_alsa_device=0)
    assert "airplay_device_id" not in out


def test_config_includes_device_id_when_set():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="Device", airplay_alsa_device=0,
                 airplay_device_id="5C:AA:FD:11:22:33")
    assert "airplay_device_id = 5C:AA:FD:11:22:33;" in out


def test_override_has_state_and_device_directives():
    out = render("shairport-override.conf.j2", airplay_state_dir="shairport-sync")
    assert "ProtectSystem=strict" in out
    assert "StateDirectory=shairport-sync" in out
    assert "CacheDirectory=shairport-sync" in out
    assert "DeviceAllow=char-alsa rw" in out
    assert "DevicePolicy=closed" in out
    assert "PrivateDevices" not in out
    assert "Requires=nqptp.service" in out


def test_config_emits_output_rate_when_set():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="Device", airplay_alsa_device=0,
                 airplay_output_rate=48000)
    assert "output_rate = 48000;" in out


def test_config_omits_output_rate_by_default():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="Device", airplay_alsa_device=0)
    assert "output_rate" not in out


def test_config_default_dev_when_alsa_device_omitted():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="Device")
    assert 'output_device = "hw:CARD=Device,DEV=0"' in out


def test_override_has_after_ordering():
    out = render("shairport-override.conf.j2", airplay_state_dir="shairport-sync")
    assert "After=nqptp.service avahi-daemon.service" in out


def test_config_alsa_prefix_override():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="AUDIO", airplay_alsa_device=0,
                 airplay_alsa_prefix="plughw")
    assert 'output_device = "plughw:CARD=AUDIO,DEV=0"' in out


def test_config_5x_emits_output_format_auto():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="AUDIO", airplay_alsa_device=0,
                 shairport_major="5")
    assert 'output_format = "auto"' in out


def test_config_4x_omits_output_format():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="AUDIO", airplay_alsa_device=0,
                 shairport_major="4")
    assert "output_format" not in out


def test_config_metadata_block_when_enabled():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="AUDIO", airplay_alsa_device=0,
                 airplay_metadata_enabled=True,
                 airplay_metadata_pipe="/run/shairport-sync/metadata-pipe")
    assert 'metadata = {' in out
    assert 'include_cover_art = "yes"' in out
    assert 'pipe_name = "/run/shairport-sync/metadata-pipe"' in out
    assert 'dbus_service_bus = "system"' in out


def test_config_no_metadata_block_by_default():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="AUDIO", airplay_alsa_device=0)
    assert "metadata = {" not in out
    assert "dbus_service_bus" not in out


def test_nqptp_override_grants_bind_capability():
    out = render("nqptp-override.conf.j2")
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in out
    assert "CapabilityBoundingSet=CAP_NET_BIND_SERVICE" in out


def test_unit_no_output_detect_runs_as_user():
    out = render("shairport-sync.service.j2", airplay_name="living room",
                 airplay_service_user="shairport-sync")
    assert "shairport-output-detect" not in out
    assert "User=shairport-sync" in out
    assert "ExecStart=/usr/local/bin/shairport-sync -c /etc/shairport-sync.conf" in out
    assert "living room" in out
    assert "Restart=on-failure" in out
