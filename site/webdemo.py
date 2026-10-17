"""The real lowkey API, answered inside a browser tab (Pyodide) for the web demo at lowkey.nirajlabs.tech.

The dashboard asks for /api/... as usual; site/demo.js hands each request to handle() instead of a server.
Same code as the app, run on the bundled demo week. Nothing is sent anywhere: there is no server.
"""
import json
import sys
import urllib.request


def no_network(*a, **kw):  # Pyodide would open a WebSocket to the visitor's own 127.0.0.1 for Ollama: never do that
    raise OSError("the web demo has no network")


urllib.request.urlopen = no_network
sys.argv = ["lowkey", "--demo"]
from lowkey import labeler, server  # noqa: E402

# Letting labeler think the model is up makes it replay what Gemma already wrote for the demo week (cached labels
# and day sentences); anything new fails at once and falls back to keyword rules. demo.js labels it as a replay.
labeler.model_ok = lambda: True


class Call(server.Handler):
    def __init__(self, path, body):  # no socket: only what get() and post() read
        self.path, self.raw, self.out = path, body.encode(), (404, {"error": "not found"})

    def send_json(self, obj, code=200):
        self.out = (code, obj)


def handle(method, path, body=""):
    c = Call(path, body or "{}")
    c.guard(c.get if method == "GET" else c.post)
    return json.dumps({"code": c.out[0], "body": c.out[1]}, ensure_ascii=False)
