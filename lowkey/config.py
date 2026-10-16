"""Paths, your clients, island settings and the live state the island reads."""
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = "--demo" in sys.argv
DATA = ROOT / ("demo" if DEMO else "data")
DATA.mkdir(exist_ok=True)

EXAMPLE = ROOT / "clients.example.json"
CLIENTS = ROOT / "clients.json"
if not CLIENTS.exists():
    shutil.copy(EXAMPLE, CLIENTS)  # your real clients live in clients.json, which git ignores
try:
    CONFIG = json.loads((EXAMPLE if DEMO else CLIENTS).read_text(encoding="utf-8"))  # demo week uses the demo clients
except ValueError as e:
    sys.exit(f"lowkey: {CLIENTS.name} isn't valid JSON ({e}). Fix it, or delete it to start again from the example.")

MODEL = os.environ.get("LOWKEY_MODEL", "gemma4:e2b")
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
PORT = int(os.environ.get("LOWKEY_PORT", "7777"))
SAMPLE_S, AFK_S, SLOT_S = 5, 300, 15 * 60  # sample every 5s, idle after 5 min, label 15-min slots
PERSONAL = "Personal"
lock = threading.Lock()

SETTINGS = ROOT / "settings.json"
# On Windows the island floats over a same-edge taskbar by default (true notch look); macOS can't cover its menu bar.
DEFAULTS = {"edge": "top", "taskbar": "over" if sys.platform == "win32" else "below", "rest": "lip"}
CHOICES = {"edge": ("top", "bottom", "left", "right"), "taskbar": ("below", "over"), "rest": ("lip", "pill")}


def write_atomic(path, text):
    """Write to a temp file, then rename over the old one: a crash mid-write can't leave half a file behind."""
    tmp = path.with_name(f".{path.name}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_json(path, default):
    """A JSON file, or the default if it's missing. A corrupt one is moved aside (never overwritten) and reported."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        keep = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
        os.replace(path, keep)
        print(f"lowkey: {path.name} was unreadable; kept it as {keep.name} and started a fresh one", flush=True)
        return default


def update_settings(changes):
    """Apply valid island settings (from the dashboard or the island itself) and remember them."""
    LIVE["settings"].update({k: v for k, v in changes.items() if v in CHOICES.get(k, ())})
    write_atomic(SETTINGS, json.dumps(LIVE["settings"], indent=1))
    return LIVE["settings"]


saved = read_json(SETTINGS, {})
LIVE = {"paused": False, "idle": 0,  # shared between the tracker, the labeler and the island
        "settings": {**DEFAULTS, **{k: v for k, v in (saved.items() if isinstance(saved, dict) else ()) if v in CHOICES.get(k, ())}}}


def load(name, default):
    return read_json(DATA / name, default)


def save(name, obj):
    write_atomic(DATA / name, json.dumps(obj, indent=1, ensure_ascii=False))


def color(name):
    return next((c["color"] for c in CONFIG["clients"] if c["name"] == name), "#6b6b6b")


def rate(name):
    return next((c["rate"] for c in CONFIG["clients"] if c["name"] == name), 0)
