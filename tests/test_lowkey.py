"""Core logic checks. Run: python -m pytest tests  (or: python tests/test_lowkey.py)"""
import json
import os
import sys
import tempfile
import time
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
        assert call("POST", "/api/config", '{"clients": []}', **js) == 409                   # the demo's clients are fixed
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
        focus.act(a["id"], "start", now=t)
        focus.act(a["id"], "drop", now=t)                                                      # delete what's on now...
        assert focus.current() is None and a["id"] not in [x["id"] for x in focus.listing(t)["next"]]
        focus.act(a["id"], "restore", now=t)                                                   # ...and undo it, time and all
        assert focus.current() is a and a["spent_s"] == 60 and "was" not in a
        focus.act(c["id"], "drop", now=t)
        focus.act(a["id"], "drop", now=t)                                                      # only the latest drop is kept
        assert [x["id"] for x in focus._xs if x["state"] == "dropped"] == [a["id"]]
    finally:
        config.DATA, focus._xs = real, None
        focus.W.clear()
        focus.W.update(w)
        LIVE.pop("focus", None)
        LIVE.pop("focus_verdict", None)


def test_receipts_renames_and_off_the_clock():
    from lowkey import config, focus, server
    real = config.DATA
    config.DATA = labeler.DATA = Path(tempfile.mkdtemp())  # both: the labeler reads activity through its own name
    focus._xs = None
    try:
        m = labeler.add_manual("1h call with acme at 3pm", "2026-10-16")
        assert (m["client"], m["task"], m["active_s"]) == ("Acme Studio", "Call with acme", 3600)
        assert [s["id"] for s in labeler.day_sessions("2026-10-16")] == [m["id"]]           # merged into its day
        from datetime import datetime
        ten = datetime(2026, 10, 16, 10, 0).timestamp()
        g = labeler.add_manual("call with nimbus", "2026-10-16", start=ten, dur_min=45)   # a gap picked on the timeline
        assert (g["client"], g["start"], g["active_s"]) == ("Nimbus Labs", ten, 2700)
        assert focus.entry("2h call at 9am", "2026-10-16", ten, 45)["dur_min"] == 120       # the words win
        soon = time.time() - 60  # a minute ago, for half an hour: not over yet
        for day, start, dur in (("2026-10-16", None, None), ("2026-10-16", ten + 86400, 30),
                                (datetime.fromtimestamp(soon).strftime("%Y-%m-%d"), soon, 30)):
            try:
                focus.entry("call", day, start, dur)
                raise AssertionError(f"accepted {day} {start} {dur}")
            except ValueError as x:
                assert str(x) in ("how long was it? add a length, like 1h or 30m", "start", "that hasn't happened yet")
        labeler.delete_manual(g["id"])
        config.save("edits.json", {m["id"]: {"status": "billed"}})
        labeler.rename_client("Acme Studio", "Acme Labs")                                     # history follows the name
        assert labeler.day_sessions("2026-10-16")[0]["client"] == "Acme Labs"
        labeler.delete_manual(m["id"])
        assert labeler.day_sessions("2026-10-16") == [] and m["id"] not in config.load("edits.json", {})
    finally:
        config.DATA = labeler.DATA = real
        focus._xs = None
    assert labeler.source("chrome.exe", "lofi beats - YouTube - Google Chrome") == "YouTube"
    assert labeler.source("chrome.exe", "Swiggy - Order food online - Google Chrome") == "Swiggy"  # site first or last
    assert labeler.source("msedge.exe", "(3) WhatsApp - Personal - Microsoft Edge") == "WhatsApp"
    assert labeler.source("chrome.exe", "New Tab - Google Chrome") is None                     # a blank tab isn't anywhere
    assert labeler.category("Netflix", [], {}, False) == "watching" and labeler.category("Tiny Tool", [], {}, False) == "other"
    me, clients, renames = server.clean_config({"me": {"daily_goal_h": "7"}, "renames": {"Acme Studio": "Acme Labs", "x": "nope"},
                                                "clients": [{"name": "Acme Labs", "rate": "1500", "hints": ["acme", "a", ""], "color": "red"}]})
    assert me == {"daily_goal_h": 7} and renames == {"Acme Studio": "Acme Labs"}
    assert clients == [{"name": "Acme Labs", "rate": 1500, "hints": ["acme"], "color": "#7AA2FF"}]
    for bad in ([{"name": "Personal"}], [{"name": "A1"}, {"name": "a1"}], [{"name": "X", "rate": -5}]):
        try:
            server.clean_config({"clients": bad})
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass


def test_merge_joins_consecutive_same_client_slots():
    lab = lambda c: {"client": c, "task": f"work for {c}", "billable": c != "Personal", "by": "test"}
    w = lambda: defaultdict(float, {("a", "b"): 300})
    t = 1_700_000_100 - 1_700_000_100 % SLOT_S
    slots = {t: (w(), lab("Acme Studio")), t + SLOT_S: (w(), lab("Acme Studio")),
             t + 2 * SLOT_S: (w(), lab("Personal")), t + 4 * SLOT_S: (w(), lab("Personal"))}  # gap before last
    s = labeler.merge(slots, "day")
    assert [x["client"] for x in s] == ["Acme Studio", "Personal", "Personal"]
    assert s[0]["active_s"] == 600 and s[0]["end"] == t + 2 * SLOT_S


def test_a_new_slot_length_never_orphans_reviews():
    from datetime import datetime
    from lowkey import config
    real, demo, slot = config.DATA, labeler.DEMO, LIVE["settings"].get("slot")
    config.DATA, labeler.DEMO = Path(tempfile.mkdtemp()), False
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        assert labeler.slot_len("2026-01-05") == SLOT_S                        # days from before the setting: 15 min
        LIVE["settings"]["slot"] = "5"
        assert labeler.slot_len(today) == 300
        LIVE["settings"]["slot"] = "10"
        assert labeler.slot_len(today) == 600                                   # nothing reviewed yet: switches now
        config.save("edits.json", {f"{today}-1792130000": {"status": "billed"}})
        LIVE["settings"]["slot"] = "15"
        assert labeler.slot_len(today) == 600                                   # reviewed: today keeps its sessions
        assert config.load("slots.json", {}) == {today: 600}                    # and tomorrow starts at 15
        config.save("slots.json", {})                                           # updating lowkey mid-day, reviews made
        assert labeler.slot_len(today) == SLOT_S                                # on 15-min slots: today stays 15
    finally:
        config.DATA, labeler.DEMO = real, demo
        LIVE["settings"]["slot"] = slot


def test_eval_slices_and_scores_against_hints():
    from lowkey import eval as ev
    with tempfile.TemporaryDirectory() as d:
        real, labeler.DATA = labeler.DATA, Path(d)
        try:
            t = 1_700_000_100 - 1_700_000_100 % SLOT_S
            (Path(d) / "activity-x.jsonl").write_text("\n".join(json.dumps(e) for e in [
                {"ts": t, "dur": 400, "app": "Code.exe", "title": "auth.ts - acme-website"},
                {"ts": t + 400, "dur": 200, "app": "chrome.exe", "title": "Instagram"}]), encoding="utf-8")
            five, fifteen = ev.slots(5), ev.slots(15)
        finally:
            labeler.DATA = real
    assert [sum(w.values()) for _, w in five] == [300, 300] and len(fifteen) == 1
    assert [ev.truth(w)[0] for _, w in five] == ["Acme Studio", "Personal"]   # second slot: 200 s Instagram, 100 s acme
    # rules picks any hinted client over Personal: right on slot 1, wrong on slot 2, which still bills 100 s right
    n, hits, min_pct, *_ = ev.score(five, labeler.rules)
    assert (n, hits, round(min_pct, 1)) == (2, 1, 66.7)
    n, hits, min_pct, *_ = ev.score(fifteen, labeler.rules)
    assert (n, hits, round(min_pct, 1)) == (1, 1, 66.7)                      # one slot, Acme's by majority
    assert list(ev.hide({("Code.exe", "auth.ts - acme-website"): 5})) == [("Code.exe", "auth.ts -")]  # --blind
    assert [round(x, 1) for x in ev.wilson(152, 155)] == [94.5, 99.3]
    # "check me": two wrong labels, each under 60% backed, so both flagged; one right session that's 67% backed isn't
    assert ev.check_me(five, ["Personal", "Acme Studio"]) == (2, 2, 2, 2)
    assert ev.check_me(five, ["Acme Studio", "Acme Studio"]) == (1, 0, 0, 0)  # merged: 400 of 600 s acme


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
