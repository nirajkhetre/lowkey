"""Paths, your clients, island settings and the live state the island reads."""
import json
import os
import shutil
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = "--demo" in sys.argv
DATA = ROOT / ("demo" if DEMO else "data")
DATA.mkdir(exist_ok=True)

EXAMPLE = ROOT / "clients.example.json"
CLIENTS = ROOT / "clients.json"
if not CLIENTS.exists():
    shutil.copy(EXAMPLE, CLIENTS)  # your real clients live in clients.json, which git ignores
CONFIG = json.loads((EXAMPLE if DEMO else CLIENTS).read_text(encoding="utf-8"))  # demo week uses the demo clients

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
LIVE = {"paused": False, "idle": 0,  # shared between the tracker, the labeler and the island
        "settings": {**DEFAULTS, **(json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {})}}


def update_settings(changes):
    """Apply valid island settings (from the dashboard or the island itself) and remember them."""
    LIVE["settings"].update({k: v for k, v in changes.items() if v in CHOICES.get(k, ())})
    SETTINGS.write_text(json.dumps(LIVE["settings"], indent=1), encoding="utf-8")
    return LIVE["settings"]


def load(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def color(name):
    return next((c["color"] for c in CONFIG["clients"] if c["name"] == name), "#6b6b6b")


def rate(name):
    return next((c["rate"] for c in CONFIG["clients"] if c["name"] == name), 0)
