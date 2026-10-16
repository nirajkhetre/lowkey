"""lowkey — bills your hours, lowkey. Everything stays on this machine.

python lowkey.py           track this PC + serve the app on http://127.0.0.1:7777
python lowkey.py --demo    serve the bundled demo week (no tracking)
"""
import ctypes, hashlib, json, os, sys, threading, time, urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    import ctypes.wintypes  # tracker is Windows-only; demo mode runs anywhere
except (ImportError, ValueError):
    pass

ROOT = Path(__file__).parent
DEMO = "--demo" in sys.argv
DATA = ROOT / ("demo" if DEMO else "data")
DATA.mkdir(exist_ok=True)
CONFIG = json.loads((ROOT / "clients.json").read_text(encoding="utf-8"))
MODEL = os.environ.get("LOWKEY_MODEL", "gemma4:e2b")
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
SAMPLE_S, AFK_S, SLOT_S = 5, 300, 15 * 60
PERSONAL = "Personal"
lock = threading.Lock()
LIVE = {"paused": False, "idle": 0}  # shared with the island


# ---------- tracker (Windows, stdlib only) ----------
def foreground():
    u32, k32, w = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.wintypes
    hwnd = u32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(hwnd, buf, 512)
    pid = w.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    app = ""
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        pbuf, size = ctypes.create_unicode_buffer(260), w.DWORD(260)
        if k32.QueryFullProcessImageNameW(h, 0, pbuf, ctypes.byref(size)):
            app = os.path.basename(pbuf.value)
        k32.CloseHandle(h)

    class LII(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    lii = LII(ctypes.sizeof(LII), 0)
    u32.GetLastInputInfo(ctypes.byref(lii))
    idle = (k32.GetTickCount() - lii.dwTime) / 1000
    return app, buf.value, idle, pid.value


def track():
    never = [s.lower() for s in CONFIG.get("never_track", [])]
    while True:
        try:
            app, title, idle, pid = foreground()
            LIVE["idle"] = idle
            text = f"{app} {title}".lower()
            if title and pid != os.getpid() and idle < AFK_S and not LIVE["paused"] and not any(n in text for n in never):
                ev = {"ts": round(time.time()), "dur": SAMPLE_S, "app": app, "title": title[:200]}
                minutes = LIVE.setdefault("minutes", {})  # feeds the island's activity bars
                m = int(time.time() // 60)
                minutes[m] = minutes.get(m, 0) + SAMPLE_S
                for old in [k for k in minutes if k < m - 60]:
                    del minutes[old]
                day = datetime.now().strftime("%Y-%m-%d")
                with open(DATA / f"activity-{day}.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception as e:  # never let the tracker die
            print("tracker:", e)
        time.sleep(SAMPLE_S)


# ---------- labelling ----------
def slots_for(day):
    """Split the day's events into 15-min slots: {slot_start_ts: {(app,title): seconds}}."""
    path = DATA / f"activity-{day}.jsonl"
    slots = defaultdict(lambda: defaultdict(float))
    if not path.exists():
        return slots
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        t, end = ev["ts"], ev["ts"] + ev["dur"]
        while t < end:  # events can straddle slot boundaries
            start = t - t % SLOT_S
            cut = min(end, start + SLOT_S)
            slots[start][(ev["app"], ev["title"])] += cut - t
            t = cut
    return slots


def describe(windows):
    top = sorted(windows.items(), key=lambda kv: -kv[1])[:8]
    return "\n".join(f"- {round(s / 60, 1)}m  {app} | {title}" for (app, title), s in top)


SYSTEM = """You turn a freelancer's computer activity into timesheet entries.
Given ~15 minutes of window titles and the client list, decide:
- client: which client this work was for, or "Personal" for non-work (social media, entertainment, personal chats, shopping).
- task: a short, specific, invoice-ready line in past tense (max 70 chars), e.g. "Built checkout page for Shopify theme". No client name, no emojis.
- billable: true only if it is real work for that client.
- confidence: 0..1, how sure you are about the client.
Use the client hints (repo names, domains, project names) as strong evidence. Never invent a client."""


def ask_model(prompt, clients):
    schema = {
        "type": "object",
        "properties": {
            "client": {"type": "string", "enum": clients + [PERSONAL]},
            "task": {"type": "string"},
            "billable": {"type": "boolean"},
            "confidence": {"type": "number"},
        },
        "required": ["client", "task", "billable", "confidence"],
    }
    body = {"model": MODEL, "stream": False, "think": False, "format": schema, "options": {"temperature": 0},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    req = urllib.request.Request(OLLAMA + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(json.loads(r.read())["message"]["content"])


def rules(windows):
    """Keyword baseline: also the fallback when no local model is running."""
    score = defaultdict(float)
    for (app, title), s in windows.items():
        text = f"{app} {title}".lower()
        for c in CONFIG["clients"]:
            if any(h.lower() in text for h in c["hints"]):
                score[c["name"]] += s
    (app, title), _ = max(windows.items(), key=lambda kv: kv[1])
    client = max(score, key=score.get) if score else PERSONAL
    return {"client": client, "task": title[:70], "billable": client != PERSONAL, "confidence": 0.3, "by": "rules"}


def label(windows, use_model=True):
    if use_model:
        clients = [c["name"] for c in CONFIG["clients"]]
        hints = "\n".join(f"- {c['name']}: {', '.join(c['hints'])}" for c in CONFIG["clients"])
        try:
            out = ask_model(f"Clients and hints:\n{hints}\n\nActivity:\n{describe(windows)}", clients)
            out["by"] = MODEL
            out["billable"] = out["billable"] and out["client"] != PERSONAL
            return out
        except Exception as e:
            print("model unavailable, using rules:", e)
    return rules(windows)


def summarize(tasks, cache):
    """Second pass: one clean invoice line per merged session (cached in labels.json)."""
    key = "sum:" + hashlib.sha1("|".join(tasks).encode()).hexdigest()[:16]
    if key not in cache:
        body = {"model": MODEL, "stream": False, "think": False, "options": {"temperature": 0},
                "format": {"type": "object", "properties": {"line": {"type": "string"}}, "required": ["line"]},
                "messages": [{"role": "user", "content": "Merge these work notes into ONE invoice line, past tense, "
                              "max 90 chars, keep concrete details (files, PR numbers, features), no client name:\n- "
                              + "\n- ".join(tasks)}]}
        try:
            req = urllib.request.Request(OLLAMA + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                cache[key] = json.loads(json.loads(r.read())["message"]["content"])["line"]
            with lock:
                save("labels.json", cache)
        except Exception as e:
            print("summary failed:", e)
            return "; ".join(tasks)[:140]
    return cache[key]


def support(windows, client):
    """How much of the session's time is backed by window titles matching the client's hints (Personal = no hints).
    Computed by plain code, not by the model, so it can't be talked into 100%."""
    hints = {c["name"]: [h.lower() for h in c["hints"]] for c in CONFIG["clients"]}
    owner = lambda text: next((n for n, hs in hints.items() if any(h in text for h in hs)), PERSONAL)
    total = sum(windows.values()) or 1
    return round(sum(s for (a, t), s in windows.items() if owner(f"{a} {t}".lower()) == client) / total, 2)


_ok = [0, False]  # (checked_at, result): avoids a 2s connect timeout per day when Ollama is off


def model_ok():
    if time.time() - _ok[0] > 30:
        try:
            with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=2) as r:
                _ok[1] = any(m["name"].startswith(MODEL) for m in json.loads(r.read())["models"])
        except Exception:
            _ok[1] = False
        _ok[0] = time.time()
    return _ok[1]


def load(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def day_sessions(day):
    slots = slots_for(day)
    with lock:
        cache = load("labels.json", {})
        use_model = model_ok()
        for start, windows in slots.items():
            key = hashlib.sha1((MODEL + describe(windows)).encode()).hexdigest()[:16]
            if key not in cache or (use_model and cache[key].get("by") == "rules"):
                cache[key] = label(windows, use_model)
                save("labels.json", cache)
            slots[start] = (windows, cache[key])
    edits = load("edits.json", {})

    # merge consecutive slots with the same client into sessions
    sessions = []
    for start in sorted(slots):
        windows, lab = slots[start]
        active = sum(windows.values())
        prev = sessions[-1] if sessions else None
        if prev and prev["client"] == lab["client"] and start - prev["_last"] <= SLOT_S:
            prev["active_s"] += active
            prev["end"] = start + SLOT_S
            prev["_last"] = start
            if lab["task"] not in prev["tasks"]:
                prev["tasks"].append(lab["task"])
            for k, s in windows.items():
                prev["_w"][k] += s
        else:
            sessions.append({"id": f"{day}-{start}", "start": start, "end": start + SLOT_S, "_last": start,
                             "active_s": active, "client": lab["client"], "tasks": [lab["task"]],
                             "billable": lab["billable"], "by": lab["by"],
                             "_w": defaultdict(float, windows), "status": "pending"})
    for s in sessions:
        tasks = s.pop("tasks")
        s["task"] = summarize(tasks, cache) if len(tasks) > 1 and use_model else "; ".join(tasks)[:140]
        s["confidence"] = support(s["_w"], s["client"])
        s["evidence"] = [{"app": a, "title": t, "s": round(v)} for (a, t), v in
                         sorted(s.pop("_w").items(), key=lambda kv: -kv[1])[:6]]
        s.pop("_last")
        s.update(edits.get(s["id"], {}))
    return sessions


# ---------- island feed ----------
def color(name):
    return next((c["color"] for c in CONFIG["clients"] if c["name"] == name), "#6b6b6b")


def rate(name):
    return next((c["rate"] for c in CONFIG["clients"] if c["name"] == name), 0)


def refresh():
    # ponytail: relabels the still-growing current slot every minute; labels.json keeps those partial entries
    while True:
        try:
            sess = day_sessions(datetime.now().strftime("%Y-%m-%d"))
            bill = [s for s in sess if s["billable"] and s["client"] != PERSONAL and s["status"] != "nah"]
            LIVE.update(today_s=sum(s["active_s"] for s in bill),
                        money=sum(s["active_s"] / 3600 * rate(s["client"]) for s in bill),
                        pending=sum(s["status"] == "pending" for s in sess))
            if sess:
                last = sess[-1]
                LIVE.update(client=last["client"], task=last["task"], session=last["id"], color=color(last["client"]),
                            session_start=last["start"])
        except Exception as e:
            print("refresh:", e)
        time.sleep(60)


def mark_personal():
    if LIVE.get("session"):
        with lock:
            edits = load("edits.json", {})
            edits.setdefault(LIVE["session"], {}).update(client=PERSONAL, billable=False)
            save("edits.json", edits)
        LIVE.update(client=PERSONAL, color=color(PERSONAL))


# ---------- web ----------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "web"), **kw)

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/api/state":
            days = sorted(p.stem[9:] for p in DATA.glob("activity-*.jsonl"))
            return self.send_json({"config": CONFIG, "model": MODEL, "model_ok": model_ok(), "demo": DEMO, "days": days})
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
            e = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            allowed = {k: e[k] for k in ("client", "task", "billable", "status") if k in e}
            with lock:
                edits = load("edits.json", {})
                edits.setdefault(e["id"], {}).update(allowed)
                save("edits.json", edits)
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)


if __name__ == "__main__":
    print(f"lowkey {'(demo) ' if DEMO else ''}-> http://127.0.0.1:7777   model: {MODEL} ({'ready' if model_ok() else 'not found, using keyword rules'})")
    server = ThreadingHTTPServer(("127.0.0.1", 7777), Handler)
    if DEMO or "--no-island" in sys.argv:
        server.serve_forever()
    else:
        from island import Island
        for job in (track, refresh, server.serve_forever):
            threading.Thread(target=job, daemon=True).start()
        Island(LIVE, {"personal": mark_personal}, CONFIG["me"]["currency"], CONFIG["me"].get("daily_goal_h", 6)).run()
