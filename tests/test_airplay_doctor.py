import json

from _load import load

ad = load("roles/airplay/files/airplay_doctor.py", "airplay_doctor")

CONF = """general = {
  name = "Living Room";
  interpolation = "soxr";
};
alsa = {
  output_device = "hw:CARD=Device,DEV=0";
};
"""

AVAHI_AIRPLAY = (
    "+;eth0;IPv4;Living\\032Room;_airplay._tcp;local\n"
    '=;eth0;IPv4;Living\\032Room;_airplay._tcp;local;wyse.local;192.168.1.10;7000;"acl=0" '
    '"deviceid=5C:AA:FD:11:22:33" "model=Shairport Sync"\n'
    '=;eth0;IPv4;Kitchen;_airplay._tcp;local;other.local;192.168.1.11;7000;"deviceid=11:22:33:44:55:66"\n'
)
AVAHI_RAOP = (
    '=;eth0;IPv4;5CAAFD112233@Living\\032Room;_raop._tcp;local;wyse.local;192.168.1.10;7000;"txtvers=1"\n'
)


class FakeProbes:
    """Stands in for ad.Probes; every attribute can be overridden per test."""

    def __init__(self, **overrides):
        self.root = True
        self.conf = CONF
        self.states = {}
        self.sps = "5.6.2-AirPlay2-smi11-OpenSSL-Avahi-ALSA-soxr-sysconfdir:/etc"
        self.nq = "Version: 1.2.9. Shared Memory Interface Version: smi11.\n"
        self.ss = (
            'UNCONN 0 0 0.0.0.0:319 0.0.0.0:* users:(("nqptp",pid=42,fd=4))\n'
            'UNCONN 0 0 0.0.0.0:320 0.0.0.0:* users:(("nqptp",pid=42,fd=5))\n'
        )
        self.avahi = {"_airplay._tcp": AVAHI_AIRPLAY, "_raop._tcp": AVAHI_RAOP}
        self.aplay = "hw:CARD=Device,DEV=0\n    USB Audio\nplughw:CARD=Device,DEV=0\n"
        self.journal_text = ""
        self.pcm = "closed\n"
        self.owner = "shairport-sync"
        self.open_out = 'HW Params of device "hw:CARD=Device,DEV=0":\n'
        self.__dict__.update(overrides)

    def is_root(self):
        return self.root

    def config(self):
        return self.conf

    def service_states(self, names):
        return {n: self.states.get(n, "active") for n in names}

    def shairport_version(self):
        return self.sps

    def nqptp_version(self):
        return self.nq

    def udp_sockets(self):
        return self.ss

    def mdns(self, service_type):
        return self.avahi[service_type]

    def alsa_pcms(self):
        return self.aplay

    def journal(self):
        return self.journal_text

    def pcm_status(self, card, device):
        return self.pcm

    def process_name(self, pid):
        return self.owner

    def open_device(self, device):
        return self.open_out


def check(report, name):
    return next(c for c in report["checks"] if c["name"] == name)


# --- parsers -----------------------------------------------------------------


def test_parse_version_classic_tokens():
    r = ad.parse_shairport_version("4.3.7-OpenSSL-Avahi-ALSA-soxr-sysconfdir:/etc-AirPlay2")
    assert r["version"] == "4.3.7"
    assert r["airplay2"] and r["soxr"] and not r["alac"]
    assert r["smi"] is None


def test_parse_version_5x_with_smi_metadata_dbus():
    r = ad.parse_shairport_version(
        "5.6.2-AirPlay2-smi11-OpenSSL-Avahi-ALSA-soxr-metadata-dbus-sysconfdir:/etc"
    )
    assert r["version"] == "5.6.2"
    assert r["smi"] == 11
    assert r["metadata"] and r["dbus"]


def test_parse_version_spaced_and_dev_tag():
    assert ad.parse_shairport_version("5.0.4 OpenSSL ALAC AirPlay 2")["airplay2"] is True
    assert ad.parse_shairport_version("5.1~dev-OpenSSL-AirPlay2")["version"] == "5.1~dev"


def test_parse_nqptp_version():
    r = ad.parse_nqptp_version("Version: 1.2.9. Shared Memory Interface Version: smi11.\n")
    assert r == {"version": "1.2.9", "smi": 11}
    assert ad.parse_nqptp_version("1.2.4\n") == {"version": "1.2.4", "smi": None}


def test_ports_owned_by_nqptp_and_not_confused_by_substring():
    r = ad.parse_listening_ports(FakeProbes().ss)
    assert r[319] == {"bound": True, "nqptp": True}
    other = ad.parse_listening_ports('UNCONN 0 0 0.0.0.0:31900 0.0.0.0:* users:(("other",pid=1,fd=1))\n')
    assert other[319]["bound"] is False


def test_parse_avahi_unescapes_names_and_reads_txt():
    records = ad.parse_avahi(AVAHI_AIRPLAY)
    assert [r["name"] for r in records] == ["Living Room", "Kitchen"]  # '+' (unresolved) lines skipped
    assert records[0]["txt"]["deviceid"] == "5C:AA:FD:11:22:33"
    assert records[0]["host"] == "wyse.local"


def test_alsa_cards_from_aplay_L():
    out = "default\nhw:CARD=Device,DEV=0\n    USB Audio\nplughw:CARD=Device,DEV=0\nhw:CARD=PCH,DEV=0\n"
    assert ad.parse_alsa_cards(out) == {"Device", "PCH"}


def test_output_card_accepts_plughw():
    assert ad.parse_output_card('output_device = "plughw:CARD=AUDIO,DEV=1";') == ("AUDIO", 1)
    assert ad.parse_output_card('output_device = "hw:CARD=Device,DEV=0";') == ("Device", 0)
    assert ad.parse_output_card("") is None


def test_conf_name_unescapes():
    assert ad.parse_conf_name('general = {\n  name = "Bob\\"s \\\\ Room";\n};') == 'Bob"s \\ Room'


def test_device_id_spellings_normalize():
    assert ad.normalize_device_id("0x5CAAFD112233L") == "5C:AA:FD:11:22:33"
    assert ad.normalize_device_id("5c:aa:fd:11:22:33") == "5C:AA:FD:11:22:33"
    assert ad.normalize_device_id("") == ""
    assert ad.parse_device_id("  airplay_device_id = 0x5CAAFD112233L;\n") == "5C:AA:FD:11:22:33"
    assert ad.parse_device_id(CONF) == ""
    assert ad.is_zero_device_id("00:00:00:00:00:00") and not ad.is_zero_device_id("5C:AA:FD:11:22:33")


def test_journal_error_counts():
    r = ad.parse_journal_errors("underrun detected\nsomething fine\nlost sync with source\noverrun!\n")
    assert r == {"xruns": 2, "sync": 1}


def test_journal_probe_is_scoped_to_recent_boot(monkeypatch):
    seen = {}
    monkeypatch.setattr(ad.Probes, "_run", lambda self, cmd, merge_stderr=False: seen.setdefault("cmd", cmd))
    ad.Probes().journal()
    assert "-b" in seen["cmd"] and "--since" in seen["cmd"]


def test_pcm_status():
    assert ad.parse_pcm_status("closed\n") == {"state": "closed", "owner_pid": None}
    running = "state: RUNNING\nowner_pid   : 812\ntrigger_time: 1.0\n"
    assert ad.parse_pcm_status(running) == {"state": "RUNNING", "owner_pid": 812}


def test_probe_timeout_or_missing_tool_returns_none():
    assert ad.Probes(timeout=1)._run(["/nonexistent/tool"]) is None
    assert ad.Probes(timeout=0.2)._run(["sleep", "5"]) is None


# --- report -------------------------------------------------------------------


def test_report_all_green():
    r = ad.build_report(FakeProbes())
    assert r["ok"] is True, [c for c in r["checks"] if not c["ok"]]
    assert r["device_id"] == "5C:AA:FD:11:22:33"  # the ADVERTISED id, from mDNS
    assert r["name"] == "Living Room"
    assert r["versions"] == {"shairport": "5.6.2", "nqptp": "1.2.9"}
    assert check(r, "nqptp:interface")["status"] == "ok"


def test_mdns_checks_this_box_not_the_network():
    # Another box advertising on the LAN must not make this one look healthy.
    only_kitchen = (
        '=;eth0;IPv4;Kitchen;_airplay._tcp;local;k.local;10.0.0.2;7000;"deviceid=11:22:33:44:55:66"\n'
    )
    r = ad.build_report(FakeProbes(avahi={"_airplay._tcp": only_kitchen, "_raop._tcp": ""}))
    assert r["ok"] is False
    assert check(r, "mdns:airplay")["status"] == "fail"
    assert check(r, "identity:device-id")["status"] == "unknown"


def test_mdns_unavailable_fails_cleanly():
    r = ad.build_report(FakeProbes(avahi={"_airplay._tcp": None, "_raop._tcp": None}))
    assert check(r, "mdns:airplay")["status"] == "fail"


def test_report_fails_when_nqptp_down():
    r = ad.build_report(FakeProbes(states={"nqptp": "inactive"}))
    assert r["ok"] is False
    assert check(r, "service:nqptp")["detail"] == "inactive"


def test_report_fails_on_missing_airplay2_feature():
    r = ad.build_report(FakeProbes(sps="4.3.7-OpenSSL-ALSA-soxr"))
    assert check(r, "feature:airplay2")["status"] == "fail"


def test_smi_mismatch_fails():
    # shairport 4.3.7/5.0.x speak smi10; nqptp 1.2.9 speaks smi11 -> no AirPlay 2 timing.
    r = ad.build_report(FakeProbes(sps="5.0.4-AirPlay2-smi10-soxr"))
    assert check(r, "nqptp:interface")["status"] == "fail"
    assert r["ok"] is False


def test_pinned_device_id_must_match_advertised():
    conf = CONF.replace(
        'interpolation = "soxr";', 'interpolation = "soxr";\n  airplay_device_id = 0x5CAAFD112234L;'
    )
    r = ad.build_report(FakeProbes(conf=conf))
    assert check(r, "identity:device-id")["status"] == "fail"


def test_zero_pinned_device_id_fails():
    conf = CONF.replace('interpolation = "soxr";', "airplay_device_id = 0x000000000000L;")
    assert check(ad.build_report(FakeProbes(conf=conf)), "identity:device-id")["status"] == "fail"


def test_alsa_card_check_honours_plughw():
    conf = CONF.replace('"hw:CARD=Device,DEV=0"', '"plughw:CARD=Missing,DEV=0"')
    r = ad.build_report(FakeProbes(conf=conf))
    assert check(r, "alsa:card") == {"name": "alsa:card", "ok": False, "status": "fail", "detail": "Missing"}


def test_non_root_marks_privileged_checks_unknown_not_failed():
    ss_no_owner = "UNCONN 0 0 0.0.0.0:319 0.0.0.0:*\nUNCONN 0 0 0.0.0.0:320 0.0.0.0:*\n"
    r = ad.build_report(FakeProbes(root=False, ss=ss_no_owner))
    assert check(r, "ports:319/320")["status"] == "unknown"
    assert check(r, "journal:errors")["status"] == "unknown"
    assert r["ok"] is True


def test_journal_warns_then_fails_on_threshold():
    one = ad.build_report(FakeProbes(journal_text="underrun\n"))
    assert check(one, "journal:errors")["status"] == "warn" and one["ok"] is True
    many = ad.build_report(FakeProbes(journal_text="underrun\n" * 40))
    assert check(many, "journal:errors")["status"] == "fail" and many["ok"] is False


def test_metadata_services_and_features_checked_when_enabled():
    conf = CONF + 'metadata = {\n  enabled = "yes";\n  pipe_name = "/run/x";\n};\n'
    r = ad.build_report(FakeProbes(conf=conf))
    assert check(r, "service:airplay-dashboard")["status"] == "ok"
    assert check(r, "feature:metadata")["status"] == "fail"  # fake build lacks metadata/dbus
    assert "service:airplay-dashboard" not in [c["name"] for c in ad.build_report(FakeProbes())["checks"]]


def test_deep_device_held_by_shairport_is_ok():
    r = ad.build_report(FakeProbes(pcm="state: RUNNING\nowner_pid : 77\n"), deep=True)
    assert check(r, "deep:device")["status"] == "ok"


def test_deep_device_held_by_someone_else_fails():
    r = ad.build_report(FakeProbes(pcm="state: RUNNING\nowner_pid : 77\n", owner="aplay"), deep=True)
    assert check(r, "deep:device")["status"] == "fail"


def test_deep_device_closed_is_opened():
    assert check(ad.build_report(FakeProbes(), deep=True), "deep:device")["status"] == "ok"
    busy = FakeProbes(open_out="aplay: main:834: audio open error: Device or resource busy\n")
    assert check(ad.build_report(busy, deep=True), "deep:device")["status"] == "fail"


def test_deep_device_missing_card_fails():
    assert check(ad.build_report(FakeProbes(pcm=None), deep=True), "deep:device")["status"] == "fail"


def test_no_deep_check_without_flag():
    assert not any(c["name"].startswith("deep:") for c in ad.build_report(FakeProbes())["checks"])


def test_main_json_exit_codes(capsys):
    assert ad.main(["--json"], probes=FakeProbes()) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert ad.main([], probes=FakeProbes(states={"nqptp": "failed"})) == 1
    assert "FAIL" in capsys.readouterr().out
