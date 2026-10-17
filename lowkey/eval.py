"""How often the labels are right, on the bundled demo week. Re-run the README's numbers: python -m lowkey.eval

Ground truth is plain code: each window belongs to the first client whose hints are in its title (else Personal),
and a slot's client is whoever owns most of its seconds. A label is scored two ways: did it pick the slot's
majority client, and how many of the slot's active minutes went to the client that really owned them.
Calls labeler.label() directly, never the cache, and writes nothing.
"""
import sys
import time
from collections import defaultdict

if "--demo" not in sys.argv:
    sys.argv.append("--demo")  # the demo week and its example clients

from . import labeler  # noqa: E402
from .config import CONFIG, MODEL, PERSONAL  # noqa: E402


def owner(app, title):
    text = f"{app} {title}".lower()
    return next((c["name"] for c in CONFIG["clients"] if any(h.lower() in text for h in c["hints"])), PERSONAL)


def truth(windows):
    """The slot's majority client by hints, and each client's seconds in it."""
    by = defaultdict(float)
    for (app, title), s in windows.items():
        by[owner(app, title)] += s
    return max(by, key=by.get), by


def slots(minutes):
    """Every demo day cut into slots of this many minutes: a list of {(app, title): seconds}."""
    real = labeler.slot_len
    labeler.slot_len = lambda day: minutes * 60
    try:
        days = sorted(p.stem[len("activity-"):] for p in labeler.DATA.glob("activity-*.jsonl"))
        return [w for day in days for _, w in sorted(labeler.slots_for(day).items())]
    finally:
        labeler.slot_len = real


def score(windows_list, pick):
    """pick(windows) -> label. Returns slots, % slots right, % active minutes right, ms per label, rules fallbacks."""
    hits = right_s = total_s = ms = fell = 0
    for w in windows_list:
        t0 = time.perf_counter()
        lab = pick(w)
        ms += (time.perf_counter() - t0) * 1000
        client, fell = lab["client"], fell + (lab["by"] == "rules")
        major, by = truth(w)
        hits += client == major
        right_s += by.get(client, 0)
        total_s += sum(by.values())
    n = len(windows_list)
    return n, 100 * hits / n, 100 * right_s / total_s, ms / n, fell


def main():
    use_model = labeler.model_ok()
    pickers = [(MODEL, labeler.label)] if use_model else []
    pickers.append(("rules", labeler.rules))
    print(f"{'slot':>6}  {'labeller':<12}{'slots':>6}{'right slot':>12}{'right minutes':>15}{'ms/label':>10}")
    for minutes in (5, 10, 15):
        ws = slots(minutes)
        for name, pick in pickers:
            n, slot_pct, min_pct, ms, fell = score(ws, pick)
            print(f"{minutes:>4} m  {name:<12}{n:>6}{slot_pct:>11.1f}%{min_pct:>14.1f}%{ms:>10.1f}", flush=True)
            if fell and name != "rules":
                print(f"        ({fell} of these {n} labels fell back to rules: the model call failed)")
    if not use_model:
        print(f"\nmodel rows skipped: {MODEL} isn't reachable through Ollama at {labeler.OLLAMA}. "
              f"Start Ollama and `ollama pull {MODEL}` to score it.")


if __name__ == "__main__":
    main()
