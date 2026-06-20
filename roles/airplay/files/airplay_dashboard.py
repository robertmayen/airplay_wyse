#!/usr/bin/env python3
"""airplay-dashboard — a tiny always-on web view for one AirPlay box.

Stdlib only. Shows now-playing (from airplay-nowplaying's JSON), cover art,
service health, and live volume; offers the controls that actually work with
modern Apple sources: a volume slider (shairport SetAirplayVolume over D-Bus)
and a disconnect button (DropSession). Transport (play/pause/next) is omitted
because iOS 17.4+/macOS 14.4+ ignore those commands from a receiver.
"""
from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NAME = os.environ.get("AIRPLAY_NAME", os.uname().nodename)
BIND = os.environ.get("AIRPLAY_DASHBOARD_BIND", "0.0.0.0")
PORT = int(os.environ.get("AIRPLAY_DASHBOARD_PORT", "8080"))
STATE_DIR = os.environ.get("AIRPLAY_STATE_DIR", "/run/airplay")
STATE_FILE = os.path.join(STATE_DIR, "nowplaying.json")

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
    options. Both were wrong before and the control silently did nothing.
    """
    return _BUS + [SVC_IFACE + ".RemoteControl", "SetAirplayVolume", "d", "--",
                   str(percent_to_db(percent))]


def disconnect_cmd() -> list:
    return _BUS + [SVC_IFACE, "DropSession"]


def _run(cmd) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def set_volume(percent: int) -> bool:
    return _run(volume_cmd(percent))


def disconnect() -> bool:
    return _run(disconnect_cmd())


def service_active(name: str) -> bool:
    try:
        out = subprocess.run(["systemctl", "is-active", name],
                             capture_output=True, text=True, timeout=5).stdout
        return out.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


def read_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"active": False, "title": "", "artist": "", "album": "",
                "volume_percent": 0, "muted": False, "cover": None}


def build_status() -> dict:
    return {
        "name": NAME,
        "nowplaying": read_state(),
        "services": {s: service_active(s) for s in ("shairport-sync", "nqptp", "avahi-daemon")},
    }


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
.ok{background:#3ddc84}.bad{background:#ff5b5b}
.art{width:100%;aspect-ratio:1;border-radius:12px;background:#23262e center/cover no-repeat;
display:flex;align-items:center;justify-content:center;color:#555;font-size:40px}
.title{font-size:20px;font-weight:700;margin:16px 0 2px}
.meta{color:#a6a8ad;font-size:14px;min-height:20px}
.idle{color:#6a6c72;text-align:center;padding:30px 0;font-size:15px}
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
const vol=$('vol');vol.oninput=()=>{dragging=true;$('vbadge').textContent=vol.value+'%'};
vol.onchange=async()=>{await fetch('/api/volume',{method:'POST',
 headers:{'content-type':'application/json'},body:JSON.stringify({percent:+vol.value})});
 setTimeout(()=>dragging=false,800)};
$('disc').onclick=()=>fetch('/api/disconnect',{method:'POST'});
async function tick(){let s;try{s=await(await fetch('/api/status')).json()}catch(e){return}
 $('name').textContent=s.name;const n=s.nowplaying;
 if(n.active&&(n.title||n.artist)){$('np').style.display='';$('idle')&&$('idle').remove();
  $('title').textContent=n.title||'—';$('artist').textContent=n.artist||'';
  $('album').textContent=n.album||'';$('state').textContent='● playing';
  $('art').style.backgroundImage=n.cover?`url(/cover?${n.updated})`:'';
  $('art').textContent=n.cover?'':'♪';}
 else{$('title').textContent='';$('artist').textContent='';$('album').textContent='';
  $('art').style.backgroundImage='';$('art').textContent='♪';$('state').textContent='idle';}
 if(!dragging){vol.value=n.volume_percent;$('vbadge').textContent=(n.muted?'muted':n.volume_percent+'%')}
 $('svc').innerHTML=Object.entries(s.services).map(([k,v])=>
  `${k.replace('-sync','').replace('-daemon','')} <span class="dot ${v?'ok':'bad'}"></span>`).join('');}
tick();setInterval(tick,2000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, PAGE.replace("__NAME__", NAME), "text/html; charset=utf-8")
        elif path == "/api/status":
            self._send(200, json.dumps(build_status()))
        elif path == "/cover":
            cover = read_state().get("cover")
            fp = os.path.join(STATE_DIR, cover) if cover else None
            if fp and os.path.isfile(fp):
                with open(fp, "rb") as fh:
                    data = fh.read()
                ctype = "image/png" if cover.endswith(".png") else "image/jpeg"
                self._send(200, data, ctype)
            else:
                self._send(404, b"")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        if self.path == "/api/volume":
            try:
                pct = int(json.loads(raw).get("percent", 0))
            except (ValueError, TypeError):
                self._send(400, json.dumps({"ok": False}))
                return
            self._send(200, json.dumps({"ok": set_volume(pct)}))
        elif self.path == "/api/disconnect":
            self._send(200, json.dumps({"ok": disconnect()}))
        else:
            self._send(404, b"not found", "text/plain")


def main():  # pragma: no cover - server loop
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
