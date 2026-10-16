# Contributing

Thanks for wanting to make lowkey better. It's deliberately small: Python standard library for the core, PySide6 for the island, one HTML file for the dashboard. Please help keep it that way.

## Setup

```bash
git clone https://github.com/nirajkhetre/lowkey.git
cd lowkey
pip install -r requirements.txt
ollama pull gemma4:e2b
python -m lowkey --demo      # work on the UI without tracking anything
python tests/test_lowkey.py  # core logic checks
```

`LOWKEY_PORT=7788 python -m lowkey --demo` runs a demo next to your real instance.

## Ground rules

- **Privacy is the product.** No network calls except to the local model. No telemetry, no CDNs, no web fonts. Nothing that sends activity anywhere.
- **No new dependencies for the core.** If the standard library can do it in a few lines, use it.
- **The model writes, code decides.** Money, time and trust scores are computed by code. The model only labels and writes text, constrained by a JSON schema.
- **Keep the look.** The dashboard is neo-brutalist on purpose: thick outlines, hard shadows, loud colours, playful copy.

## Good first contributions

- Real-hardware reports for the macOS and Linux trackers.
- A Wayland tracker via a desktop-specific API.
- Multi-monitor support for the island (it uses the primary screen today).
- More invoice templates (GST invoice, US 1099-friendly), still generated locally.
- An evaluation script for hand-labelled real days: right client per slot, invoice lines kept without edits.

## Pull requests

Keep them focused. Include a screenshot for UI changes, and make sure `python tests/test_lowkey.py` passes.
