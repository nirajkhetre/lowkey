"""The local dashboard and its JSON API. Binds to 127.0.0.1 only, and only answers this machine's own pages."""
import json
import re
import socket
import sys
import time
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import focus
from .config import CONFIG, DATA, DEMO, LIVE, MODEL, PORT, load, lock, save, update_settings
from .labeler import WAKE, day_sessions, model_ok

WEB = Path(__file__).parent / "web"
STATUSES = ("pending", "billed", "nah")


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

    def allowed(self):
        """Only this machine's own pages get an answer. A foreign Host header means DNS rebinding (a website
        pretending to be localhost to read your activity); a foreign Origin means some site in your browser is
        trying to drive lowkey. Both get a 403."""
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        origin = self.headers.get("Origin")
        if self.headers.get("Host") in hosts and (not origin or origin.removeprefix("http://") in hosts):
            return True
        self.send_json({"error": "forbidden"}, 403)
        return False

    def guard(self, route):
        try:
            route()
        except (ValueError, KeyError, TypeError, AttributeError) as e:  # bad JSON, missing fields, wrong types
            self.send_json({"error": f"bad request ({e.__class__.__name__})"}, 400)

    def do_GET(self):
        if self.allowed():
            self.guard(self.get)

    def do_POST(self):
        if not self.allowed():
            return
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self.send_json({"error": "send JSON"}, 415)  # also makes browsers preflight, which we never allow
        self.guard(self.post)

    def get(self):
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
        if url.path == "/api/intents":  # now, what's next (with the reason), what got done today
            return self.send_json(focus.listing())
        if url.path == "/api/range":
            d, end = datetime.fromisoformat(q["from"]), datetime.fromisoformat(q["to"])
            if not timedelta(0) <= end - d <= timedelta(days=62):
                raise ValueError("range")
            out = {}
            while d <= end:
                key = d.strftime("%Y-%m-%d")
                out[key] = day_sessions(key)
                d += timedelta(days=1)
            return self.send_json(out)
        return super().do_GET()

    def post(self):
        if self.path == "/api/edit":
            e = self.body()
            if not isinstance(e.get("id"), str):
                raise ValueError("id")
            allowed = {k: e[k] for k in ("client", "task", "billable", "status") if k in e}
            if allowed.get("status", "pending") not in STATUSES or not isinstance(allowed.get("billable", True), bool):
                raise ValueError("status")
            for k in ("client", "task"):
                if k in allowed:
                    allowed[k] = str(allowed[k])[:300]
            with lock:
                edits = load("edits.json", {})
                edits.setdefault(e["id"][:80], {}).update(allowed)
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
        if self.path == "/api/intents/parse":  # live chips while you type: plain parsing only, instant
            p = focus.parse(str(self.body()["text"])[:200])
            return self.send_json({**p, "reason": focus.reason({**p, "created": time.time()}, time.time()) if p["text"] else ""})
        if self.path == "/api/intents":
            e = self.body()
            return self.send_json(focus.add(str(e["text"])[:200], e.get("start") if isinstance(e.get("start"), bool) else None))
        if self.path == "/api/intents/act":
            e = self.body()
            return self.send_json(focus.act(str(e["id"]), str(e["action"]), e.get("value")))
        self.send_json({"error": "not found"}, 404)


class Server(ThreadingHTTPServer):
    # On Windows, address reuse would let a second lowkey bind the same port and track twice; there we ask for
    # the port exclusively instead, so a second copy fails fast with a clear message.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(port=PORT):
    return Server(("127.0.0.1", port), Handler)
