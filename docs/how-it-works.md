# How it works

<p align="center"><img src="images/architecture.svg" alt="lowkey architecture" width="100%"></p>

lowkey is three small loops that share one in-memory dict (`LIVE` in `config.py`). The tracker and the labeler write to it, and the island and dashboard read it.

## 1. Tracker: `lowkey/tracker.py`

Every 5 seconds it asks the OS for the foreground app, its window title, how long you've been idle, and the window's process id.

| OS | How |
|---|---|
| Windows | `GetForegroundWindow`, `GetWindowTextW`, `QueryFullProcessImageNameW` and `GetLastInputInfo` via `ctypes` |
| macOS | one `osascript` call to System Events (app, front window, pid), plus `ioreg` for `HIDIdleTime` |
| Linux (X11) | `xdotool` for the window and pid, `ps` for the app name, `xprintidle` for idle time |

`should_record()` drops a sample when:
- the window has no title
- the window belongs to lowkey itself
- you've been idle for more than 5 minutes
- you hit **go dark**
- the app or title matches `never_track`

Everything else is appended as one JSON line to `data/activity-YYYY-MM-DD.jsonl`. The tracker also counts active seconds per minute; those counts feed the island's flow wave.

## 2. Labeler: `lowkey/labeler.py`

**Slots.** `slots_for(day)` cuts the day into slots of `slot_len(day)` seconds (the **reads every** setting: 5, 10 or 15 minutes, 5 by default), splitting any sample that straddles a boundary. A day keeps the length it was first labelled with (`data/slots.json`), because your reviews point at sessions by their start time: a new length applies today only if nothing today is reviewed yet, otherwise from tomorrow. Days from before the setting existed are 15-minute days. Each slot becomes a map of `(app, title) → seconds`.

**Labels.** `describe()` turns a slot into the top 8 windows by time. `label()` sends that, plus your client list and hints, to the local model:

```python
schema = {"type": "object", "required": ["client", "task", "billable", "confidence"], "properties": {
    "client": {"type": "string", "enum": your_clients + ["Personal"]},   # can't invent a client
    "task": {"type": "string"}, "billable": {"type": "boolean"}, "confidence": {"type": "number"}}}
```

Calls go to Ollama's `/api/chat` with `"format": schema`, `"temperature": 0` and `"think": false`. Gemma 4 reasons out loud by default, which took about 9.5 s per label on a 6 GB laptop GPU; with thinking off it's about 0.3 s.

Labels are cached in `data/labels.json`, keyed by a hash of the model name and the slot description, so each slot is labelled once. If Ollama isn't reachable, `rules()` labels by keyword hints, and those entries are relabelled by the model once it's back.

**Sessions.** `merge()` joins consecutive slots that have the same client into one session. When a session spans several slots, `summarize()` asks the model to merge the slot notes into **one** invoice line (past tense, ≤ 90 characters, concrete details), also cached.

**The honesty score.** The model's self-reported confidence was useless: it said 1.0 for everything. So each card instead shows `support()`, computed by plain code: the share of the session's seconds whose window titles match the chosen client's hints, or no client's hints for `Personal`. Under 60% the card says *"🤔 check me"*.

**Live feed.** `refresh()` recomputes today every minute and pushes the current client, task, session start, billable time, money and review count into `LIVE` for the island.

## 3. Dashboard: `lowkey/server.py` + `lowkey/web/index.html`

A standard-library `ThreadingHTTPServer` bound to `127.0.0.1` serves one HTML file with no build step and no CDN, plus a small JSON API:

| Endpoint | Purpose |
|---|---|
| `GET /api/state` | config, model status, days with data |
| `GET /api/range?from=YYYY-MM-DD&to=YYYY-MM-DD` | sessions per day (labels on demand) |
| `POST /api/edit` | `{id, client?, task?, billable?, status?}`: your review decisions |
| `GET /api/settings` · `POST /api/settings` | island settings + detected taskbar side |

Edits are stored separately in `data/edits.json` and applied on top of the model's labels, so relabelling never overwrites your decisions.

## 4. Island: `lowkey/island.py`

PySide6 with hand-painted `QPainter`. tkinter was tried first, but it can't anti-alias or do per-pixel transparency on Windows, so it looked pixelated.

- **Window:** frameless, always on top, `Qt.Tool` (no taskbar button), translucent background, and `WindowDoesNotAcceptFocus` + `WA_ShowWithoutActivating`, so it never steals your keyboard.
- **Motion:** a small spring simulation (`Spring`, stiffness 260, damping 24) drives width, height and per-state opacity. The slight overshoot is what makes it feel like the real Dynamic Island. Rows in the open card fade and slide in with a stagger.
- **Shape:** the notch, including its concave "ears" where it meets the screen edge, is built as if it hung from the top edge, then mirrored or rotated onto the chosen edge with a `QTransform`.
- **Placement:** re-read every frame. By default it hangs from the *work area* (`availableGeometry()`), so a taskbar or the macOS menu bar on the same edge pushes it inward. With `taskbar: over` it uses the full screen instead, and on Windows calls `SetWindowPos(HWND_TOPMOST)` every 0.4 s: the taskbar is also topmost, and whichever window was raised last wins.
- **Creature (`mascot.py`):** drawn every frame.
  - **Body:** a superellipse body (exponent, aspect and "egg" taper picked from a hash of the client's name) with a radial-gradient light, a specular highlight and a contact shadow.
  - **Morphing:** shape and colour ease towards the current client, so switching clients morphs the creature.
  - **Eyes:** two pill eyes shift towards the cursor and crowd together on the side it turns to, which fakes a head turn. They blink at random intervals, with an occasional double blink.
  - **Mood, by priority:**
    1. gone dark → squeezed `> <`
    2. away → closed with z's
    3. a recent event → wide eyes on a client switch, star eyes on a ₹1,000 milestone, happy `^ ^` with sparkles on the daily goal
    4. no client yet → one big eye, one small
    5. personal → `^ ^`
    6. 90+ minutes on one session → narrowed, slanted
    7. otherwise → plain pill eyes
  - **Click it** to cycle through one-liners built from your live stats.
- **States:** `lip → pill` after 0.12 s of hover, `→ open` after 0.6 s or a click, back to rest 0.35 s after the cursor leaves. Toasts fire on client switches and every ₹1,000 milestone.
