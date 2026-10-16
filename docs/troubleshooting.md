# Troubleshooting

**The dashboard says "keyword mode" / the pill says `… offline`**
Ollama isn't running, or the model isn't pulled. Run `ollama list` and check that `gemma4:e2b` (or your `LOWKEY_MODEL`) is listed. If it isn't, run `ollama pull gemma4:e2b`. If Ollama isn't running at all, start the Ollama app or run `ollama serve`. lowkey re-checks every 30 seconds.

**Everything is labelled "Personal"**
Your `clients.json` probably still has the example clients, or your hints don't appear in your window titles. Open a few windows you use for a client, look at their titles, and add distinctive words from them as hints. See [configuration](configuration.md).

**Labelling is slow**
- Check that Ollama is using your GPU: `ollama ps` shows `100% GPU` when it is.
- On CPU-only machines, try a smaller model, e.g. `LOWKEY_MODEL=qwen3:1.7b`.
- If you swapped in a model that "thinks", lowkey already sends `think: false`, but make sure your Ollama version supports it.

**No island appears**
- Install Qt: `pip install -r requirements.txt` (PySide6-Essentials). Without it lowkey prints `island off` and runs dashboard-only.
- The island hides as a thin lip by default. Hover the middle of your chosen screen edge, or set *when you're not looking → always show the pill* in settings.

**My taskbar is at the top and covers the island**
Open settings (`S`) and choose *hang below it*. Or keep *sit on the screen edge*, which re-raises the island above the taskbar every 0.4 s.

**macOS: only app names, no window titles**
Give your terminal (or Python) access under *System Settings → Privacy & Security → Accessibility*, and allow it to control *System Events* when asked. Restart lowkey afterwards.

**Linux: nothing is tracked**
The tracker needs X11 plus `xdotool` and `xprintidle` (`sudo apt install xdotool xprintidle`). Wayland sessions deliberately hide other apps' windows, so they aren't supported.

**`OSError: [Errno 10048]` / address already in use**
Another lowkey is already running on port 7777. Close it, or run this one on another port: `LOWKEY_PORT=7788 python -m lowkey --demo`.

**I switched models and want fresh labels**
Delete `data/labels.json`. Your approvals live in `data/edits.json` and are kept.
