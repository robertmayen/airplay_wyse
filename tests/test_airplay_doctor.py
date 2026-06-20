import importlib.util
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "roles/airplay/files/airplay_doctor.py"
_spec = importlib.util.spec_from_file_location("airplay_doctor", SRC)
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)


def test_parse_version_classic_tokens():
    out = "4.3.7-OpenSSL-Avahi-ALSA-soxr-sysconfdir:/etc-AirPlay2"
    r = ad.parse_shairport_version(out)
    assert r["version"] == "4.3.7"
    assert r["airplay2"] is True
    assert r["soxr"] is True
    assert r["alac"] is False


def test_parse_version_spaced_and_alac():
    out = "5.0.4 OpenSSL Avahi ALSA soxr ALAC AirPlay 2"
    r = ad.parse_shairport_version(out)
    assert r["version"] == "5.0.4"
    assert r["airplay2"] is True
    assert r["alac"] is True


def test_parse_version_dev_tag():
    r = ad.parse_shairport_version("5.1~dev-OpenSSL-AirPlay2")
    assert r["version"] == "5.1~dev"
    assert r["airplay2"] is True


def test_ports_owned_by_nqptp():
    ss = (
        'UNCONN 0 0 0.0.0.0:319 0.0.0.0:* users:(("nqptp",pid=42,fd=4))\n'
        'UNCONN 0 0 0.0.0.0:320 0.0.0.0:* users:(("nqptp",pid=42,fd=5))\n'
        'UNCONN 0 0 0.0.0.0:5353 0.0.0.0:* users:(("avahi-daemon",pid=7,fd=12))\n'
    )
    r = ad.parse_listening_ports(ss)
    assert r[319]["bound"] and r[319]["nqptp"]
    assert r[320]["bound"] and r[320]["nqptp"]


def test_ports_not_confused_by_substring():
    ss = 'UNCONN 0 0 0.0.0.0:31900 0.0.0.0:* users:(("other",pid=1,fd=1))\n'
    r = ad.parse_listening_ports(ss)
    assert r[319]["bound"] is False


def test_mdns_detects_services():
    out = "+ eth0 IPv4 Living Room _airplay._tcp local\n+ eth0 IPv4 Living Room _raop._tcp local\n"
    r = ad.parse_mdns(out)
    assert r["airplay"] and r["raop"]


def test_alsa_cards_from_aplay_L():
    out = (
        "default\n"
        "hw:CARD=Device,DEV=0\n"
        "    USB Audio Device, USB Audio\n"
        "plughw:CARD=Device,DEV=0\n"
        "hw:CARD=PCH,DEV=0\n"
    )
    assert ad.parse_alsa_cards(out) == {"Device", "PCH"}


def test_journal_error_counts():
    j = "underrun detected\nsomething fine\nlost sync with source\noverrun!\n"
    r = ad.parse_journal_errors(j)
    assert r["xruns"] == 2
    assert r["sync"] == 1


def test_device_id_parse_and_zero():
    assert ad.parse_device_id('  airplay_device_id = "5C:AA:FD:11:22:33";') == "5C:AA:FD:11:22:33"
    assert ad.is_zero_device_id("00:00:00:00:00:00") is True
    assert ad.is_zero_device_id("5C:AA:FD:11:22:33") is False
    assert ad.is_zero_device_id("") is True
