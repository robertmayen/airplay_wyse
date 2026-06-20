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
