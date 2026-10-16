"""Core logic checks. Run: python -m pytest tests  (or: python tests/test_lowkey.py)"""
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if "--demo" not in sys.argv:
    sys.argv.append("--demo")  # use the example clients (Acme Studio, Chai & Co, Nimbus Labs)

from lowkey import labeler, tracker  # noqa: E402
from lowkey.config import LIVE, SLOT_S  # noqa: E402


def test_mac_and_linux_parsers():
    outs = {"osascript": "Google Chrome\nPull request #42 - acme-website\n4242",
            "ioreg": '|   "HIDIdleTime" = 3500000000\n', "xdotool": "12345", "ps": "code", "xprintidle": "2000"}
    real = tracker.run
    tracker.run = lambda *c: outs[c[0]]
    try:
        assert tracker.foreground_mac() == ("Google Chrome", "Pull request #42 - acme-website", 3.5, 4242)
        outs["osascript"] = "Finder\n\n311"  # app with no window
        assert tracker.foreground_mac() == ("Finder", "", 3.5, 311)
        assert tracker.foreground_linux() == ("code", "12345", 2.0, 12345)
    finally:
        tracker.run = real


def test_what_gets_recorded():
    never = ["keepass", "incognito"]
    assert tracker.should_record("Code.exe", "auth.ts - acme", 3, 1, never)
    assert not tracker.should_record("Code.exe", "auth.ts", 400, 1, never)                 # idle > 5 min
    assert not tracker.should_record("KeePass.exe", "Vault", 1, 1, never)                  # never_track
    assert not tracker.should_record("chrome.exe", "New Incognito tab", 1, 1, never)       # never_track
    assert not tracker.should_record("python.exe", "tk", 1, os.getpid(), never)             # lowkey itself
    assert not tracker.should_record("explorer.exe", "", 1, 1, never)                       # no title
    LIVE["paused"] = True
    assert not tracker.should_record("Code.exe", "auth.ts", 1, 1, never)                   # "go dark"
    LIVE["paused"] = False


def test_slots_split_events_on_15_minute_boundaries():
    with tempfile.TemporaryDirectory() as d:
        real, labeler.DATA = labeler.DATA, Path(d)
        try:
            start = 1_700_000_000 - 1_700_000_000 % SLOT_S + SLOT_S - 60  # 60 s before a slot boundary
            (Path(d) / "activity-x.jsonl").write_text(
                json.dumps({"ts": start, "dur": 180, "app": "Code.exe", "title": "acme"}) + "\n", encoding="utf-8")
            slots = labeler.slots_for("x")
            assert sorted(sum(w.values()) for w in slots.values()) == [60, 120]
        finally:
            labeler.DATA = real


def test_rules_and_support():
    w = defaultdict(float, {("Code.exe", "auth.ts - acme-website"): 600, ("chrome.exe", "Instagram"): 300})
    assert labeler.rules(w)["client"] == "Acme Studio"
    assert labeler.support(w, "Acme Studio") == 0.67   # 600 of 900 s match Acme's hints
    assert labeler.support(w, "Personal") == 0.33
    assert labeler.rules(defaultdict(float, {("chrome.exe", "YouTube"): 60}))["client"] == "Personal"


def test_settings_only_take_known_choices():
    from lowkey import config
    real, before = config.SETTINGS, dict(LIVE["settings"])
    config.SETTINGS = Path(tempfile.mkdtemp()) / "settings.json"
    try:
        out = config.update_settings({"edge": "left", "rest": "sideways", "evil": "x"})
        assert out["edge"] == "left" and out["rest"] == before["rest"] and "evil" not in out
        assert json.loads(config.SETTINGS.read_text(encoding="utf-8"))["edge"] == "left"
    finally:
        config.SETTINGS = real
        LIVE["settings"].clear()
        LIVE["settings"].update(before)


def test_merge_joins_consecutive_same_client_slots():
    lab = lambda c: {"client": c, "task": f"work for {c}", "billable": c != "Personal", "by": "test"}
    w = lambda: defaultdict(float, {("a", "b"): 300})
    t = 1_700_000_100 - 1_700_000_100 % SLOT_S
    slots = {t: (w(), lab("Acme Studio")), t + SLOT_S: (w(), lab("Acme Studio")),
             t + 2 * SLOT_S: (w(), lab("Personal")), t + 4 * SLOT_S: (w(), lab("Personal"))}  # gap before last
    s = labeler.merge(slots, "day")
    assert [x["client"] for x in s] == ["Acme Studio", "Personal", "Personal"]
    assert s[0]["active_s"] == 600 and s[0]["end"] == t + 2 * SLOT_S


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
