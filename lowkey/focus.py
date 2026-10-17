"""Intentions: say what you're about to do, and lowkey holds you to it, gently.

    capture  "acme login fix by 5, about an hour"  ->  text, client, due, estimate. Plain parsing you can predict;
             the model only helps pick a client when no name or hint in your words says it.
    order    what's next, and why: overdue first, then due soon, then the better-paid client, then whatever has
             waited longest. A rule you can read, not a black box.
    watch    every tracker sample: on it, neutral (a terminal, some docs: maybe part of the work) or drifting
             (another client's window, or a known distraction). Only drifting counts against you.

lowkey can't see how *finished* something is, so it never guesses a percentage: it measures time against your
estimate, and when you move on it asks you, with one tap, how far you got.
"""
import re
import threading
import time
from datetime import datetime, timedelta

from .config import CONFIG, LIVE, PERSONAL, SAMPLE_S, color, load, rate, save

FILE = "intents.json"
_cfg = CONFIG.get("focus", {})
NUDGE_S = 60 * _cfg.get("nudge_after_min", 8)    # drifting this long earns one gentle nudge
SWITCH_S = 60 * _cfg.get("ask_after_min", 10)     # on another client's work this long: ask how far you got
NUDGES_PER_HOUR, SNOOZE_S, BACK_S = 3, 30 * 60, 15 * 60
STEPS = (10, 50, 80, 100)                          # how far you got: just started, halfway, almost, done
DISTRACTIONS = {"youtube": "YouTube", "netflix": "Netflix", "instagram": "Instagram", "reddit": "Reddit",
                "twitter": "X", "x.com": "X", "facebook": "Facebook", "whatsapp": "WhatsApp", "tiktok": "TikTok",
                "prime video": "Prime Video", "hotstar": "Hotstar", "twitch": "Twitch", "steam": "Steam"}
DISTRACTIONS.update({d.lower(): d for d in CONFIG.get("distractions", [])})
STOP = set("about after again also and around before being could doing done fix fixed fixing from have into just "
           "make more need need some that then this today tomorrow update with work would your".split())

_lock = threading.Lock()
_xs = None                                          # intentions, cached in memory; written through on every change
W = {"drift_s": 0, "what": None, "kind": None, "nudges": [], "snooze": 0.0, "saved": 0.0, "prompt": None}


def _items():
    global _xs
    if _xs is None:
        _xs = [x for x in load(FILE, []) if isinstance(x, dict) and x.get("id")]
    return _xs


def _write():
    save(FILE, _xs)


# ---------- capture: plain parsing ----------
UNIT = r"(h|hrs?|hours?|m|mins?|minutes?)"
AMOUNT = r"(\d+(?:\.\d+)?|an?|half an?)"
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY = r"(today|tonight|eod|tomorrow|tmrw|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
SHORT_DAY = r"(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)"  # "sat down", "sun icon": only after by/on/due


LENGTH = rf"(?:\b(?:about|around|roughly|for)\s+|~\s*)?\b{AMOUNT}\s*{UNIT}\b"


def _minutes(n, unit):
    n = {"a": 1, "an": 1, "half a": 0.5, "half an": 0.5}.get(n.lower(), None) or float(n)
    return round(n * (60 if unit.lower().startswith("h") else 1))


def _hour(m):
    """A clock time from a match of (h)(:mm)?(am|pm)?: without am/pm, 1 to 7 read as afternoon (working hours)."""
    hour, minute, ap = int(m[1]), int(m[2] or 0), (m[3] or "").lower()
    return (hour % 12 + 12 if ap == "pm" else hour % 12 if ap == "am" else hour + 12 if hour < 8 else hour), minute


def _cut(t, m):
    return t[:m.start()] + " " + t[m.end():]


def _client(low):
    """The client whose name or hint appears in the words (the longest match wins), or None."""
    return max((c for c in CONFIG["clients"] if any(h in low for h in [c["name"].lower(), *map(str.lower, c["hints"])])),
               key=lambda c: max(len(h) for h in [c["name"], *c["hints"]] if h.lower() in low), default=None)


def _clean(t):
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"^[\s,;:\-·]+|[\s,;:\-·]+$", "", t)
    t = re.sub(r"(?:\s*[,;·-]?\s*\b(?:by|for|about|around|at|due|in|on|until|before|and|from|since)\b)+$", "", t, flags=re.I).strip(" ,;-·")
    return re.sub(r"^(?:of|for|to|on|about|and)\b\s*", "", t, flags=re.I)  # "half an hour of email" -> "email"


def parse(text, now=None):
    """'acme login fix by 5, about an hour' -> {text: 'acme login fix', client: 'Acme Studio', due: <today 17:00>,
    est_min: 60}. Times without am/pm read as working hours (by 5 means 5 pm); a time that has already passed
    today means tomorrow; a day without a time means the end of that working day (6 pm)."""
    now = now or time.time()
    t, base = " " + str(text)[:200] + " ", datetime.fromtimestamp(now)
    due = est = None
    m = re.search(rf"\bin\s+{AMOUNT}\s*{UNIT}\b", t, re.I)  # "in 2 hours" is a deadline, not a length
    if m:
        due, t = now + 60 * _minutes(m[1], m[2]), t[:m.start()] + " " + t[m.end():]
    m = re.search(LENGTH, t, re.I)
    if m:
        est, t = _minutes(m[1], m[2]), _cut(t, m)
    day = hour = minute = None
    m = (re.search(rf"\b(?:(?:by|before|on|due|until)\s+)?{DAY}\b", t, re.I)
         or re.search(rf"\b(?:by|before|on|due|until)\s+{SHORT_DAY}\b", t, re.I))
    if m:
        day, t = m[1].lower(), t[:m.start()] + " " + t[m.end():]
    m = (re.search(r"\b(?:by|before|at|until|due)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t, re.I)
         or re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t, re.I))
    if m and int(m[1]) <= 23:
        (hour, minute), t = _hour(m), _cut(t, m)
    if due is None and (day or hour is not None):
        d = base.replace(second=0, microsecond=0)
        if day in ("tomorrow", "tmrw"):
            d += timedelta(days=1)
        elif day and day not in ("today", "tonight", "eod"):
            want = next(i for i, n in enumerate(DAYS) if n.startswith(day[:3]))
            d += timedelta(days=(want - d.weekday()) % 7)
        hh, mm = (hour, minute) if hour is not None else ((21, 0) if day == "tonight" else (18, 0))
        d = d.replace(hour=hh, minute=mm)
        if d.timestamp() <= now and day not in ("today", "tonight", "eod", "tomorrow", "tmrw"):
            d += timedelta(days=7 if day else 1)  # "by 5" at 6 pm: tomorrow; "by friday" late on a friday: next week
        due = d.timestamp()
    client = _client(t.lower())
    return {"text": _clean(t), "client": client["name"] if client else None, "due": due, "est_min": est}


def entry(text, day, start=None, dur_min=None):
    """Time lowkey couldn't see, logged after the fact: '1h call with acme at 3pm' on the day you're looking at.
    A span picked on the timeline (start, dur_min) means the words only have to say what it was; a length or a time
    in the words still wins. With no start at all, the caller puts it after the day's last session. Nothing rolls
    forward to tomorrow here: a receipt is about the past."""
    t = " " + str(text)[:200] + " "
    m = re.search(LENGTH, t, re.I)
    if m:
        dur_min, t = _minutes(m[1], m[2]), _cut(t, m)
    elif not dur_min:
        raise ValueError("how long was it? add a length, like 1h or 30m")
    dur = int(dur_min)
    day0 = datetime.fromisoformat(day).timestamp()
    if start is not None and not day0 <= start < day0 + 86400:
        raise ValueError("start")
    m = (re.search(r"\b(?:at|from|since|by)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t, re.I)
         or re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t, re.I))
    if m and int(m[1]) <= 23:
        (hour, minute), t = _hour(m), _cut(t, m)
        start = datetime.fromisoformat(day).replace(hour=hour, minute=minute).timestamp()
    client = _client(t.lower())
    if not 0 < dur <= 16 * 60:
        raise ValueError("length")
    if start is not None and start + dur * 60 > time.time() + 60:
        raise ValueError("that hasn't happened yet")
    return {"text": _clean(t), "client": client["name"] if client else None, "start": start, "dur_min": dur}


def guess_client(text):
    """Only when nothing in the words named a client: ask the local model, constrained to your clients."""
    from .labeler import chat, model_ok
    if not model_ok():
        return None
    names = [c["name"] for c in CONFIG["clients"]]
    hints = "\n".join(f"- {c['name']}: {', '.join(c['hints'])}" for c in CONFIG["clients"])
    try:
        out = chat([{"role": "user", "content": f"Clients and hints:\n{hints}\n\nWhich client is this task for? "
                                                f"Answer none if it isn't client work.\nTask: {text}"}],
                   {"type": "object", "required": ["client"], "properties": {"client": {"type": "string", "enum": names + ["none"]}}}, 8)
        return out["client"] if out["client"] in names else None
    except Exception:
        return None


# ---------- order: a readable rule ----------
def span(s):
    s = max(0, int(s))
    if s < 3600:
        return f"{max(1, s // 60)}m"
    if s < 86400:
        h, m = s // 3600, s % 3600 // 60
        return f"{h}h {m}m" if m else f"{h}h"
    return f"{s // 86400}d"


def reason(it, now):
    due = it.get("due")
    if due is not None:
        left = due - now
        if left < 0:
            return f"overdue by {span(-left)}"
        if left < 6 * 3600:
            return f"due in {span(left)}"
        d, today = datetime.fromtimestamp(due), datetime.fromtimestamp(now).date()
        if d.date() == today:  # later today: the time reads better than a countdown
            return f"due {d.hour % 12 or 12}{f':{d.minute:02d}' if d.minute else ''} {'am' if d.hour < 12 else 'pm'}"
        return "due tomorrow" if d.date() == today + timedelta(days=1) else f"due {d:%a}".lower()
    r = rate(it["client"]) if it.get("client") else 0
    return f"{CONFIG['me']['currency']}{r:,}/h" if r else f"waiting {span(now - it['created'])}"


def order(xs, now):
    """Overdue, then due within a day and a half (soonest first), then the better-paid client, then the oldest."""
    def key(it):
        due = it.get("due")
        tier = 0 if due is not None and due < now else 1 if due is not None and due - now < 36 * 3600 else 2
        return tier, due if due is not None and tier < 2 else 0, -(rate(it["client"]) if it.get("client") else 0), it["created"]
    return sorted((x for x in xs if x["state"] == "next"), key=key)


# ---------- watch: on it, neutral, or drifting ----------
def _hits(text, client):
    c = next((c for c in CONFIG["clients"] if c["name"] == client), None)
    return bool(c) and any(h.lower() in text for h in [c["name"], *c["hints"]])


def keywords(text):
    return {w for w in re.findall(r"[a-z0-9][a-z0-9.\-]{3,}", text.lower()) if w not in STOP}


def judge(text, cur):
    """On it: your own words or your client's hints are in the window. Drifting: another client's, or a distraction.
    Everything else is neutral, because research and terminals are often part of the work."""
    if keywords(cur["text"]) & keywords(text) or (cur.get("client") and _hits(text, cur["client"])):
        return "on", None, None
    other = next((c["name"] for c in CONFIG["clients"] if c["name"] != cur.get("client") and _hits(text, c["name"])), None)
    if other:
        return "drift", other, "client"
    what = next((label for k, label in DISTRACTIONS.items() if k in text), None)
    return ("drift", what, "distraction") if what else ("neutral", None, None)


def current():
    return next((x for x in _items() if x["state"] == "now"), None)


def watch(app, title, active, now=None):
    """One tracker sample (every few seconds). Time on the intention grows while you're on it or neutral; drifting
    grows its own clock, which earns a nudge (rarely, and never while you're away) or, if you've clearly moved on
    to another client, a one-tap "how far did you get?"."""
    now = now or time.time()
    with _lock:
        cur = current()
        if not cur:
            W.update(drift_s=0, what=None, kind=None)
            return publish(now)
        verdict, what, kind = judge(f"{app} {title}".lower(), cur)
        if active:
            if verdict == "drift":
                W["drift_s"] += SAMPLE_S
                W["what"], W["kind"] = what, kind
            else:
                W.update(drift_s=0, what=None, kind=None)
                cur["spent_s"] = cur.get("spent_s", 0) + SAMPLE_S
        W["nudges"] = [t for t in W["nudges"] if now - t < 3600]
        if active and not W["prompt"] and now >= W["snooze"]:
            if W["kind"] == "client" and W["drift_s"] >= SWITCH_S:
                W["prompt"] = {"kind": "ask", "id": cur["id"], "at": now, "what": W["what"]}
            elif W["kind"] == "distraction" and W["drift_s"] >= NUDGE_S and len(W["nudges"]) < NUDGES_PER_HOUR:
                W["nudges"].append(now)
                W["prompt"] = {"kind": "nudge", "id": cur["id"], "at": now, "what": W["what"], "min": round(W["drift_s"] / 60)}
        if now - W["saved"] > 60:
            W["saved"] = now
            _write()
        LIVE["focus_verdict"] = verdict
    publish(now)


# ---------- changes ----------
def add(text, start=None, now=None):
    now = now or time.time()
    p = parse(text, now)
    if not p["text"]:
        raise ValueError("empty")
    if p["client"] is None:
        p["client"] = guess_client(p["text"])
    it = {"id": f"i{now:.3f}", **p, "created": now, "state": "next", "progress": 0, "spent_s": 0, "done_at": None}
    with _lock:
        xs = _items()
        if start or (start is None and not current()):
            for x in xs:
                if x["state"] == "now":
                    x["state"] = "next"
            it["state"] = "now"
            W.update(drift_s=0, what=None, kind=None, prompt=None)
        xs.append(it)
        _write()
    publish(now)
    return it


def act(iid, action, value=None, now=None):
    """start · progress (10/50/80/100) · done · drop · edit {text, client, due, est_min}"""
    now = now or time.time()
    with _lock:
        xs = _items()
        it = next((x for x in xs if x["id"] == iid), None)
        if not it:
            raise KeyError(iid)
        was_now = it["state"] == "now"
        if action == "start":
            for x in xs:
                if x["state"] == "now":
                    x["state"] = "next"
            it["state"] = "now"
            W.update(drift_s=0, what=None, kind=None, prompt=None)
        elif action in ("progress", "done"):
            p = 100 if action == "done" else int(value)
            if p not in STEPS:
                raise ValueError("progress")
            it["progress"] = p
            if p == 100:
                it.update(state="done", done_at=now)
            elif was_now:
                it["state"] = "next"  # paused where you left it; it keeps its place in line
            if was_now:  # suggest what's next, with its reason
                nxt = order(xs, now)
                nxt = [x for x in nxt if x["id"] != iid] or ([it] if p < 100 else [])
                W["prompt"] = ({"kind": "next", "id": nxt[0]["id"], "at": now, "done": it["text"] if p == 100 else None,
                                "spent": it.get("spent_s", 0)} if nxt else
                               {"kind": "done", "id": iid, "at": now, "spent": it.get("spent_s", 0)} if p == 100 else None)
        elif action == "drop":
            xs.remove(it)
            if was_now:
                W["prompt"] = None
        elif action == "edit":
            v = value if isinstance(value, dict) else {}
            if "text" in v and str(v["text"]).strip():
                it["text"] = str(v["text"]).strip()[:200]
            if "client" in v and (v["client"] is None or v["client"] in [c["name"] for c in CONFIG["clients"]] + [PERSONAL]):
                it["client"] = v["client"]
            if "due" in v and (v["due"] is None or isinstance(v["due"], (int, float))):
                it["due"] = v["due"]
            if "est_min" in v and (v["est_min"] is None or (isinstance(v["est_min"], int) and 0 < v["est_min"] < 1440)):
                it["est_min"] = v["est_min"]
        else:
            raise ValueError("action")
        _write()
    publish(now)
    return it


def respond(kind, value=None, now=None):
    """The island's answers to a prompt: back (on it), later (snooze), switch (ask how far), progress, start, dismiss."""
    now = now or time.time()
    p = W["prompt"]
    if kind == "back":
        W.update(drift_s=0, prompt=None, snooze=now + BACK_S)
    elif kind == "later":
        W.update(prompt=None, snooze=now + SNOOZE_S)
    elif kind == "dismiss":
        W["prompt"] = None
    elif kind == "switch" and current():
        W["prompt"] = {"kind": "ask", "id": current()["id"], "at": now, "what": None}
    elif kind == "progress" and p and p.get("id"):
        return act(p["id"], "progress", value, now)
    elif kind == "start" and p and p.get("id"):
        return act(p["id"], "start", None, now)
    publish(now)


def rename(old, new):
    with _lock:
        for x in _items():
            if x.get("client") == old:
                x["client"] = new
        _write()
    publish()


def publish(now=None):
    """A snapshot for the island and the dashboard (replaced whole, so readers never see it half-built)."""
    now = now or time.time()
    xs = _items()
    cur = current()
    view = lambda x: {"id": x["id"], "text": x["text"], "client": x.get("client"), "progress": x.get("progress", 0),
                      "color": color(x["client"]) if x.get("client") else "#9a9aa6", "due": x.get("due"),
                      "est_min": x.get("est_min"), "spent_s": x.get("spent_s", 0), "reason": reason(x, now)}
    p = W["prompt"]
    if p:
        target = next((x for x in xs if x["id"] == p.get("id")), None)
        p = {**p, "item": view(target)} if target else None
        if not p:
            W["prompt"] = None
    today = datetime.fromtimestamp(now).date()
    LIVE["focus"] = {"now": view(cur) if cur else None, "next": [view(x) for x in order(xs, now)[:3]],
                     "drift_min": W["drift_s"] // 60, "what": W["what"], "prompt": p,
                     "done_today": sum(1 for x in xs if x["state"] == "done" and x.get("done_at")
                                       and datetime.fromtimestamp(x["done_at"]).date() == today)}
    return LIVE["focus"]


def listing(now=None):
    """Everything the dashboard shows: now, the ordered queue with reasons, and what got done today."""
    now = now or time.time()
    xs = _items()
    today = datetime.fromtimestamp(now).date()
    focus = publish(now)
    done = [x for x in xs if x["state"] == "done" and x.get("done_at") and datetime.fromtimestamp(x["done_at"]).date() == today]
    with_reason = lambda x: {**x, "reason": reason(x, now), "color": color(x["client"]) if x.get("client") else "#9a9aa6"}
    return {"now": with_reason(current()) if current() else None,
            "next": [with_reason(x) for x in order(xs, now)], "done": [with_reason(x) for x in done],
            "drift_min": focus["drift_min"], "what": focus["what"], "verdict": LIVE.get("focus_verdict")}
