"""How often the labels are right, on the bundled demo week. Re-run the README's numbers: python -m lowkey.eval

Ground truth is plain code: each window belongs to the first client whose hints are in its title (else Personal),
and a slot's client is whoever owns most of its seconds. A label is scored two ways: did it pick the slot's
majority client (with a 95% Wilson interval), and how many of the slot's active minutes went to the client that
really owned them. Calls labeler.label() directly, never the cache, and writes nothing.

--blind strips every client name and hint from the titles before labelling (the truth still comes from the full
titles). The demo titles name their clients, so the normal run mostly measures string matching; the blind run shows
what the model gets from everything else in a title. Keyword rules have nothing left to match there.

The normal run also scores the "check me" flag (under 60% of a session backed by its client's hints): of the
sessions it flags, how many are mislabelled, and how many mislabelled sessions it catches. On this week the truth
comes from the same hints, so a wrong session can never be over 50% backed: recall is 100% by construction here,
and precision is the number that says something.
"""
import math
import re
import sys
import time
from collections import defaultdict

BLIND = "--blind" in sys.argv
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


NAMES = re.compile("|".join(re.escape(w) for w in sorted({w for c in CONFIG["clients"] for w in [c["name"], *c["hints"]]},
                                                         key=len, reverse=True)), re.I)


def hide(windows):
    """The same windows with every client name and hint cut out of the titles."""
    out = defaultdict(float)
    for (app, title), s in windows.items():
        out[(app, re.sub(r"\s{2,}", " ", NAMES.sub("", title)).strip())] += s
    return out


def slots(minutes):
    """Every demo day cut into slots of this many minutes: a list of (day, {(app, title): seconds}), in time order."""
    real = labeler.slot_len
    labeler.slot_len = lambda day: minutes * 60
    try:
        days = sorted(p.stem[len("activity-"):] for p in labeler.DATA.glob("activity-*.jsonl"))
        return [(day, w) for day in days for _, w in sorted(labeler.slots_for(day).items())]
    finally:
        labeler.slot_len = real


def wilson(k, n, z=1.96):
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * (c - h), 100 * (c + h)


def check_me(slot_list, labels):
    """Merge consecutive same-client slots into sessions, as the dashboard does, and score the "check me" flag."""
    sessions = []
    for (day, w), client in zip(slot_list, labels):
        if sessions and sessions[-1][0] == day and sessions[-1][1] == client:
            for k, s in w.items():
                sessions[-1][2][k] += s
        else:
            sessions.append([day, client, defaultdict(float, w)])
    flagged = [labeler.support(w, c) < .6 for _, c, w in sessions]
    wrong = [c != truth(w)[0] for _, c, w in sessions]
    both = sum(f and x for f, x in zip(flagged, wrong))
    return len(sessions), sum(flagged), sum(wrong), both


def score(slot_list, pick):
    """pick(windows) -> label. Returns slots, slots right, % active minutes right, ms per label, rules fallbacks, labels."""
    hits = right_s = total_s = ms = fell = 0
    labels = []
    for _, w in slot_list:
        t0 = time.perf_counter()
        lab = pick(hide(w) if BLIND else w)
        ms += (time.perf_counter() - t0) * 1000
        client, fell = lab["client"], fell + (lab["by"] == "rules")
        major, by = truth(w)
        hits += client == major
        right_s += by.get(client, 0)
        total_s += sum(by.values())
        labels.append(client)
    n = len(slot_list)
    return n, hits, 100 * right_s / total_s, ms / n, fell, labels


def main():
    use_model = labeler.model_ok()
    pickers = [(MODEL, labeler.label)] if use_model else []
    pickers.append(("rules", labeler.rules))
    if BLIND:
        print("blind: client names and hints are cut out of every title before labelling\n")
    print(f"{'slot':>6}  {'labeller':<12}{'slots':>6}{'right slot':>12}{'95% interval':>17}{'right minutes':>15}{'ms/label':>10}")
    flags = []
    for minutes in (5, 10, 15):
        sl = slots(minutes)
        for name, pick in pickers:
            n, hits, min_pct, ms, fell, labels = score(sl, pick)
            lo, hi = wilson(hits, n)
            print(f"{minutes:>4} m  {name:<12}{n:>6}{100 * hits / n:>11.1f}%{lo:>9.1f}–{hi:.1f}%{min_pct:>14.1f}%{ms:>10.1f}", flush=True)
            if fell and name != "rules":
                print(f"        ({fell} of these {n} labels fell back to rules: the model call failed)")
            if not BLIND:
                flags.append((minutes, name, *check_me(sl, labels)))
    if flags:
        print('\n"check me" (under 60% backed by hints), per session:')
        print(f"{'slot':>6}  {'labeller':<12}{'sessions':>9}{'flagged':>9}{'wrong':>7}{'precision':>11}{'recall':>8}")
        for minutes, name, n, f, x, both in flags:
            prec = f"{100 * both / f:.0f}%" if f else "-"
            rec = f"{100 * both / x:.0f}%" if x else "-"
            print(f"{minutes:>4} m  {name:<12}{n:>9}{f:>9}{x:>7}{prec:>11}{rec:>8}")
    if not use_model:
        print(f"\nmodel rows skipped: {MODEL} isn't reachable through Ollama at {labeler.OLLAMA}. "
              f"Start Ollama and `ollama pull {MODEL}` to score it.")


if __name__ == "__main__":
    main()
