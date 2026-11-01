import importlib.util
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "scripts/check_upstream.py"
_spec = importlib.util.spec_from_file_location("check_upstream", SRC)
cu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cu)

PINS = (
    'shairport_major: "4"\n'
    'shairport_sync_version: "4.3.7"\n'
    'shairport_sync_commit: "aaaa111"\n'
    'nqptp_version: "1.2.8"\n'
    'nqptp_commit: "bbbb222"\n'
)


def test_parse_pins():
    p = cu.parse_pins(PINS)
    assert p["shairport_sync_version"] == "4.3.7"
    assert p["shairport_major"] == "4"


def test_plan_bumps_minor_within_major():
    plan = cu.plan_bumps(cu.parse_pins(PINS), {"shairport-sync": "4.3.8", "nqptp": "1.2.9"})
    assert plan["shairport_sync_version"] == {"from": "4.3.7", "to": "4.3.8"}
    assert plan["nqptp_version"] == {"from": "1.2.8", "to": "1.2.9"}


def test_plan_bumps_never_crosses_major():
    plan = cu.plan_bumps(cu.parse_pins(PINS), {"shairport-sync": "5.0.4", "nqptp": "1.2.8"})
    assert "shairport_sync_version" not in plan
    assert any("major" in n for n in plan["_notices"])


def test_plan_bumps_noop_and_v_prefix():
    plan = cu.plan_bumps(cu.parse_pins(PINS), {"shairport-sync": "v4.3.7", "nqptp": "1.2.8"})
    assert plan == {"_notices": []}


def test_plan_bumps_missing_upstream_data_is_skipped():
    plan = cu.plan_bumps(cu.parse_pins(PINS), {})
    assert plan == {"_notices": []}


def test_rewrite_pins_roundtrip():
    out = cu.rewrite_pins(PINS, {"nqptp_version": "1.2.9", "nqptp_commit": "cccc333"})
    assert 'nqptp_version: "1.2.9"' in out
    assert 'nqptp_commit: "cccc333"' in out
    assert 'shairport_sync_version: "4.3.7"' in out
