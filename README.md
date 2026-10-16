<p align="center">
  <img src="docs/images/hero.png" alt="lowkey: bills your hours, lowkey. highkey private." width="100%">
</p>

<p align="center">
  <b>A Dynamic Island for your laptop that writes your timesheet.</b><br>
  It watches what you work on, lets an open model running <i>on your own GPU</i> turn it into invoice-ready lines,<br>
  and never sends a byte of your screen activity anywhere.
</p>

<p align="center">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-B8FF3B?style=flat-square&labelColor=111">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-7AA2FF?style=flat-square&labelColor=111">
  <img alt="Windows and macOS" src="https://img.shields.io/badge/runs%20on-Windows%20%C2%B7%20macOS-FF7AD9?style=flat-square&labelColor=111">
  <img alt="Model: Gemma 4 via Ollama" src="https://img.shields.io/badge/model-Gemma%204%20via%20Ollama-FFD23F?style=flat-square&labelColor=111">
  <img alt="Network: localhost only" src="https://img.shields.io/badge/network-localhost%20only-111?style=flat-square">
</p>

<p align="center">
  <a href="#-quick-start">Quick start</a> ·
  <a href="#-what-you-get">What you get</a> ·
  <a href="#-how-it-works">How it works</a> ·
  <a href="#-privacy">Privacy</a> ·
  <a href="docs/configuration.md">Configuration</a> ·
  <a href="docs/troubleshooting.md">Troubleshooting</a>
</p>

<!-- demo video goes here -->

---

## Why

If you bill by the hour, your timesheet is a guess. You forget to start the timer, you jump between three clients before lunch, and at the end of the month you rebuild the week from browser history.

The tools that fix this want either **your money** (subscriptions that keep going up) or **your screen** (they watch everything you do and send it to their cloud). Your screen is your clients' code, your DMs and your bank tab.

**lowkey** does the watching *on your laptop*, with an open-weight model you run yourself. Nothing to sign up for, nothing to upload, nothing to cancel.

## ⚡ Quick start

**1. Install [Ollama](https://ollama.com) and pull the model** (≈4.6 GB, runs on a 6 GB laptop GPU):

```bash
ollama pull gemma4:e2b
```

**2. Get lowkey** (Python 3.10+):

```bash
git clone https://github.com/nirajkhetre/lowkey.git
cd lowkey
pip install -r requirements.txt   # only needed for the island; the rest is standard library
```

**3. Try the demo week first** (tracks nothing):

```bash
python -m lowkey --demo
```

Open **http://127.0.0.1:7777**.

**4. Add your clients and start tracking:**

```bash
python -m lowkey
```

The first run creates `clients.json` from [`clients.example.json`](clients.example.json). Put your real clients in it, then restart. Each client gets a name, hourly rate, colour and a few **hints**: repo names, domains, project names, anything that shows up in your window titles. See [Configuration](docs/configuration.md).

> **macOS:** allow your terminal under *System Settings → Privacy & Security → Accessibility* so lowkey can read window titles.

## ✨ What you get

### 🏝️ The island

A notch tucked into the edge of your screen, glowing in your current client's colour.

<p align="center"><img src="docs/images/island-states.png" alt="The island tucked away, as a pill on hover, and fully open" width="100%"></p>

- **Hover** and it springs out into a pill: your client's creature, a tiny live squiggle, the session timer and money earned today.
- **Keep hovering, or click,** and it opens:
  - what the model thinks you're doing, typed in live
  - a **flow wave** of your last hour: it ripples while you work, goes still and moonlit when you're off the record, and on hover tells you how many of the last 60 minutes were active and how long you've been in flow
  - today's money in the corner, today's time as a little activity ring, and how many sessions wait for review
  - three round buttons and nothing else: **go dark** (pause tracking: the island turns into a night sky, off the record), **open lowkey** (the one filled, primary action) and **•••**
- **Built like a Live Activity:** the buttons have no labels, because hovering any of them explains it in the line under the client name. The rarer actions wait behind **•••**: not work (with 5 s to undo), pin and settings.
- **Pin** (or double-click) keeps it out. It never takes keyboard focus, so it can't interrupt your typing.
- **Settings** open right inside the island. Hover an option and a little screen pops out beside it, acting out exactly where the island will go; click and it moves there for real, then waits open for you.

<p align="center"><img src="docs/images/island-settings.png" alt="Island settings inside the island, with a hover preview acting out the move to the left edge" width="100%"></p>

<p align="center"><img src="docs/images/island-details.png" alt="One primary action, the rarer actions behind more, and undo instead of a confirm dialog" width="100%"></p>

<p align="center"><img src="docs/images/island-moments.png" alt="Pop-out when switching clients, and the gone-dark state" width="80%"></p>

#### Meet your creatures

Every client gets its own little blob: a shape picked from the client's name, in the client's colour. When you switch clients, it **morphs** into the next one.
- **Its eyes follow your cursor,** with a bit of perspective, so it looks like it turns its head.
- **It blinks on its own,** and sometimes double-blinks.
- **It breathes,** squash-wobbles when its mood changes, and falls asleep when you walk away.
- **Its mood follows what you're actually doing.**
- **Click it** and it tells you something useful about your day: time on the current client, money secured, progress to your daily goal, sessions waiting for review.

<p align="center"><img src="docs/images/mascot-moods.png" alt="The creature's nine moods" width="80%"></p>

### 🎛️ Every control, explained

**Hover anything on the island and it tells you what it does,** in the line under the client name.

| Control | Where | What it does |
|---|---|---|
| **the lip** | island, resting | Hover to open the pill; keep hovering (or click) to open the full card. Double-click pins it open; double-click again tucks it away. |
| **the creature** | island | Your current client, as a blob in their colour. Click it for a one-liner about your day; click again for the next. |
| 🌙 **go dark** | island | Pauses tracking. Nothing is saved until you resume, so the AI never sees those minutes and they can't reach an invoice. The island turns into a night sky. Not remembered after a restart. |
| ☀️ **resume** | island, while dark | Back on the clock from this moment. |
| ↗ **open lowkey** | island, open card | The one filled button: opens the dashboard. |
| ••• **more** | island, open card | Slides the buttons over to the rarer actions below. Turns into ✕ to slide back. |
| 🎮 **not work** | island, behind ••• | Marks the current session as a side quest (personal), so it stays off the invoice. Undo stays on offer for 5 s; the shrinking underline is the countdown. Dimmed when there's nothing to move (already personal, or gone dark); hover it to see why. |
| 📌 **pin** | island, behind ••• | Keeps the pill out instead of tucking it away. Click again to unpin. |
| ⚙️ **settings** | island, behind ••• | Which edge it lives on, below or over the taskbar, tucked or a pill at rest. Hover an option for an animated preview of exactly where it goes; click to apply. The ‹ goes back. |
| ◔ **today** | island, open card | Billable time today. The ring fills up towards your daily goal (`daily_goal_h`). Click to open the dashboard. |
| ₹ **earned today** | island, open card | Earned today at your client rates; it glows when it ticks up. Click to make the invoice. |
| ● **to review** | island, open card | Sessions you haven't approved yet. Its dot pulses while something waits; click to review them. |
| **bill it ✅ / nah 🙅** | dashboard card | Approve a session for the invoice, or leave it off. |
| **client dropdown / ✏️** | dashboard card | Move a session to another client, or edit its invoice line. |
| 🧾 **why?** | dashboard card | Shows the exact windows behind the line: your receipts. |
| 💸 **send the bill** | dashboard header | A receipt-style invoice per client from approved sessions → PDF or CSV. |
| ✨ **wrapped** | dashboard header | Your week as a shareable card. |
| ⚙️ **settings** | dashboard header | Island edge, taskbar behaviour, resting style, each with live previews. |
| **← / →, ◐** | dashboard header | Change day, toggle light/dark theme. |

**Keyboard in the dashboard:** `J`/`K` move · `Y` bill it · `N` nah · `E` edit · `←`/`→` day · `B` bill · `W` wrapped · `S` settings · `Esc` close.

### 🧾 The dashboard

Your day as colour blocks, one card per work session, each with an invoice line written by the model.

<p align="center"><img src="docs/images/dashboard.png" alt="lowkey dashboard" width="100%"></p>

- Review like a feed: **bill it ✅ / nah 🙅**, or move the session to another client.
- Keyboard: `J`/`K` move · `Y` bill · `N` nah · `E` edit · `←`/`→` change day · `B` bill · `W` wrapped · `S` settings.
- **🧾 why?** shows the exact windows behind every line. If a client ever asks what they paid for, you have receipts.
- **"backed by your windows" %** is computed by plain code, not by the model: the share of the session's time whose window titles match that client. Low score → *"🤔 check me"*.

### 💸 Send the bill · ✨ Wrapped

<table>
<tr>
<td width="50%"><img src="docs/images/invoice.png" alt="Receipt-style invoice"></td>
<td width="50%"><img src="docs/images/wrapped.png" alt="Your week, wrapped"></td>
</tr>
<tr>
<td>A receipt-style invoice per client from the sessions you approved. Save as PDF or copy as CSV.</td>
<td>Your week as a shareable card: main character client, longest flow state, side quests.</td>
</tr>
</table>

### ⚙️ Island settings

Pick the **edge** (top, bottom, left, right), what happens when the island **shares an edge with your taskbar** (sit over it like a real notch, or hang below it), and whether it rests as a **tucked-away lip** or an **always-visible pill**. Every option is a card with a mini preview of *your* screen layout. Hover a card and its island springs open.

<p align="center"><img src="docs/images/settings.png" alt="Island settings with live screen previews" width="85%"></p>

## 🧠 How it works

<p align="center"><img src="docs/images/architecture.svg" alt="lowkey architecture" width="100%"></p>

1. **Tracker:** every 5 seconds, the foreground app and window title are appended to `data/activity-YYYY-MM-DD.jsonl`. Nothing is written when you're idle, when you've hit *go dark*, or for apps in `never_track`.
2. **Labeler:** activity is cut into 15-minute slots. Each slot goes to **Gemma 4 E2B** through Ollama, which returns `{client, task, billable}`.
   - The output is constrained by a JSON schema, and `client` is an enum of *your* clients, so the model can't invent one.
   - Consecutive slots for the same client merge into a session, and a second pass writes one clean invoice line.
3. **Code check:** plain code scores how well window titles back each session. You review, and only approved sessions reach an invoice.

If Ollama isn't running, lowkey falls back to keyword rules and says so in the UI. Deep dive: [docs/how-it-works.md](docs/how-it-works.md).

## 🔒 Privacy

- **Local only.** The dashboard and API bind to `127.0.0.1`. The page loads no external fonts, scripts or images.
- **One network call.** lowkey talks only to Ollama on `127.0.0.1:11434`. No accounts, no cloud, no telemetry.
- **Plain files.** Your activity is plain JSONL in `data/`. Open it, edit it, delete it.
- **You choose what's never recorded.** `never_track` skips apps entirely (password managers, private browsing by default), and **go dark** pauses everything with one click.
- **Your config stays out of git.** `clients.json`, `settings.json` and `data/` are gitignored.

More in [docs/privacy.md](docs/privacy.md).

## 💻 Platform support

| | Windows 10/11 | macOS | Linux |
|---|:---:|:---:|:---:|
| Tracker | ✅ Win32 via ctypes | ✅ `osascript` + `ioreg` | ⚠️ X11 only (`xdotool`, `xprintidle`) |
| Island | ✅ | ✅ (sits below the menu bar) | ✅ |
| Dashboard | ✅ | ✅ | ✅ |

Daily use is on Windows 11. The macOS and Linux trackers are covered by tests with recorded command output, but haven't run on real hardware yet. Reports are welcome.

## 📊 Numbers so far

| Test | Gemma 4 E2B (local) | Keyword rules |
|---|:---:|:---:|
| Right client per 15-min slot, **synthetic** demo week (155 slots) | 152 / 155 (98.1%) | 150 / 155 (96.8%) |
| Label latency, RTX 4050 Laptop (6 GB), thinking off | ~0.3–0.6 s | instant |
| Same call with Gemma 4's thinking on | ~9.5 s | — |

The synthetic week is deliberately easy for keywords, since its window titles contain client names. The model earns its place on real days, where titles don't name the client, and in writing invoice lines, which rules can't do.

## ❓ FAQ

<details><summary><b>Does it record my screen?</b></summary>

No screenshots, no keystrokes, no audio. Only the foreground app name and window title, every 5 seconds, into a text file on your disk.
</details>

<details><summary><b>Do I need a GPU?</b></summary>

No. Without one, Gemma 4 E2B runs on CPU via Ollama, just slower. Labels are cached, so each 15-minute slot is labelled once. Any Ollama model with structured outputs works: `LOWKEY_MODEL=qwen3:4b python -m lowkey`.
</details>

<details><summary><b>What if the model gets a session wrong?</b></summary>

Nothing is billed until you approve it. Change the client from the card's dropdown, edit the line, or press `N`. The "backed by your windows" score points you to the sessions worth checking.
</details>

<details><summary><b>My taskbar is at the top. Will the island cover it?</b></summary>

Your choice. In settings, "sit on the screen edge" floats the island over the taskbar like a notch; "hang below it" attaches it underneath. Bottom-taskbar users aren't affected either way.
</details>

## 🛠️ Development

```bash
python tests/test_lowkey.py       # or: python -m pytest tests
python -m lowkey --demo           # UI work without tracking
```

```
lowkey/
├── __main__.py      entry point: python -m lowkey
├── config.py        paths, clients, settings, shared live state
├── tracker.py       foreground window on Windows / macOS / Linux
├── labeler.py       slots → Gemma → sessions → invoice lines
├── server.py        local dashboard + JSON API
├── island.py        the notch (PySide6, hand-painted)
├── mascot.py        the island's creature: shapes, eyes, moods, one-liners
├── jelly.py         jelly icons: moon, sun, gamepad, live clock, flipping coin, self-drawing tick
└── web/index.html   the dashboard (no build step, no CDN)
demo/                a synthetic week for --demo
docs/                guides and images
tests/               core logic checks
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

- Fonts, bundled so the app makes no web-font requests, all under the SIL Open Font License (licences in [`lowkey/web/fonts/`](lowkey/web/fonts)):
  - [Bricolage Grotesque](https://github.com/ateliertriay/bricolage) for the UI
  - [Instrument Serif](https://github.com/Instrument/instrument-serif) for the italic accents
  - [Geist Mono](https://github.com/vercel/geist-font) for numbers
- Icons: lowkey's own "jelly" icons ([`lowkey/jelly.py`](lowkey/jelly.py)), drawn with the same light as the creatures.
- Creature style inspired by the procedural avatars of [Bible Strong Avatar Lab](https://github.com/smontlouis/bible-strong-avatar-lab). lowkey's creatures are drawn by its own QPainter renderer; no code or art is taken from that project.
- Local inference: [Ollama](https://ollama.com) running Google's open-weight [Gemma 4](https://ai.google.dev/gemma).

## License

[MIT](LICENSE). Use it, fork it, ship it.
