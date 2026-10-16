"""The local dashboard and its JSON API. Binds to 127.0.0.1 only."""
import json
import re
import sys
import time
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import CONFIG, DATA, DEMO, LIVE, MODEL, PORT, load, lock, save, update_settings
from .labeler import WAKE, day_sessions, model_ok

WEB = Path(__file__).parent / "web"


def nums(v, n):
    """Exactly n finite numbers of a sane size (screen coordinates from the page), or None."""
    try:
        out = [float(x) for x in v]
    except (TypeError, ValueError):
        return None
    return out if len(out) == n and all(abs(x) < 1e5 for x in out) else None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")  # always revalidate, so an update never shows yesterday's UI
        super().end_headers()

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        return json.loads(self.rfile.read(int(self.headers["Content-Length"])))

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/api/state":
            days = sorted(p.stem[9:] for p in DATA.glob("activity-*.jsonl"))
            return self.send_json({"config": CONFIG, "model": MODEL, "model_ok": model_ok(), "demo": DEMO, "days": days})
        if url.path == "/api/settings":
            return self.send_json({"settings": LIVE["settings"], "taskbar": LIVE.get("taskbar"),
                                   "platform": sys.platform, "island": not DEMO})
        if url.path == "/api/island":  # where the island sits on screen, so the dashboard can send things home to it
            return self.send_json({"island": LIVE.get("island"), "settings": LIVE["settings"]})
        if url.path == "/api/range":
            d, end = datetime.fromisoformat(q["from"]), datetime.fromisoformat(q["to"])
            out = {}
            while d <= end:
                key = d.strftime("%Y-%m-%d")
                out[key] = day_sessions(key)
                d += timedelta(days=1)
            return self.send_json(out)
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/edit":
            e = self.body()
            allowed = {k: e[k] for k in ("client", "task", "billable", "status") if k in e}
            with lock:
                edits = load("edits.json", {})
                edits.setdefault(e["id"], {}).update(allowed)
                save("edits.json", edits)
            WAKE.set()  # recount today now, so the island's numbers change as the change lands
            return self.send_json({"ok": True})
        if self.path == "/api/catch":  # something is flying from the dashboard to the island: tell it when it lands
            e, now = self.body(), time.time()
            ms = lambda k: min(3000, max(0, float(e.get(k) or 0))) / 1000
            color = e.get("color") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(e.get("color"))) else "#7a7a7a"
            c = {"id": f"{now:.6f}", "text": str(e.get("text", ""))[:60], "color": color,
                 "kind": str(e.get("kind", ""))[:12], "at": now + ms("delay_ms")}
            f = e.get("flight") if isinstance(e.get("flight"), dict) else None
            if f:  # the whole path in screen coordinates, so the island can draw the part outside the browser
                pts = {k: nums(f.get(k), 4 if k == "vp" else 2) for k in ("S", "C", "I", "vp")}
                if all(pts.values()) and f.get("edge") in ("top", "bottom", "left", "right"):
                    t0 = now + ms("start_ms")
                    c["flight"] = {**pts, "t0": t0, "lift": ms("lift_ms"), "dur": max(0.05, ms("dur_ms")),
                                   "size": nums([f.get("w"), f.get("h")], 2) or [80, 30], "label": str(f.get("label", ""))[:40],
                                   "edge": f["edge"]}
                    c["at"] = t0 + c["flight"]["lift"] + c["flight"]["dur"]
            LIVE["catches"] = (LIVE.get("catches", []) + [c])[-6:]
            return self.send_json({"ok": True})
        if self.path == "/api/settings":
            return self.send_json({"ok": True, "settings": update_settings(self.body())})
        self.send_json({"error": "not found"}, 404)


def make_server():
    return ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
