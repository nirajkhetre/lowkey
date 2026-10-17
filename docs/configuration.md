# Configuration

lowkey has two config files. Both live in the project folder and are **gitignored**, so your clients and preferences never end up in a commit.

| File | Created | Edited by |
|---|---|---|
| `clients.json` | copied from `clients.example.json` on first run | you, in a text editor |
| `settings.json` | the first time you change an island setting | the dashboard (⚙️ or `S`) |

Restart lowkey after editing `clients.json`. Settings apply live.

## `clients.json`

The easy way: the 👥 **your clients** sheet in the dashboard (or press `C`). It edits this file for you, saves as you go, and carries a client's history over when you rename it. Editing the file by hand still works; restart lowkey afterwards.

```json
{
  "me": { "name": "Riya Sharma", "email": "riya@example.com", "currency": "₹", "daily_goal_h": 6 },
  "clients": [
    { "name": "Acme Studio", "rate": 1200, "color": "#B8FF3B", "hints": ["acme", "acme-website", "acme.studio"] },
    { "name": "Chai & Co",   "rate": 900,  "color": "#FF7AD9", "hints": ["chaico", "chai & co", "shopify"] }
  ],
  "never_track": ["KeePass", "Bitwarden", "1Password", "InPrivate", "Incognito"]
}
```

### `me`

| Field | What it does |
|---|---|
| `name`, `email` | Printed at the top of every invoice. |
| `currency` | Symbol used everywhere money appears (`₹`, `$`, `€`, …). |
| `daily_goal_h` | Hours that fill the ring around the island's avatar. Default `6`. |

### `clients`

| Field | What it does |
|---|---|
| `name` | Shown on cards, invoices and the island. The model can only pick from these names, or `Personal`. |
| `rate` | Hourly rate, used for money on cards, the island, invoices and Wrapped. |
| `color` | The client's colour: island glow, timeline blocks, card headers. |
| `hints` | Words that appear in your window titles when you work for this client: repo and folder names, domains, Figma or Notion page names, Slack channels, meeting titles. Matching is case-insensitive substring matching. |

**Good hints make everything better.** The model gets them as evidence, the keyword fallback uses them, and the "backed by your windows" % is computed from them. Three to five specific hints per client is plenty. Avoid generic words like `design` that appear in every client's work.

### `never_track`

Any app or window whose name or title contains one of these strings (case-insensitive) is **never written to disk**. Add your bank, your messaging apps, anything you'd rather not even have locally.

### `focus` and `distractions` (optional)

```json
"focus": { "nudge_after_min": 8, "ask_after_min": 10 },
"distractions": ["Hacker News", "Discord"]
```

| Key | What it does |
|---|---|
| `focus.nudge_after_min` | Minutes on a distraction before the island nudges you back to your intention. Default `8`. At most three nudges an hour. |
| `focus.ask_after_min` | Minutes on another client's work before the island asks how far you got. Default `10`. |
| `distractions` | Extra window-title words that count as drifting, on top of the built-in list (YouTube, Netflix, Instagram, Reddit, X, Facebook, WhatsApp, TikTok, Prime Video, Hotstar, Twitch, Steam). |

## Island settings (`settings.json`)

Change these in the dashboard. Every option has a live preview.

| Key | Values | Default |
|---|---|---|
| `edge` | `top` · `bottom` · `left` · `right` | `top` |
| `taskbar` | `over`: sits on the physical screen edge, raised above a taskbar on the same edge · `below`: hangs from the usable screen area, so the taskbar pushes it inward | `over` on Windows, `below` on macOS (the menu bar can't be covered) |
| `rest` | `lip`: tucked away until you hover · `pill`: always shows client, timer and money | `lip` |

## Environment variables

| Variable | Default | Use it to… |
|---|---|---|
| `LOWKEY_MODEL` | `gemma4:e2b` | try another Ollama model with structured outputs, e.g. `qwen3:4b` |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | point at Ollama on a different port |
| `LOWKEY_PORT` | `7777` | run the dashboard on another port, e.g. a demo next to your real instance |

```bash
LOWKEY_MODEL=qwen3:4b python -m lowkey                 # macOS / Linux
$env:LOWKEY_MODEL="qwen3:4b"; python -m lowkey         # Windows PowerShell
```

## Command-line flags

| Command | What runs |
|---|---|
| `python -m lowkey` | tracker + island + dashboard |
| `python -m lowkey --demo` | dashboard on the bundled demo week; nothing is tracked |
| `python -m lowkey --no-island` | tracker + dashboard, no island |

## Where your data lives

```
data/
├── activity-2026-10-16.jsonl   one line per 5-second sample: {"ts", "dur", "app", "title"}
├── labels.json                 cached model labels, so each slot is labelled once
├── edits.json                  your approvals, rejections and edits
├── intents.json                your intentions: what you said, time on each, how far you got
└── manual.json                 receipts you added yourself ("1h call with acme at 3pm")
```

Delete `labels.json` to relabel everything, for example after switching models. Delete the whole folder to start fresh.
