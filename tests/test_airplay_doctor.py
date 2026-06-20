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
