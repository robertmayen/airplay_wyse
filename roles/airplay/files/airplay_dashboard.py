#!/usr/bin/env python3
"""airplay-dashboard — a tiny always-on web view for one AirPlay box.

Stdlib only. Shows now-playing (from airplay-nowplaying's JSON), cover art,
service health, and live volume; offers the controls that actually work with
modern Apple sources: a volume slider (shairport SetAirplayVolume over D-Bus)
and a disconnect button (DropSession). Transport (play/pause/next) is omitted
because iOS 17.4+/macOS 14.4+ ignore those commands from a receiver.

It is an unauthenticated LAN control surface, so state-changing requests are
guarded against cross-site requests (JSON content type + Origin check) and the
Host header is checked against DNS rebinding.
"""

from __future__ import annotations

import html
import ipaddress
import json
import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

NAME = os.environ.get("AIRPLAY_NAME", os.uname().nodename)
BIND = os.environ.get("AIRPLAY_DASHBOARD_BIND", "127.0.0.1")
PORT = int(os.environ.get("AIRPLAY_DASHBOARD_PORT", "8080"))
STATE_DIR = os.environ.get("AIRPLAY_STATE_DIR", "/run/airplay")
STATE_FILE = os.path.join(STATE_DIR, "nowplaying.json")
DOCTOR_FILE = os.environ.get("AIRPLAY_DOCTOR_FILE", "/run/airplay-doctor.json")
HEALTH_INTERVAL = int(os.environ.get("AIRPLAY_HEALTH_INTERVAL", "1800"))
# Extra Host names the dashboard answers to (comma-separated), e.g. a DNS alias.
EXTRA_HOSTS = {
    h.strip().lower() for h in os.environ.get("AIRPLAY_DASHBOARD_HOSTS", "").split(",") if h.strip()
}

SERVICES = ("shairport-sync", "nqptp", "avahi-daemon")
MAX_BODY = 1024
_BUS = ["busctl", "--system", "call", "org.gnome.ShairportSync", "/org/gnome/ShairportSync"]
SVC_IFACE = "org.gnome.ShairportSync"


def percent_to_db(percent: int) -> float:
    """Map a 0-100 slider to shairport's AirPlay volume dB (0..-30, -144=mute)."""
    percent = max(0, min(100, int(percent)))
    if percent == 0:
        return -144.0
    return round(-30.0 + percent * 0.30, 2)


def volume_cmd(percent: int) -> list:
    """busctl argv to set the AirPlay volume.

    SetAirplayVolume lives on the RemoteControl interface (not the main one),
    and the '--' is required so busctl does not parse the negative dB value as
    options.
    """
    return [*_BUS, SVC_IFACE + ".RemoteControl", "SetAirplayVolume", "d", "--", str(percent_to_db(percent))]


def disconnect_cmd() -> list:
    return [*_BUS, SVC_IFACE, "DropSession"]


def _run(cmd) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=5, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def set_volume(percent: int) -> bool:
    return _run(volume_cmd(percent))


def disconnect() -> bool:
    return _run(disconnect_cmd())


class _ServiceCache:
    """One `systemctl is-active` for all units, at most every `ttl` seconds —
    every open browser polls, and spawning per unit per poll adds up."""

    def __init__(self, ttl: float = 2.0):
        self.ttl = ttl
        self._lock = threading.Lock()
        self._at = 0.0
        self._value: dict = {}

    def get(self) -> dict:
        with self._lock:
            if time.monotonic() - self._at >= self.ttl:
                self._value = service_states()
                self._at = time.monotonic()
            return self._value


def service_states() -> dict:
    try:
        out = subprocess.run(
            ["systemctl", "is-active", *SERVICES], capture_output=True, text=True, timeout=5, check=False
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        out = []
    return {s: (out[i] == "active" if i < len(out) else False) for i, s in enumerate(SERVICES)}


_services = _ServiceCache()


def read_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"active": False, "title": "", "artist": "", "album": "", "volume_percent": 0, "muted": False}


def read_doctor(now: float | None = None) -> dict:
    """Summarize the health timer's last airplay-doctor report, if any."""
    try:
        with open(DOCTOR_FILE, encoding="utf-8") as fh:
            report = json.load(fh)
        updated = os.path.getmtime(DOCTOR_FILE)
    except (OSError, ValueError):
        return {"ok": None, "failed": [], "updated": 0, "stale": True}
    return {
        "ok": bool(report.get("ok")),
        "failed": [c.get("name", "?") for c in report.get("checks", []) if not c.get("ok")],
        "updated": updated,
        # A wedged health run must not leave an old green badge up forever.
        "stale": ((now or time.time()) - updated) > 2 * HEALTH_INTERVAL,
    }


def build_status() -> dict:
    return {"name": NAME, "nowplaying": read_state(), "services": _services.get(), "doctor": read_doctor()}


def host_allowed(host_header: str, hostname: str | None = None) -> bool:
    """DNS-rebinding guard: answer only to IP literals and this box's own names.

    A rebinding attack always arrives with the attacker's domain in Host; an
    IP literal (any of the box's addresses) or a known local name cannot be one.
    """
    host = (urlsplit(f"//{host_header}").hostname or "").lower()
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    me = (hostname or socket.gethostname()).lower()
    return host in {"localhost", me, f"{me}.local"} | EXTRA_HOSTS


def origin_allowed(origin: str | None, host_header: str) -> bool:
    """CSRF guard: a browser always sends Origin on cross-site POSTs; it must
    name this very host. Non-browser clients (curl) send none and are allowed."""
    if origin is None:
        return True
    return urlsplit(origin).netloc.lower() == host_header.lower()


PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>__NAME__ · AirPlay</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;font:16px system-ui,sans-serif;background:#0e0f13;color:#e8e8ea;
display:flex;min-height:100vh;align-items:center;justify-content:center}
.card{width:min(420px,92vw);background:#17191f;border-radius:18px;padding:22px;
box-shadow:0 10px 40px #0008}
.hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.hdr h1{font-size:15px;margin:0;font-weight:600;letter-spacing:.3px}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-left:6px}
.ok{background:#3ddc84}.bad{background:#ff5b5b}.unk{background:#6a6c72}
.art{width:100%;aspect-ratio:1;border-radius:12px;background:#23262e center/cover no-repeat;
display:flex;align-items:center;justify-content:center;color:#555;font-size:40px}
.title{font-size:20px;font-weight:700;margin:16px 0 2px}
.meta{color:#a6a8ad;font-size:14px;min-height:20px}
.vol{display:flex;align-items:center;gap:10px;margin-top:18px}
.vol input{flex:1}.vbadge{font-variant-numeric:tabular-nums;width:42px;text-align:right;color:#a6a8ad}
button{width:100%;margin-top:14px;padding:11px;border:0;border-radius:10px;
background:#2a2d36;color:#e8e8ea;font-size:14px;cursor:pointer}button:active{background:#343843}
.svc{margin-top:14px;font-size:12px;color:#777;display:flex;gap:14px;justify-content:center}
</style></head><body><div class=card>
<div class=hdr><h1 id=name>__NAME__</h1><span id=state class=meta></span></div>
<div class=art id=art>♪</div>
<div id=np><div class=title id=title></div><div class=meta id=artist></div>
<div class=meta id=album></div></div>
<div class=vol><span>🔈</span><input type=range min=0 max=100 id=vol>
<span class=vbadge id=vbadge>–</span></div>
<button id=disc>Disconnect session</button>
<div class=svc id=svc></div></div><script>
let dragging=false;const $=id=>document.getElementById(id);
const post=(url,body)=>fetch(url,{method:'POST',headers:{'content-type':'application/json'},
 body:JSON.stringify(body||{})});
const vol=$('vol');vol.oninput=()=>{dragging=true;$('vbadge').textContent=vol.value+'%'};
vol.onchange=async()=>{await post('/api/volume',{percent:+vol.value});setTimeout(()=>dragging=false,800)};
$('disc').onclick=()=>post('/api/disconnect');
const dot=v=>{const s=document.createElement('span');s.className='dot '+(v===null?'unk':v?'ok':'bad');return s};
async function tick(){let s;try{s=await(await fetch('/api/status')).json()}catch(e){return}
 $('name').textContent=s.name;const n=s.nowplaying;
 if(n.active&&(n.title||n.artist)){
  $('title').textContent=n.title||'—';$('artist').textContent=n.artist||'';
  $('album').textContent=n.album||'';$('state').textContent='● playing';
  $('art').style.backgroundImage=n.cover?`url(/cover?r=${n.cover_rev||0})`:'';
  $('art').textContent=n.cover?'':'♪';}
 else{$('title').textContent='';$('artist').textContent='';$('album').textContent='';
  $('art').style.backgroundImage='';$('art').textContent='♪';$('state').textContent='idle';}
 if(!dragging){vol.value=n.volume_percent;$('vbadge').textContent=(n.muted?'muted':n.volume_percent+'%')}
 const svc=$('svc');svc.replaceChildren();
 for(const[k,v]of Object.entries(s.services)){const e=document.createElement('span');
  e.textContent=k.replace('-sync','').replace('-daemon','');e.append(dot(v));svc.append(e)}
 const d=s.doctor,e=document.createElement('span');e.textContent='doctor';
 e.title=d.ok===null?'no report yet':d.stale?'report is stale':d.failed.join(', ');
 e.append(dot(d.ok===null||d.stale?null:d.ok));svc.append(e)}
tick();setInterval(tick,2000);
</script></body></html>"""


def render_page(name: str = NAME) -> str:
    return PAGE.replace("__NAME__", html.escape(name))


class Handler(BaseHTTPRequestHandler):
    timeout = 10  # per-connection socket timeout: slow clients can't pin threads

    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json", headers=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def _host_ok(self) -> bool:
        if host_allowed(self.headers.get("Host", "")):
            return True
        self._send(421, b"unknown host", "text/plain")
        return False

    def do_GET(self):
        if not self._host_ok():
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, render_page(), "text/html; charset=utf-8", {"Cache-Control": "no-cache"})
        elif path == "/api/status":
            self._json(200, build_status())
        elif path == "/cover":
            self._send_cover()
        else:
            self._send(404, b"not found", "text/plain")

    def _send_cover(self):
        cover = read_state().get("cover")
        # Only the reader's own file names are ever served (no path traversal).
        if cover in ("cover.jpg", "cover.png", "cover.bin"):
            try:
                with open(os.path.join(STATE_DIR, cover), "rb") as fh:
                    data = fh.read()
            except OSError:
                data = None
            if data is not None:
                ctype = {"cover.png": "image/png", "cover.jpg": "image/jpeg"}.get(
                    cover, "application/octet-stream"
                )
                # The URL carries ?r=<cover_rev>, so a cached copy is never stale.
                self._send(200, data, ctype, {"Cache-Control": "private, max-age=86400"})
                return
        self._send(404, b"", "text/plain")

    def _read_json(self) -> dict | None:
        """The POST body as a JSON object, or None (after replying) if unacceptable."""
        ctype = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            # Cross-site forms/fetches can't send JSON without a CORS preflight,
            # which this server never answers.
            self._json(415, {"ok": False, "error": "content-type must be application/json"})
            return None
        if not origin_allowed(self.headers.get("Origin"), self.headers.get("Host", "")):
            self._json(403, {"ok": False, "error": "cross-origin request"})
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            self._json(413 if length > MAX_BODY else 400, {"ok": False, "error": "bad content-length"})
            return None
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = None
        if not isinstance(body, dict):
            self._json(400, {"ok": False, "error": "body must be a JSON object"})
            return None
        return body

    def do_POST(self):
        if not self._host_ok():
            return
        if self.path not in ("/api/volume", "/api/disconnect"):
            self._send(404, b"not found", "text/plain")
            return
        body = self._read_json()
        if body is None:
            return
        if self.path == "/api/volume":
            try:
                pct = int(body.get("percent", 0))
            except (ValueError, TypeError, OverflowError):
                self._json(400, {"ok": False, "error": "percent must be a number"})
                return
            self._json(200, {"ok": set_volume(pct)})
        else:
            self._json(200, {"ok": disconnect()})


class Server(ThreadingHTTPServer):
    daemon_threads = True


def make_server(bind: str = BIND, port: int = PORT) -> Server:
    """IPv4 or IPv6 listener depending on the bind address ('::' is dual-stack)."""
    family = socket.AF_INET6 if ":" in bind else socket.AF_INET
    cls = type("DashboardServer", (Server,), {"address_family": family})
    return cls((bind, port), Handler)


def main():  # pragma: no cover - server loop
    make_server().serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
