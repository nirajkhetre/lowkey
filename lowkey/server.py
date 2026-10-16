"""The local dashboard and its JSON API. Binds to 127.0.0.1 only."""
import json
import sys
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import CONFIG, DATA, DEMO, LIVE, MODEL, PORT, load, lock, save, update_settings
from .labeler import day_sessions, model_ok

WEB = Path(__file__).parent / "web"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, *a):
        pass

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
            return self.send_json({"ok": True})
        if self.path == "/api/settings":
            return self.send_json({"ok": True, "settings": update_settings(self.body())})
        self.send_json({"error": "not found"}, 404)


def make_server():
    return ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
