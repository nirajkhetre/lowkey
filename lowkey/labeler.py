"""Turns raw activity into billable sessions with a local open model (Gemma via Ollama).

activity -> 15-minute slots -> model labels each slot {client, task, billable}
         -> consecutive slots for one client become a session -> model merges notes into one invoice line
         -> plain code scores how well window titles back the client ("backed by your windows").
"""
import hashlib
import json
import re
import threading
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

from .config import CONFIG, DATA, DEMO, LIVE, MODEL, OLLAMA, PERSONAL, SLOT_S, color, load, lock, rate, save, save_config


def reviewed(day):
    """Has anything of this day been billed, left off or moved? Those edits point at its sessions by start time."""
    return any(k.startswith(f"{day}-") for k in load("edits.json", {}))


def slot_len(day):
    """Seconds of windows per label for a day. A day keeps the length it was first labelled with, so your reviews
    keep pointing at the same sessions: a new "reads every" applies today only if nothing today is reviewed yet,
    otherwise from tomorrow. Days from before the setting existed were 15-minute days."""
    today = datetime.now().strftime("%Y-%m-%d")
    fixed = load("slots.json", {})
    if day != today:
        return fixed.get(day, SLOT_S)
    want = int(LIVE["settings"].get("slot", "5")) * 60
    if DEMO:
        return want
    if fixed.get(today) != want and (today not in fixed or not reviewed(today)):
        with lock:
            fixed = load("slots.json", {})
            # first sight of a day you already reviewed (the update that brought this setting): it was a 15-minute day
            fixed[today] = SLOT_S if today not in fixed and reviewed(today) else want
            save("slots.json", fixed)
    return fixed[today]


def slots_for(day):
    """Split the day's events into slots: {slot_start_ts: {(app, title): seconds}}."""
    path = DATA / f"activity-{day}.jsonl"
    slots = defaultdict(lambda: defaultdict(float))
    slot = slot_len(day)
    if not path.exists():
        return slots
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        t, end = ev["ts"], ev["ts"] + ev["dur"]
        while t < end:  # events can straddle slot boundaries
            start = t - t % slot
            cut = min(end, start + slot)
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


_busy = []  # what the model is doing right now, newest last: the island and the dashboard show it while it happens


def chat(messages, schema, timeout=180, what="thinking"):
    """One structured-output call to the local model. Thinking off: ~0.3s instead of ~9s on Gemma 4."""
    body = {"model": MODEL, "stream": False, "think": False, "format": schema, "options": {"temperature": 0},
            "messages": messages}
    req = urllib.request.Request(OLLAMA + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    _busy.append(what)
    LIVE["thinking"], t0 = what, time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(json.loads(r.read())["message"]["content"])
    finally:
        _busy.remove(what)
        LIVE["thinking"] = _busy[-1] if _busy else None
        LIVE["thought"] = {"what": what, "ms": round((time.time() - t0) * 1000), "at": time.time()}


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
                        {"role": "user", "content": f"Clients and hints:\n{hints}\n\nActivity:\n{describe(windows)}"}], schema,
                       what=f"reading {max(1, round(sum(windows.values()) / 60))} min of your windows")
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
                              {"type": "object", "properties": {"line": {"type": "string"}}, "required": ["line"]}, 120,
                              "writing the invoice line")["line"]
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
    sessions, slot = [], slot_len(day)
    for start in sorted(slots):
        windows, lab = slots[start]
        active = sum(windows.values())
        prev = sessions[-1] if sessions else None
        if prev and prev["client"] == lab["client"] and start - prev["_last"] <= slot:
            prev["active_s"] += active
            prev["end"] = start + slot
            prev["_last"] = start
            if lab["task"] not in prev["tasks"]:
                prev["tasks"].append(lab["task"])
            for k, s in windows.items():
                prev["_w"][k] += s
        else:
            sessions.append({"id": f"{day}-{start}", "start": start, "end": start + slot, "_last": start,
                             "active_s": active, "client": lab["client"], "tasks": [lab["task"]],
                             "billable": lab["billable"], "by": lab["by"],
                             "_w": defaultdict(float, windows), "status": "pending"})
    return sessions


def labeled(day):
    """The day's 15-minute slots with their labels (cached, so each slot is labelled once): {start: (windows, label)}."""
    slots = slots_for(day)
    with lock:
        cache = load("labels.json", {})
        use_model = model_ok()
        for start, windows in slots.items():
            key = hashlib.sha1((MODEL + describe(windows)).encode()).hexdigest()[:16]
            if key not in cache or (use_model and cache[key].get("by") == "rules"):
                cache[key] = label(windows, use_model)
                save("labels.json", cache)
                LIVE["labels_rev"] = LIVE.get("labels_rev", 0) + 1  # the dashboard sees a new line and fetches it
            slots[start] = (windows, cache[key])
    return slots, cache, use_model


def day_sessions(day):
    slots, cache, use_model = labeled(day)
    edits = load("edits.json", {})
    sessions = merge(slots, day)
    for s in sessions:
        tasks = s.pop("tasks")
        s["task"] = summarize(tasks, cache) if len(tasks) > 1 and use_model else "; ".join(tasks)[:140]
        s["confidence"] = support(s["_w"], s["client"])
        s["evidence"] = [{"app": a, "title": t, "s": round(v)} for (a, t), v in
                         sorted(s.pop("_w").items(), key=lambda kv: -kv[1])[:6]]
        s.pop("_last")
    sessions += [m for m in load("manual.json", []) if m.get("day") == day]  # time you logged yourself
    for s in sessions:
        e = edits.get(s["id"], {})
        s.update(e)
        s["edited"] = sorted(k for k in ("client", "task") if k in e)  # so the page can say who wrote what: you or the model
    return sorted(sessions, key=lambda s: s["start"])


# ---------- the model in its own words ----------
def brief(day):
    """The day in a sentence or two, written by the model from the receipts (never from raw window titles).
    Cached by content, so it's rewritten only when the day changes. No model, no brief: nothing is faked."""
    sess = [s for s in day_sessions(day) if s.get("status") != "nah"]
    if not sess or not model_ok():
        return None
    lines = "\n".join(f"- {round(s['active_s'] / 60)} min, {'side quest' if s['client'] == PERSONAL else s['client']}: "
                      f"{s['task']}" for s in sess)
    key = "brief:" + hashlib.sha1(lines.encode()).hexdigest()[:16]
    cache = load("labels.json", {})
    if key not in cache:
        prompt = ("Timesheet lines from a freelancer's day, in order (minutes, client, what got done):\n" + lines +
                  "\n\nTell them how their day went in 1-2 short sentences (max 200 characters), the way a sharp friend would "
                  "after reading it. Lead with the most concrete win (a feature, a fix, a file), then where the rest of the time "
                  "went. Your own words: never copy a line, no times, no minutes. Use client names as written. Second person, "
                  "all lowercase, casual. Only facts from the lines. No money, no emojis, no judgement about side quests.")
        try:
            out = chat([{"role": "user", "content": prompt}],
                       {"type": "object", "required": ["line"], "properties": {"line": {"type": "string"}}}, 60,
                       "writing your day")["line"].strip()
        except Exception as e:
            print("brief failed:", e)
            return None
        with lock:
            cache = load("labels.json", {})
            cache[key] = out.lower()[:300]
            save("labels.json", cache)
    return {"text": cache[key], "by": MODEL, "lines": len(sess)}


GENERIC = {"chrome", "google chrome", "edge", "firefox", "github", "gitlab", "figma", "slack", "notion", "untitled",
           "new tab", "code", "visual studio code", "terminal", "powershell", "docs", "google docs", "localhost", "home"}


def suggest_hint(day, sid, client):
    """You moved a session to a client: the model picks a keyword from its windows that should mean that client
    from now on. Plain code checks it really is in those windows, isn't generic, and isn't a hint already."""
    s = next((x for x in day_sessions(day) if x["id"] == sid), None)
    titles = [e["title"] for e in (s or {}).get("evidence", []) if e.get("title")][:6]
    if not titles or client == PERSONAL or not model_ok():
        return None
    try:
        k = chat([{"role": "user", "content": f'These windows were work for the client "{client}":\n- ' + "\n- ".join(titles) +
                  "\n\nCopy ONE short keyword exactly as it appears in a title (a repo, file, domain or project name, "
                  "3-30 characters) that would identify this client's work next time. Not an app name or a generic word."}],
                 {"type": "object", "required": ["keyword"], "properties": {"keyword": {"type": "string"}}}, 30,
                 "learning from your fix")["keyword"].strip()
    except Exception:
        return None
    have = {h.lower() for c in CONFIG["clients"] for h in c["hints"]}
    if not 3 <= len(k) <= 30 or k.lower() in GENERIC or k.lower() in have or not any(k.lower() in t.lower() for t in titles):
        return None
    return k


def teach(client, hint, forget=False):
    """Add (or take back) a hint. Hints go into every label prompt and the keyword rules, so the next slots use it.
    The demo's clients only change in memory."""
    c = next((c for c in CONFIG["clients"] if c["name"] == client), None)
    hint = str(hint).strip()[:40]
    if c is None:
        raise KeyError(client)
    if len(hint) < 3:
        raise ValueError("hint")
    hs = [h for h in c["hints"] if h.lower() != hint.lower()]
    c["hints"] = hs if forget else hs + [hint]
    if not DEMO:
        save_config({}, CONFIG["clients"])
    return c


# ---------- receipts you add yourself ----------
def add_manual(text, day, start=None, dur_min=None):
    """'1h call with acme at 3pm': a session lowkey couldn't see (a call, a meeting, work on paper). With no start
    time it goes right after the day's last session, or ends now if that would be in the future."""
    from .focus import entry, guess_client
    e = entry(text, day, start, dur_min)
    if not e["text"]:
        raise ValueError("what was it?")
    dur = e["dur_min"] * 60
    start = e["start"]
    if start is None:
        ends = [s["end"] for s in day_sessions(day)]
        start = max(ends) if ends else datetime.fromisoformat(day).replace(hour=9).timestamp()
        start = min(start, time.time() - dur)
    client = e["client"] or guess_client(e["text"]) or PERSONAL  # no client named: the local model guesses, like intentions
    m = {"id": f"m-{day}-{int(start)}-{int(time.time() * 1000) % 100000}", "day": day, "start": start, "end": start + dur,
         "active_s": dur, "client": client, "task": e["text"][0].upper() + e["text"][1:], "billable": client != PERSONAL,
         "by": "you", "confidence": 1.0, "evidence": [], "status": "pending", "manual": True}
    with lock:
        save("manual.json", load("manual.json", []) + [m])
    return m


def delete_manual(mid):
    with lock:
        rows = load("manual.json", [])
        if not any(m["id"] == mid for m in rows):
            raise KeyError(mid)
        save("manual.json", [m for m in rows if m["id"] != mid])
        edits = load("edits.json", {})
        if edits.pop(mid, None) is not None:
            save("edits.json", edits)


def rename_client(old, new):
    """Renaming a client keeps its history: cached labels, your edits, your receipts and intentions follow it."""
    from . import focus
    with lock:
        for name in ("labels.json", "edits.json"):
            data, changed = load(name, {}), False
            for v in data.values():
                if isinstance(v, dict) and v.get("client") == old:
                    v["client"], changed = new, True
            if changed:
                save(name, data)
        rows = load("manual.json", [])
        if any(m.get("client") == old for m in rows):
            save("manual.json", [{**m, "client": new} if m.get("client") == old else m for m in rows])
    focus.rename(old, new)


# ---------- off the clock ----------
LIFE = ("watching", "gaming", "social", "messaging", "music", "shopping & food", "reading & learning", "browsing", "other")
LIFE_HINTS = {  # the obvious ones are settled by plain code; the model only sees what these don't cover
    "watching": ["netflix", "youtube", "prime video", "hotstar", "jiocinema", "disney+", "twitch", "vlc", "crunchyroll", "mx player"],
    "gaming": ["steam", "epic games", "valorant", "riot client", "minecraft", "roblox", "battle.net", "xbox", "genshin", "bgmi"],
    "social": ["instagram", "twitter", "x.com", "facebook", "reddit", "tiktok", "snapchat", "pinterest", "threads"],
    "messaging": ["whatsapp", "telegram", "discord", "signal", "messenger"],
    "music": ["spotify", "apple music", "youtube music", "soundcloud", "gaana", "jiosaavn"],
    "shopping & food": ["amazon", "flipkart", "myntra", "swiggy", "zomato", "blinkit", "zepto", "ajio", "meesho", "bigbasket"],
    "reading & learning": ["wikipedia", "medium", "kindle", "coursera", "udemy", "duolingo", "substack"]}
BROWSERS = ("chrome", "msedge", "firefox", "brave", "opera", "vivaldi", "safari", "arc")
BROWSER_NAMES = ("google chrome", "microsoft edge", "mozilla firefox", "brave", "opera", "vivaldi", "safari", "personal", "profile", "new tab")


def source(app, title):
    """Where the time went, the way you'd say it: the site for a browser tab ("YouTube"), otherwise the app.
    A browser with no site in its title (a new tab) is nowhere: None."""
    a = re.sub(r"\.(exe|app)$", "", app.strip(), flags=re.I)
    if any(b in a.lower() for b in BROWSERS):
        parts = [re.sub(r"^\(\d+\)\s*|\s*\([^)]*\)$", "", p.strip()) for p in re.split(r"\s[-|–—·]\s", title)]  # "· GitHub" too
        parts = [p for p in parts if p and not any(b in p.lower() for b in BROWSER_NAMES)]
        known = next((p for p in parts if any(h in p.lower() for hs in LIFE_HINTS.values() for h in hs)), None)
        return (known or parts[-1])[:40] if parts else None  # a site we know wins wherever it sits in the title
    return a[:1].upper() + a[1:40]


def category(src, titles, cache, use_model):
    """watching, gaming, social...: plain hints first, then the local model (constrained to the list), cached for good."""
    key = "life:" + src.lower()
    if key in cache:
        return cache[key]
    low = (src + " " + " ".join(titles)).lower()
    cat = next((c for c, hs in LIFE_HINTS.items() if any(h in low for h in hs)), None)
    if cat is None and use_model:
        try:
            cat = chat([{"role": "user", "content": f"Someone spent personal (non-work) time in: {src}\nExample window titles: "
                                                    f"{'; '.join(titles[:3])}\nWhich kind of time was it?"}],
                       {"type": "object", "required": ["kind"], "properties": {"kind": {"type": "string", "enum": list(LIFE)}}}, 20,
                       f"sorting {src}")["kind"]
        except Exception:
            cat = None
    cache[key] = cat or "other"
    return cache[key]


def life(day):
    """The day's off-the-clock time: by kind (watching, gaming, social...) and by source (Netflix, Valorant...).
    It reads the same labelled slots as the timesheet, with your edits: what you moved to a client stops counting."""
    slots, cache, use_model = labeled(day)
    edits = load("edits.json", {})
    mine = {t for s in merge(slots, day) if edits.get(s["id"], {}).get("client", s["client"]) == PERSONAL
            for t in slots if s["start"] <= t < s["end"]}
    secs, titles = defaultdict(float), defaultdict(list)
    work = [h.lower() for c in CONFIG["clients"] for h in [c["name"], *c["hints"]]]
    for t in mine:
        for (app, title), s in slots[t][0].items():
            if any(h in f"{app} {title}".lower() for h in work) or "lowkey — bills your hours" in title.lower():
                continue  # a client's window (or lowkey's own dashboard) inside a personal slot isn't leisure
            src = source(app, title)
            if not src:
                continue
            secs[src] += s
            if len(titles[src]) < 3 and title not in titles[src]:
                titles[src].append(title[:80])
    secs = {k: v for k, v in secs.items() if v >= 30}  # a few seconds in the Snipping Tool isn't time anyone spent
    with lock:
        before = len(cache)
        kinds = {src: category(src, titles[src], cache, use_model) for src in secs}
        if len(cache) != before:
            save("labels.json", cache)
    out = defaultdict(lambda: {"s": 0.0, "sources": []})
    for src, s in sorted(secs.items(), key=lambda kv: -kv[1]):
        out[kinds[src]]["s"] += s
        out[kinds[src]]["sources"].append({"name": src, "s": round(s)})
    cats = [{"name": k, "s": round(v["s"]), "sources": v["sources"][:5]} for k, v in out.items()]
    return {"total_s": round(sum(secs.values())), "cats": sorted(cats, key=lambda c: -c["s"])}


def life_week(day):
    """Monday to Sunday around the day: each day's total and kinds, for the week strip. Days still ahead stay empty."""
    d0 = datetime.fromisoformat(day)
    out = []
    for d in (d0 + timedelta(days=k - d0.weekday()) for k in range(7)):
        k = d.strftime("%Y-%m-%d")
        has = d.date() <= datetime.now().date() and (DATA / f"activity-{k}.jsonl").exists()
        x = life(k) if has else {"total_s": 0, "cats": []}
        out.append({"day": k, "s": x["total_s"], "has": has, "cats": [{"name": c["name"], "s": c["s"]} for c in x["cats"]]})
    return out


# ---------- live feed for the island ----------
WAKE = threading.Event()  # set by a dashboard edit: recount now instead of waiting out the minute


def refresh():
    # ponytail: relabels the still-growing current slot every minute; labels.json keeps those partial entries
    while True:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            sess = day_sessions(today)
            LIVE["slot_today"] = str(slot_len(today) // 60)  # what today really uses (a change may wait for tomorrow)
            LIVE["slot_locked"] = reviewed(today)
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
