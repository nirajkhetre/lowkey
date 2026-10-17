"""Samples the foreground window every few seconds and appends it to data/activity-YYYY-MM-DD.jsonl.

Standard library only. Each platform function returns (app, window title, idle seconds, pid).
"""
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

from . import focus
from .config import AFK_S, CONFIG, DATA, LIVE, SAMPLE_S

try:
    import ctypes.wintypes  # only the Windows tracker uses it
except (ImportError, ValueError):
    pass


def foreground_windows():
    u32, k32, w = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.wintypes
    hwnd = u32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(hwnd, buf, 512)
    pid = w.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    app = ""
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        pbuf, size = ctypes.create_unicode_buffer(260), w.DWORD(260)
        if k32.QueryFullProcessImageNameW(h, 0, pbuf, ctypes.byref(size)):
            app = os.path.basename(pbuf.value)
        k32.CloseHandle(h)

    class LII(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    lii = LII(ctypes.sizeof(LII), 0)
    u32.GetLastInputInfo(ctypes.byref(lii))
    idle = (k32.GetTickCount() - lii.dwTime) / 1000
    return app, buf.value, idle, pid.value


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout.strip()


MAC_SCRIPT = ['tell application "System Events" to set p to first application process whose frontmost is true',
              'set t to ""',
              'try', 'tell application "System Events" to set t to name of front window of p', 'end try',
              'tell application "System Events" to return (name of p) & linefeed & t & linefeed & (unix id of p)']


def foreground_mac():
    # Window titles need System Settings > Privacy & Security > Accessibility for your terminal/Python.
    out = run("osascript", *[a for line in MAC_SCRIPT for a in ("-e", line)]).splitlines()
    app, title, pid = (out + ["", "", "0"])[:3]
    m = re.search(r'"HIDIdleTime" = (\d+)', run("ioreg", "-c", "IOHIDSystem"))
    idle = int(m.group(1)) / 1e9 if m else 0
    return app, title, idle, int(pid) if pid.isdigit() else 0


def foreground_linux():
    # X11 only (needs xdotool + xprintidle). Wayland deliberately hides other apps' windows.
    wid = run("xdotool", "getactivewindow")
    pid = int(run("xdotool", "getwindowpid", wid) or 0)
    app = run("ps", "-p", str(pid), "-o", "comm=") if pid else ""
    return app, run("xdotool", "getwindowname", wid), int(run("xprintidle") or 0) / 1000, pid


foreground = {"win32": foreground_windows, "darwin": foreground_mac}.get(sys.platform, foreground_linux)


def should_record(app, title, idle, pid, never):
    """Idle, paused, lowkey's own windows and never_track apps are never written to disk."""
    text = f"{app} {title}".lower()
    return bool(title) and pid != os.getpid() and idle < AFK_S and not LIVE["paused"] and not any(n in text for n in never)


def track():
    never = [s.lower() for s in CONFIG.get("never_track", [])]
    while True:
        try:
            app, title, idle, pid = foreground()
            LIVE["idle"] = idle
            recorded = should_record(app, title, idle, pid, never)
            focus.watch(app, title, recorded)  # are you on what you said you'd do?
            if recorded:
                ev = {"ts": round(time.time()), "dur": SAMPLE_S, "app": app, "title": title[:200]}
                minutes = LIVE.setdefault("minutes", {})  # feeds the island's activity bars
                m = int(time.time() // 60)
                minutes[m] = minutes.get(m, 0) + SAMPLE_S
                for old in [k for k in minutes if k < m - 60]:
                    del minutes[old]
                day = datetime.now().strftime("%Y-%m-%d")
                with open(DATA / f"activity-{day}.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception as e:  # never let the tracker die (and don't spam the same error every 5s)
            if str(e) != LIVE.get("tracker_error"):
                print("tracker:", e)
                LIVE["tracker_error"] = str(e)
        time.sleep(SAMPLE_S)
