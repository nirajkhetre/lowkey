# lowkey.

**lowkey bills your hours. highkey private.**

A Dynamic Island for Windows that watches what you work on, lets a local Gemma 4 model turn it into invoice-ready timesheet lines, and never sends a byte of your screen activity off your laptop.

- 🏝️ **The island**: a notch tucked into the top edge of your screen, glowing in your current client's colour.
  - **Hover** and it springs down into a pill: client avatar with a daily-goal ring, a live "now playing" equaliser, the session timer and ₹ earned.
  - **Keep hovering (or click)** and it opens: what the AI thinks you're doing (typed in live), a 30-minute activity equaliser, today's stats, and **go dark** / **not work** / **open lowkey** buttons.
  - **Pop-outs** when you switch clients or cross a ₹1,000 milestone.
  - **Double-click** to pin it open. It never takes keyboard focus.
- 🧾 **The dashboard** (`http://127.0.0.1:7777`): your day as colour blocks, one card per work session with an AI-written invoice line, **bill it ✅ / nah 🙅** (or `Y` / `N`, `J`/`K` to move), a "why?" button that shows the exact windows behind every line.
- 💸 **Send the bill**: a receipt-style invoice per client → save as PDF or copy CSV.
- ✨ **Wrapped**: your week as a shareable card (main character client, longest flow state, side quests).

## How it works

```
your foreground window, every 5s   ──►  data/activity-YYYY-MM-DD.jsonl      (stdlib ctypes, no deps)
          │  (idle > 5 min, "go dark", or a never_track app → nothing is written)
          ▼
15-minute slots ──► Gemma 4 E2B via Ollama on 127.0.0.1 ──► {client, task, billable}   (JSON-schema constrained)
          ▼
consecutive slots for the same client ──► one session ──► Gemma merges the notes into one invoice line
          ▼
"backed by your windows" % = share of the session's time whose window titles match that client's hints
(computed by plain code, not by the model, so it can't talk itself into 100%)
```

If Ollama isn't running, lowkey falls back to keyword rules (and tells you in the UI).

## Run it

Requirements: Windows 10/11, Python 3.10+, `pip install PySide6-Essentials` (for the island), [Ollama](https://ollama.com).

```bash
ollama pull gemma4:e2b
python lowkey.py            # tracks + island + dashboard
python lowkey.py --demo     # bundled demo week, no tracking
python lowkey.py --no-island
```

Edit `clients.json` first: add your clients, hourly rate, colour and **hints** (repo names, domains, project names; anything that shows up in your window titles). `never_track` lists apps/windows that are never recorded (password managers, private browsing).

Want a different model? `set LOWKEY_MODEL=qwen3:4b` (any Ollama model that supports structured outputs).

## Privacy

- The dashboard and API bind to `127.0.0.1` only. The page loads no external fonts, scripts or images.
- The only network call lowkey makes is to Ollama on `127.0.0.1:11434`. (Ollama's desktop app checks for its own updates; turn that off in Ollama if you want zero outbound traffic.)
- Your activity lives in `data/` as plain JSONL. Delete it whenever you want.

## Numbers so far

| Test | Gemma 4 E2B | Keyword rules |
|---|---|---|
| Client per 15-min slot, **synthetic** demo week (155 slots) | 152/155 (98.1%) | 150/155 (96.8%) |
| Label latency on RTX 4050 6 GB, thinking off | ~0.3–0.6 s/slot | — |
| Same call with Gemma's thinking on | ~9.5 s | — |

The synthetic week is easy for keywords on purpose (titles contain the client names). Real-day results: _TODO_.

## License

MIT
