"""Turns raw activity into billable sessions with a local open model (Gemma via Ollama).

activity -> 15-minute slots -> model labels each slot {client, task, billable}
         -> consecutive slots for one client become a session -> model merges notes into one invoice line
         -> plain code scores how well window titles back the client ("backed by your windows").
"""
import hashlib
import json
import threading
import time
import urllib.request
from collections import defaultdict
from datetime import datetime

from .config import CONFIG, DATA, LIVE, MODEL, OLLAMA, PERSONAL, SLOT_S, color, load, lock, rate, save


def slots_for(day):
    """Split the day's events into 15-min slots: {slot_start_ts: {(app, title): seconds}}."""
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


def chat(messages, schema, timeout=180):
    """One structured-output call to the local model. Thinking off: ~0.3s instead of ~9s on Gemma 4."""
    body = {"model": MODEL, "stream": False, "think": False, "format": schema, "options": {"temperature": 0},
            "messages": messages}
    req = urllib.request.Request(OLLAMA + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
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
        schema = {"type": "object", "required": ["client", "task", "billable", "confidence"], "properties": {
            "client": {"type": "string", "enum": clients + [PERSONAL]},  # the model cannot invent a client
            "task": {"type": "string"}, "billable": {"type": "boolean"}, "confidence": {"type": "number"}}}
        try:
            out = chat([{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": f"Clients and hints:\n{hints}\n\nActivity:\n{describe(windows)}"}], schema)
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
        prompt = ("Merge these work notes into ONE invoice line, past tense, max 90 chars, keep concrete details "
                  "(files, PR numbers, features), no client name:\n- " + "\n- ".join(tasks))
        try:
            cache[key] = chat([{"role": "user", "content": prompt}],
                              {"type": "object", "properties": {"line": {"type": "string"}}, "required": ["line"]}, 120)["line"]
            with lock:
                save("labels.json", cache)
        except Exception as e:
            print("summary failed:", e)
            return "; ".join(tasks)[:140]
    return cache[key]


def support(windows, client):
    """Share of the session's time whose window titles match the client's hints (Personal = no hints).
    Computed by plain code, not by the model, so it can't talk itself into 100%."""
    hints = {c["name"]: [h.lower() for h in c["hints"]] for c in CONFIG["clients"]}
    owner = lambda text: next((n for n, hs in hints.items() if any(h in text for h in hs)), PERSONAL)
    total = sum(windows.values()) or 1
    return round(sum(s for (a, t), s in windows.items() if owner(f"{a} {t}".lower()) == client) / total, 2)


_ok = [0, False]  # (checked_at, result): avoids a 2s connect timeout per request when Ollama is off


def model_ok():
    if time.time() - _ok[0] > 30:
        try:
            with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=2) as r:
                _ok[1] = any(m["name"].startswith(MODEL) for m in json.loads(r.read())["models"])
        except Exception:
            _ok[1] = False
        _ok[0] = time.time()
    return _ok[1]


def merge(slots, day):
    """Consecutive labelled slots for the same client become one session."""
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
    return sessions


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
    sessions = merge(slots, day)
    for s in sessions:
        tasks = s.pop("tasks")
        s["task"] = summarize(tasks, cache) if len(tasks) > 1 and use_model else "; ".join(tasks)[:140]
        s["confidence"] = support(s["_w"], s["client"])
        s["evidence"] = [{"app": a, "title": t, "s": round(v)} for (a, t), v in
                         sorted(s.pop("_w").items(), key=lambda kv: -kv[1])[:6]]
        s.pop("_last")
        s.update(edits.get(s["id"], {}))
    return sessions


# ---------- live feed for the island ----------
WAKE = threading.Event()  # set by a dashboard edit: recount now instead of waiting out the minute


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
        WAKE.wait(60)
        WAKE.clear()


def mark_personal():
    """Moves the current session to side quests. Returns a function that puts it back (for undo)."""
    sid = LIVE.get("session")
    if not sid:
        return None
    before = {k: LIVE.get(k) for k in ("client", "color")}
    with lock:
        edits = load("edits.json", {})
        old = dict(edits[sid]) if sid in edits else None
        edits.setdefault(sid, {}).update(client=PERSONAL, billable=False)
        save("edits.json", edits)
    LIVE.update(client=PERSONAL, color=color(PERSONAL))

    def undo():
        with lock:
            edits = load("edits.json", {})
            if old is None:
                edits.pop(sid, None)
            else:
                edits[sid] = old
            save("edits.json", edits)
        LIVE.update(before)
    return undo
