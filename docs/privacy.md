# Privacy

lowkey watches what you do so you don't have to log it. That only works if you can trust it completely, so here is exactly what happens to your data.

## What is recorded

Every 5 seconds, while you're active:

| Recorded | Not recorded |
|---|---|
| foreground app name (`Code.exe`, `Google Chrome`) | screenshots or screen pixels |
| window title (up to 200 characters) | keystrokes, clipboard, mouse movement |
| a timestamp | audio, camera, files, URLs beyond what the title shows |

Nothing is recorded when you've been idle for 5 minutes, after you click **go dark**, for lowkey's own windows, or for anything matching `never_track` (password managers and private-browsing windows by default).

## Where it goes

Nowhere. It's appended to `data/activity-YYYY-MM-DD.jsonl` in the project folder, as plain text you can open, edit or delete.

The model runs in Ollama on your own machine. lowkey's only network traffic is to `http://127.0.0.1:11434`, which is localhost.

- The dashboard server binds to `127.0.0.1`, so other devices on your Wi-Fi can't reach it.
- The dashboard page loads no web fonts, scripts, analytics or images from the internet.
- There are no accounts, no telemetry and no update checks in lowkey.

Ollama's own desktop app checks for Ollama updates. If you want zero outbound traffic, turn that off in Ollama, or run `ollama serve` without the desktop app.

## Check it yourself

You don't have to take this page's word for it:

- **Read the code.** All network calls are `urllib.request` calls in `lowkey/labeler.py`, and all of them go to `OLLAMA` (`127.0.0.1:11434` unless you change it).
- **Pull the plug.** Turn Wi-Fi off. lowkey keeps tracking, labelling and invoicing exactly as before.
- **Watch the traffic.** Any network monitor (Resource Monitor on Windows, Little Snitch on macOS) shows lowkey talking only to localhost.

## In git

`data/`, `clients.json` (your clients and rates) and `settings.json` are in `.gitignore`. The repo only ships `clients.example.json` and a synthetic `demo/` week.
