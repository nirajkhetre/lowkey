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


def test_a_corrupt_file_is_kept_aside_not_lost():
    from lowkey import config
    d = Path(tempfile.mkdtemp())
    (d / "edits.json").write_text('{"half": ', encoding="utf-8")  # what a crash mid-write used to leave
    assert config.read_json(d / "edits.json", {}) == {}
    kept = list(d.glob("edits.json.corrupt-*"))
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8") == '{"half": '
    config.write_atomic(d / "edits.json", '{"ok": 1}')
    assert config.read_json(d / "edits.json", {}) == {"ok": 1} and not list(d.glob(".*.tmp"))


def test_api_answers_only_this_machines_pages():
    import http.client
    import threading
    from lowkey import server
    srv = server.make_server(0)  # any free port
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def call(method, path, body=None, **headers):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request(method, path, body, headers)
        return c.getresponse().status
    js = {"Content-Type": "application/json"}
    try:
        assert call("GET", "/api/settings") == 200
        assert call("GET", "/api/settings", Host="evil.example") == 403                      # DNS rebinding
        assert call("POST", "/api/catch", "{}", **{"Content-Type": "text/plain"}) == 415     # cross-site "simple" POST
        assert call("POST", "/api/catch", "{}", Origin="https://evil.example", **js) == 403  # another site driving it
        assert call("POST", "/api/catch", "{oops", **js) == 400                              # bad JSON
        assert call("POST", "/api/edit", '{"status": "billed"}', **js) == 400                # no session id
        assert call("GET", "/api/range?from=2020-01-01&to=2026-01-01") == 400                # absurd range
        assert call("POST", "/api/catch", '{"text": "hi"}', Origin=f"http://127.0.0.1:{port}", **js) == 200
    finally:
        srv.shutdown()
        LIVE.pop("catches", None)


def test_intentions_parse_order_and_watch():
    from datetime import datetime
    from lowkey import config, focus
    real, w = config.DATA, dict(focus.W)
    config.DATA, focus._xs = Path(tempfile.mkdtemp()), []
    try:
        now = datetime(2026, 10, 16, 14, 0).timestamp()  # a Friday, 2 pm
        p = focus.parse("acme login fix by 5, about an hour", now)
        assert (p["text"], p["client"], p["est_min"], datetime.fromtimestamp(p["due"]).hour) == ("acme login fix", "Acme Studio", 60, 17)
        assert focus.parse("sat down to fix the sun icon", now)["due"] is None                 # "sat" is not Saturday here
        assert datetime.fromtimestamp(focus.parse("ship it by 5", now + 5 * 3600)["due"]).day == 17  # 5 pm passed: tomorrow

        a = focus.add("acme login fix by 5, about an hour", now=now)                           # nothing on yet: it starts
        b = focus.add("nimbus invoice by friday", now=now + 1)
        c = focus.add("chai & co banner", now=now + 2)
        assert a["state"] == "now" and [x["id"] for x in focus.order(focus._xs, now)] == [b["id"], c["id"]]
        assert focus.reason(b, now) == "due in 4h" and focus.reason(c, now) == "₹900/h"

        t = now
        for _ in range(12):                                                                     # a minute on it
            t += 5
            focus.watch("Code.exe", "auth.ts - acme-website", True, t)
        assert a["spent_s"] == 60 and focus.W["prompt"] is None
        for _ in range(focus.NUDGE_S // 5):                                                     # then YouTube
            t += 5
            focus.watch("chrome.exe", "lofi beats - YouTube", True, t)
        assert focus.W["prompt"]["kind"] == "nudge" and focus.W["prompt"]["what"] == "YouTube" and a["spent_s"] == 60
        focus.respond("back", now=t)
        assert focus.W["prompt"] is None and focus.W["snooze"] > t

        for _ in range(focus.SWITCH_S // 5 + 1):                                               # clearly on Nimbus now
            t += 5
            focus.watch("Code.exe", "handlers.py - nimbus-api", True, t + focus.BACK_S)
        assert focus.W["prompt"]["kind"] == "ask"
        focus.respond("progress", 50, now=t)                                                    # "halfway"
        assert a["state"] == "next" and a["progress"] == 50
        assert focus.W["prompt"]["kind"] == "next" and focus.W["prompt"]["id"] == b["id"]      # due soonest goes next
        focus.respond("start", now=t)
        assert b["state"] == "now" and focus.W["prompt"] is None
        focus.act(b["id"], "done", now=t + 60)
        assert b["state"] == "done" and focus.listing(t + 60)["done"][0]["id"] == b["id"]
    finally:
        config.DATA, focus._xs = real, None
        focus.W.clear()
        focus.W.update(w)
        LIVE.pop("focus", None)
        LIVE.pop("focus_verdict", None)


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
