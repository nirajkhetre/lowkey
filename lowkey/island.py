"""The island: a notch that hides in a screen edge (top by default) and springs open on hover.

PySide6 + QPainter: anti-aliased, per-pixel transparent, never takes keyboard focus.
States: lip (tucked away) -> pill (hover) -> open (keep hovering or click), plus "toast" pop-outs.
The pin button (or a double-click) keeps the pill out instead of tucking it away.
The open card is laid out like a Live Activity: two stats, three icon buttons, rarer actions behind "more".
Settings open inside the island; hovering an option pops out a tiny screen acting it out.
Changes made in the dashboard fly here as little capsules (out of the browser and across the desktop when they
have to); the island swallows each one, gulps and says what changed.
"""
import ctypes, math, signal, subprocess, sys, time, webbrowser

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QCursor, QFont, QFontMetricsF, QFontDatabase, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient, QRegion, QTransform
from PySide6.QtWidgets import QApplication, QWidget

from . import jelly
from . import focus
from .config import PERSONAL, update_settings
from .mascot import Mascot

TXT, DIM, FAINT = QColor(245, 245, 245), QColor(150, 150, 150), QColor(255, 255, 255, 16)
GREY = QColor("#7a7a7a")
NIGHT, DUSK, AURORA = QColor("#9B8CFF"), QColor("#FF7AD9"), QColor("#4FD1C5")  # "off the record"
MIND = (QColor("#B8FF3B"), QColor("#7AA2FF"), QColor("#FF7AD9"))  # the local model at work: the dashboard's sparkle colours


def mix(a, b, t):
    return QColor(*(round(x + (y - x) * t) for x, y in zip(a.getRgb()[:3], b.getRgb()[:3])))
def ease(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def back(u):
    """Ease out with a little overshoot, like the island's springs."""
    u = max(0.0, min(1.0, u)) - 1
    return 1 + 2.7 * u ** 3 + 1.7 * u ** 2


def lerp_rect(a, b, u):
    return QRectF(*(x + (y - x) * u for x, y in zip(a.getRect(), b.getRect())))


SIZES = {"lip": (150, 8), "pill": (330, 42), "toast": (360, 48), "open": (440, 214), "settings": (440, 230), "prompt": (440, 126)}
FONTS = Path(__file__).parent / "web" / "fonts"  # Bricolage Grotesque, Instrument Serif, Geist Mono (all OFL)
EAR, PAD = 10, 24  # concave ears where the notch meets the screen edge; room for the soft shadow
UNDO_S = 5.0  # how long "not work" can be undone
EDGES = ("top", "bottom", "left", "right")
# settings rows: key, row label, then (value, segment label, preview title, what it does)
SETTINGS_UI = (
    ("edge", "lives on", (("top", "top", "top edge", "hangs from the top edge, like a MacBook notch"),
                          ("bottom", "bottom", "bottom edge", "sits on the bottom edge, by your taskbar"),
                          ("left", "left", "left edge", "peeks out from the left side of your screen"),
                          ("right", "right", "right edge", "peeks out from the right side of your screen"))),
    ("taskbar", "taskbar", (("below", "below it", "below the taskbar", "hangs below the taskbar, never covers it"),
                            ("over", "over it", "over the taskbar", "sits over the taskbar: the true notch look"))),
    ("rest", "at rest", (("lip", "tucked", "tucked away", "just a glowing lip until you hover"),
                         ("pill", "pill", "always a pill", "client, timer and money always in view"))))
OPTION = {(k, o[0]): o for k, _, opts in SETTINGS_UI for o in opts}
PEEK_W, PEEK_H, PEEK_M, NUB = 212, 160, 18, 7  # preview card, margin for its shadow, the arrow pointing at the option
MINI = {"lip": (0.2, 0.03), "pill": (0.42, 0.085), "open": (0.5, 0.3)}  # island sizes on the tiny screen


def fmt(s):
    m = int(s // 60)
    return f"{m}m" if m < 60 else f"{m // 60}h {m % 60:02d}m"


def clock(s):
    s = max(0, int(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


UI = ["Bricolage Grotesque", "Segoe UI Variable Display", "SF Pro Display", "Helvetica Neue", "sans-serif"]
NUM = ["Geist Mono", "Cascadia Code", "SF Mono", "Menlo", "monospace"]
SERIF = ["Instrument Serif", "Georgia", "serif"]


def font(px, weight=QFont.Normal, families=UI, italic=False):
    f = QFont()
    f.setItalic(italic)
    f.setFamilies(families)  # first installed family wins: Windows, then macOS, then Linux
    f.setPixelSize(round(px))
    f.setWeight(weight)
    return f


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", ctypes.c_long * 4), ("rcWork", ctypes.c_long * 4), ("dwFlags", ctypes.c_ulong)]


def fullscreen_app(own=0):
    """True when the window in front covers the whole main screen (a video, a game, slides). Maximized windows
    and the desktop itself don't count. Windows only; macOS gives fullscreen apps their own Space, where the island
    isn't shown anyway."""
    if sys.platform != "win32":
        return False
    try:
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        if not h or h == own or u.IsZoomed(h):
            return False
        cls = ctypes.create_unicode_buffer(32)
        u.GetClassNameW(h, cls, 32)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return False
        r, mi = (ctypes.c_long * 4)(), MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        u.GetWindowRect(h, r)
        if not u.GetMonitorInfoW(u.MonitorFromWindow(h, 2), ctypes.byref(mi)) or not mi.dwFlags & 1:
            return False  # on another monitor: the island's screen is free
        m = mi.rcMonitor
        return r[0] <= m[0] and r[1] <= m[1] and r[2] >= m[2] and r[3] >= m[3]
    except Exception:
        return False


def reduced_motion():
    """The OS "reduce motion" / "show animations" switch, read once at startup."""
    try:
        if sys.platform == "win32":
            on = ctypes.c_int(1)
            ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0)  # SPI_GETCLIENTAREAANIMATION
            return not on.value
        cmd = (["defaults", "read", "com.apple.universalaccess", "reduceMotion"] if sys.platform == "darwin"
               else ["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"])
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=2).stdout.strip()
        return out == ("1" if sys.platform == "darwin" else "false")
    except Exception:
        return False


class Spring:
    """Critically-ish damped spring: slight overshoot reads as 'bouncy', like the real Dynamic Island."""

    def __init__(self, x, k=260.0, d=24.0):
        self.x = self.target = float(x)
        self.v, self.k, self.d = 0.0, k, d

    def step(self, dt):
        self.v += (self.k * (self.target - self.x) - self.d * self.v) * dt
        self.x += self.v * dt

    def snap(self):
        self.x, self.v = self.target, 0.0


class Peek(QWidget):
    """The hover preview beside a settings option. Its own window, so it can float outside the island,
    and transparent to the mouse, so it never steals the hover from the option it explains."""

    def __init__(self, island):
        super().__init__()
        self.island = island
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
                            | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput)
        for a in (Qt.WA_TranslucentBackground, Qt.WA_ShowWithoutActivating, Qt.WA_TransparentForMouseEvents,
                  Qt.WA_MacAlwaysShowToolWindow):
            self.setAttribute(a)
        self.resize(PEEK_W + 2 * PEEK_M, PEEK_H + 2 * PEEK_M)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.island.draw_peek(p, time.time())
        p.end()


def flight_at(f, t):
    """A dashboard change t seconds into its flight: the page's own curve (an arc, pulled in as t^2.1) and scale."""
    k = max(0.0, min(1.0, (t - f["lift"]) / f["dur"]))
    u = k ** 2.1
    q = 1 - u
    (sx, sy), (cx, cy), (ix, iy) = f["S"], f["C"], f["I"]
    x, y = q * q * sx + 2 * q * u * cx + u * u * ix, q * q * sy + 2 * q * u * cy + u * u * iy
    size, st = 1 - 0.42 * u, max(0.0, (u - 0.5) / 0.5)
    along, across = size * (1 + 0.55 * st), size * (1 - 0.4 * st)  # it stretches along its path as it speeds up
    return (x, y, across, along) if f["edge"] in ("top", "bottom") else (x, y, along, across)


class Flight(QWidget):
    """A change crossing the desktop from the browser to the island. The page draws its capsule inside its own
    viewport; this window draws the very same capsule (same curve, same clock) everywhere outside it, so the two
    halves meet at the browser's edge and read as one. Small, click-through, and only alive during a flight."""

    def __init__(self, island):
        super().__init__()
        self.island, self.c = island, None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
                            | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput)
        for a in (Qt.WA_TranslucentBackground, Qt.WA_ShowWithoutActivating, Qt.WA_TransparentForMouseEvents,
                  Qt.WA_MacAlwaysShowToolWindow):
            self.setAttribute(a)

    def paintEvent(self, _):
        if self.c:
            p = QPainter(self)
            p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
            self.island.draw_flight(p, self.c["flight"], time.time())
            p.end()


class Island(QWidget):
    def __init__(self, live, actions, currency="₹", goal_h=6):
        self.app = QApplication.instance() or QApplication([])
        super().__init__()
        for name in ("BricolageGrotesque.ttf", "InstrumentSerif-Italic.ttf", "GeistMono.ttf"):
            QFontDatabase.addApplicationFont(str(FONTS / name))
        self.live, self.actions, self.cur, self.goal = live, actions, currency, goal_h * 3600
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)  # macOS hides tool windows when the app is inactive
        self.setMouseTracking(True)
        self.W, self.H = Spring(SIZES["lip"][0]), Spring(SIZES["lip"][1])
        self.fade = {m: Spring(0, 320, 34) for m in ("pill", "toast", "open", "settings", "prompt")}
        self.dark = Spring(0, 90, 19)  # 0 = on the record, 1 = midnight
        self.mind = Spring(0, 120, 18)  # 1 while the local model is working: its colours run round the edge
        self.mode, self.force, self.pinned, self.click_open = "lip", None, False, False
        self.hover_since = self.left_at = None
        self.toast_msg, self.toast_until, self.toast_color, self.toast_len = "", 0.0, GREY, 2.8
        self.seen_client, self.milestone = None, None
        self.task, self.task_t0 = "", 0.0
        self.mascot, self.quip = Mascot(live, self.goal, currency), None
        self.buttons, self.hot, self.pressed = {}, None, None
        self.edge, self.over, self.rest, self.raised_at = self.want_edge(), False, "lip", 0.0
        self.hov, self.prs = {}, {}  # hover and press springs per control
        self.lines = {}  # per view: [what the info line shows, when it started]
        self.cap_key, self.hot_t = None, 0.0  # the caption follows the cursor with a little hover intent
        self.undo, self.undo_until, self.disabled = None, 0.0, set()
        self.pin_s = Spring(0, 260, 20)
        self.in_settings, self.hold_until = False, 0.0  # after a change moves it, it waits open for you
        self.quitting = 0.0  # when "quit lowkey" was pressed: it tucks away, then the app ends
        self.fs, self.fs_t = False, 0.0  # something is fullscreen: the island steps aside, like the menu bar on a Mac
        self.prompt_at, self.ring, self.last_prompt = None, (0.0, GREY), None  # the prompt on show; the info line's ring
        self.more, self.more_s = False, Spring(0, 300, 28)  # the footer's rarer actions
        self.notice, self.notice_until = "", 0.0
        self.thumbs = {}  # segmented-control thumbs, sliding between options
        self.slide, self.slide_edge = Spring(0, 220, 26), None  # glides when the taskbar mode moves it
        self.peek, self.peek_along, self.peek_key, self.peek_t0, self.nub = Spring(0, 340, 30), None, None, 0.0, 0.0
        self.peek_win = Peek(self)
        self.incoming, self.caught, self.glow_c, self.glow_t0 = [], set(), None, 0.0  # changes flying in from the dashboard
        self.flight_win = Flight(self)
        self.calm = self.mascot.calm = reduced_motion()
        self.coin_t0, self.last_money = 0.0, None
        self.money_view = Spring(0, 60, 15)  # the ₹ chip counts up
        self.last = time.time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self.place()
        self.show()

    # ---------- state ----------
    def color(self):
        L = self.live
        if L.get("paused"):
            return NIGHT
        if L.get("idle", 0) > 300 or not L.get("client"):
            return GREY
        return QColor(L.get("color", "#7a7a7a"))

    def toast(self, msg, color=None, secs=2.8):
        self.toast_msg, self.toast_color, self.toast_len = msg, color or self.color(), secs
        self.toast_until = time.time() + secs

    def watch_events(self, now):
        L = self.live
        client = L.get("client")
        if client and client != self.seen_client:
            if self.seen_client is not None:
                self.toast(f"switched to {client}", QColor(L.get("color", "#7a7a7a")))
                self.mascot.react("surprised", 2.5)
            self.seen_client = client
        step = int(L.get("money", 0) // 1000)
        if self.milestone is None:
            self.milestone = step
        elif step > self.milestone:
            self.milestone = step
            self.toast(f"{self.cur}{step * 1000:,} secured today", QColor("#B8FF3B"), 3.5)
            self.mascot.react("money", 4)
        task = L.get("task", "")
        if task != self.task:
            self.task, self.task_t0 = task, now

    def pick_mode(self, now):
        if self.force:
            return self.force
        if (self.live.get("focus") or {}).get("prompt") and not self.in_settings and not self.quitting and not self.fs:
            if self.frameGeometry().contains(QCursor.pos()):
                self.left_at, self.hold_until = None, 0.0
                self.hover_since = self.hover_since or now
            return "prompt"  # it asked you something: it stays until you answer (or it times out)
        resting = "pill" if self.pinned or self.rest == "pill" else "lip"
        if self.fs:
            resting = "lip"
        base = "toast" if now < self.toast_until and not self.fs else resting
        if self.frameGeometry().contains(QCursor.pos()):
            self.left_at, self.hold_until = None, 0.0
            self.hover_since = self.hover_since or now
            dwell = now - self.hover_since
            if self.click_open or dwell > 0.6 or self.mode in ("open", "settings"):
                self.click_open = True  # once open, it stays open while you're on it
                return "settings" if self.in_settings else "open"
            return "pill" if dwell > 0.12 else self.mode
        self.hover_since = None
        self.left_at = self.left_at or now
        if (now - self.left_at > 0.35 and now > self.hold_until) or self.mode == "prompt":  # small grace so it doesn't flicker
            self.click_open = self.in_settings = self.more = False  # (an answered question hands back at once)
            return base
        return self.mode

    def catch_changes(self, now):
        """The dashboard says when each flying change will land; swallow each one right on time, in order."""
        for c in self.live.get("catches", ()):
            if c["id"] not in self.caught:
                self.caught.add(c["id"])
                self.incoming.append(dict(c))
                self.plan_flight(self.incoming[-1])
        for c in self.incoming:
            if not c.get("done") and now >= c["at"]:
                c["done"] = True
                if now - c["at"] < 1.5:  # stale ones (island was busy elsewhere) land quietly
                    self.swallow(c, now)
        self.incoming = [c for c in self.incoming if not c.get("done") or now - c["at"] < 1.0]

    def plan_flight(self, c):
        """Size the overlay to just the stretch of path the page can't draw (outside its viewport), with room for
        the capsule itself. Nothing outside the page (say, the browser sits under the island): no overlay at all."""
        f = c.get("flight")
        if not f or self.calm:
            return
        f = c["flight"] = {**f, "color": c["color"]}
        vx, vy, vw, vh = f["vp"]
        w, h = f["size"]
        xs, ys = [], []
        for n in range(97):
            x, y, sx, sy = flight_at(f, f["lift"] + f["dur"] * n / 96)
            hw, hh = w * max(sx, sy, 1.0) / 2 + 4, h * max(sx, sy, 1.0) / 2 + 12  # room for its shadow too
            if x - hw < vx or y - hh < vy or x + hw > vx + vw or y + hh > vy + vh:
                xs += [x - hw, x + hw]
                ys += [y - hh, y + hh]
        if xs:
            f["box"] = [math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs) - min(xs)) + 1, math.ceil(max(ys) - min(ys)) + 1]

    def fly_tick(self, now):
        """Keep the overlay up while a flight is out between the page and the island; the island stays above it,
        so the capsule ends by sliding under the island's edge."""
        win = self.flight_win
        c = next((c for c in self.incoming if not c.get("done") and c.get("flight", {}).get("box")
                  and c["flight"]["t0"] + c["flight"]["lift"] <= now), None)
        if c is None:
            if win.isVisible():
                win.hide()
            win.c = None
            return
        if win.c is not c:
            win.c = c
            win.setGeometry(*c["flight"]["box"])
            win.show()
            self.raise_()
        win.update()

    def draw_flight(self, p, f, now):
        """The capsule, exactly as the page draws it (island black, a dot in the client's colour, the label), clipped
        to everything outside the browser's viewport so the page's half and this half meet seamlessly."""
        bx, by, bw, bh = f["box"]
        vx, vy, vw, vh = f["vp"]
        p.setClipRegion(QRegion(0, 0, bw, bh).subtracted(QRegion(round(vx - bx), round(vy - by), round(vw), round(vh))))
        x, y, sx, sy = flight_at(f, now - f["t0"])
        w, h = f["size"]
        p.translate(x - bx, y - by)
        p.scale(sx, sy)
        r = QRectF(-w / 2, -h / 2, w, h)
        p.setPen(Qt.NoPen)
        for i in range(3, 0, -1):  # the same soft drop shadow as the page's capsule
            p.setBrush(QColor(0, 0, 0, 16))
            p.drawRoundedRect(r.adjusted(-i * 2, -i + 3 * i, i * 2, i + 3 * i), h / 2 + i, h / 2 + i)
        p.setPen(QPen(QColor(255, 255, 255, 36), 1))
        p.setBrush(QColor(11, 11, 11))
        p.drawRoundedRect(r, h / 2, h / 2)
        col, dot = QColor(f["color"]), QPointF(r.left() + 14.5, 0)
        glow = QRadialGradient(dot, 10)
        c0, c1 = QColor(col), QColor(col)
        c0.setAlpha(150)
        c1.setAlpha(0)
        glow.setColorAt(0, c0)
        glow.setColorAt(1, c1)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(dot, 10, 10)
        p.setBrush(col)
        p.drawEllipse(dot, 4.5, 4.5)
        p.setPen(QColor(244, 244, 244))
        p.setFont(font(13.5, QFont.ExtraBold))
        p.drawText(QRectF(r.left() + 26, r.top(), w - 39, h), Qt.AlignLeft | Qt.AlignVCenter, f["label"])

    def swallow(self, c, now):
        """A change just docked: a springy gulp (it bulges inward and wider), a flash of its colour, and a pop-out
        that says what it was. The creature reacts too."""
        col = QColor(c["color"])
        self.toast(c["text"], col, 2.8)
        self.glow_c, self.glow_t0 = col, now
        if not self.calm:
            side = self.edge in ("top", "bottom")
            (self.H if side else self.W).v += 420
            (self.W if side else self.H).v += 260
        self.mascot.react("money" if c["kind"] == "billed" else "surprised", 2.2)

    def inner(self, b):
        """The middle of the island's inward-facing side, and the direction that points into the island."""
        return {"top": (QPointF(b.center().x(), b.bottom()), QPointF(0, -1)),
                "bottom": (QPointF(b.center().x(), b.top()), QPointF(0, 1)),
                "left": (QPointF(b.right(), b.center().y()), QPointF(-1, 0)),
                "right": (QPointF(b.left(), b.center().y()), QPointF(1, 0))}[self.edge]

    def want_edge(self):
        e = (self.live.get("settings") or {}).get("edge")
        return e if e in EDGES else "top"

    def tick(self):
        now = time.time()
        dt, self.last = min(0.033, now - self.last), now
        st, L = self.live.get("settings") or {}, self.live
        self.over, self.rest = st.get("taskbar") == "over", st.get("rest", "lip")
        if now - self.fs_t > 0.5:
            self.fs, self.fs_t = fullscreen_app(int(self.winId())), now
        self.watch_events(now)
        self.catch_changes(now)
        self.watch_prompt(now)
        self.fly_tick(now)
        self.quip = self.mascot.update(now)
        self.disabled = {"personal"} if (L.get("paused") or L.get("client") in (None, "", PERSONAL)) else set()
        if sys.platform == "darwin":
            self.disabled.add("set:taskbar:over")  # macOS keeps its menu bar on top
        self.mode = self.pick_mode(now)
        tw, th = SIZES[self.mode]
        if self.mode == "lip" and self.edge in ("left", "right"):
            tw, th = th, tw  # a side lip stands upright
        moving = self.want_edge() != self.edge
        if moving:  # a new edge: tuck into the old one, then bloom out of the new one
            side = self.edge in ("top", "bottom")
            th, tw = (0, tw) if side else (th, 0)
            if (self.H.x if side else self.W.x) < 1.5:
                self.edge = self.want_edge()
                self.W.x = self.H.x = self.W.v = self.H.v = 0.0
        if self.quitting or (self.fs and self.mode == "lip"):  # goodbye, or a fullscreen app: tuck all the way in
            th, tw = (0, tw) if self.edge in ("top", "bottom") else (th, 0)
            if self.quitting and now - self.quitting > 0.4:
                self.app.quit()
        self.W.target, self.H.target = tw, th
        for m, s in self.fade.items():
            s.target = 1.0 if m == self.mode and not moving and not self.quitting else 0.0
        for thumb in self.thumbs.values():
            thumb.step(dt)
            if self.calm:
                thumb.snap()
        self.dark.target = 1.0 if self.live.get("paused") else 0.0
        self.money_view.target = float(self.live.get("money", 0))
        if self.last_money is not None and self.live.get("money", 0) > self.last_money + 0.5:
            self.coin_t0 = now  # the coin flips when you earn
        self.last_money = self.live.get("money", 0)
        self.money_view.step(dt)
        for k, sp in self.hov.items():
            sp.target = 1.0 if self.hot == k else 0.0
            sp.step(dt)
        # hover intent: visuals react at once, but the caption waits a beat so sweeping across controls doesn't flicker
        wait = 0.2 if self.hot is None else 0.06 if self.cap_key is None else 0.12
        if self.hot != self.cap_key and now - self.hot_t >= wait:
            self.cap_key = self.hot
        self.pin_s.target = 1.0 if self.pinned else 0.0
        self.pin_s.step(dt)
        self.more_s.target = 1.0 if self.more else 0.0
        self.more_s.step(dt)
        if self.calm:
            self.more_s.snap()
        for k, sp in self.prs.items():
            sp.target = 0.95 if self.pressed == k else 1.0  # squish while held, springs back on release
            sp.step(dt)
        t = self.live.get("thought") or {}
        self.mind.target = 1.0 if self.live.get("thinking") or now - t.get("at", 0) < 1.2 else 0.0  # long enough to see
        for s in (self.W, self.H, self.dark, self.slide, self.mind, *self.fade.values()):
            s.step(dt)
        self.place()
        self.update()
        self.place_peek(now, dt, moving)
        # resting costs almost nothing: 60 fps only while something moves or you're on it, 30 for a resting pill
        # (its creature still blinks), 15 for the breathing lip
        settled = (all(abs(s.v) < 1 and abs(s.target - s.x) < 0.5 for s in (self.W, self.H, self.slide, self.money_view))
                   and all(abs(s.target - s.x) < 0.01 for s in (self.dark, *self.fade.values())))
        busy = (not settled or self.mode not in ("lip", "pill") or self.hover_since or self.incoming or self.quitting
                or (self.left_at and now - self.left_at < 0.5) or now < self.toast_until or self.peek.x > 0.01 or self.mind.x > 0.01)
        ms = 16 if busy else 33 if self.mode == "pill" else 66
        if self.timer.interval() != ms:
            self.timer.setInterval(ms)

    def place(self, snap=False):
        """Attach to the chosen edge. By default the island hangs from the *work area*, so a taskbar on
        the same edge (or the macOS menu bar) pushes it inward instead of covering it. With taskbar="over"
        it sits on the physical screen edge and is re-raised above the taskbar on Windows. Switching between
        the two glides on a spring instead of jumping."""
        scr = QGuiApplication.primaryScreen()
        full, work = scr.geometry(), scr.availableGeometry()
        side = ("top" if work.top() > full.top() else "bottom" if work.bottom() < full.bottom()
                else "left" if work.left() > full.left() else "right" if work.right() < full.right() else "none")
        self.live["taskbar"] = side
        edge, w, h = self.edge, max(0.0, self.W.x), max(1.0, self.H.x)
        over = (self.over and side == edge) or self.fs  # fullscreen: hang from the real edge, the taskbar is gone
        a = full if over else work
        self.slide.target = {"top": a.top(), "bottom": a.bottom() + 1, "left": a.left(), "right": a.right() + 1}[edge]
        if snap or self.slide_edge != edge:
            self.slide_edge = edge
            self.slide.snap()
        line = self.slide.x
        if edge in ("top", "bottom"):
            ww, wh = w + 2 * (EAR + PAD), h + PAD
            x = a.center().x() - ww / 2
            y = line if edge == "top" else line - wh
        else:
            ww, wh = w + PAD, h + 2 * (EAR + PAD)
            y = a.center().y() - wh / 2
            x = line if edge == "left" else line - ww
        self.setGeometry(round(x), round(y), round(ww), round(wh))
        tip, _ = self.inner(self.body())  # where a change from the dashboard should fly to, in screen coordinates
        self.live["island"] = {"x": round(x) + round(tip.x()), "y": round(y) + round(tip.y()), "edge": edge,
                               "screen": [full.x(), full.y(), full.width(), full.height()]}
        if over and not self.fs and sys.platform == "win32" and time.time() - self.raised_at > 0.4:  # never fight a game for the top
            # the taskbar is also "always on top"; whoever was raised last wins, so keep winning
            ctypes.windll.user32.SetWindowPos(int(self.winId()), -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
            self.raised_at = time.time()

    def settle(self):
        """Jump straight to the target state (used for screenshots/tests)."""
        self.edge = self.want_edge()
        self.tick()
        self.mascot.snap()
        for s in (self.W, self.H, self.dark, self.peek, self.more_s, *self.fade.values(), *self.thumbs.values()):
            s.snap()
        self.place(snap=True)

    # ---------- painting ----------
    def body(self):
        w, h = self.W.x, max(1.0, self.H.x)
        x, y = {"top": (PAD + EAR, 0), "bottom": (PAD + EAR, PAD), "left": (0, PAD + EAR), "right": (PAD, PAD + EAR)}[self.edge]
        return QRectF(x, y, w, h)

    def notch(self, b):
        """Build the notch as if it hung from the top edge, then mirror/rotate it onto the real edge."""
        side = self.edge in ("top", "bottom")
        a, d = (b.width(), b.height()) if side else (b.height(), b.width())  # along the edge, depth into the screen
        e = min(EAR, d * 0.6)
        r = max(0.5, min(22.0, d - e, a / 2, d / 2 if d < 46 else 22.0))
        x0, x1 = PAD + EAR, PAD + EAR + a
        P = QPainterPath()
        P.moveTo(x0 - e, 0)
        P.quadTo(x0, 0, x0, e)
        P.lineTo(x0, d - r)
        P.arcTo(QRectF(x0, d - 2 * r, 2 * r, 2 * r), 180, 90)
        P.lineTo(x1 - r, d)
        P.arcTo(QRectF(x1 - 2 * r, d - 2 * r, 2 * r, 2 * r), 270, 90)
        P.lineTo(x1, e)
        P.quadTo(x1, 0, x1 + e, 0)
        P.closeSubpath()
        W, H = self.width(), self.height()
        T = {"top": QTransform(), "bottom": QTransform(1, 0, 0, -1, 0, H),
             "left": QTransform(0, 1, 1, 0, 0, 0), "right": QTransform(0, 1, -1, 0, W, 0)}[self.edge]
        return T.map(P), r

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        now, b = time.time(), self.body()
        if self.fs and min(b.width(), b.height()) < 1.5:  # tucked away over a fullscreen app: not even a shadow
            return p.end()
        path, r = self.notch(b)

        # soft shadow
        p.setPen(Qt.NoPen)
        for i in range(7, 0, -1):
            p.setBrush(QColor(0, 0, 0, 9))
            p.drawRoundedRect(b.adjusted(-i * 1.6, -i * 1.6, i * 1.6, i * 2.4), r + i, r + i)

        g = QLinearGradient(0, b.top(), 0, b.bottom())
        g.setColorAt(0, QColor(14, 14, 14))
        g.setColorAt(1, QColor(4, 4, 4))
        p.setBrush(g)
        p.drawPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        p.setClipPath(path)
        if self.dark.x > 0.02:
            self.draw_night(p, b, now, min(1.0, self.dark.x))
        if self.glow_c is not None and now - self.glow_t0 < 0.7:  # the swallowed change's colour, fading out
            tip, _ = self.inner(b)
            g = QRadialGradient(tip, 120)
            c0, c1 = QColor(self.glow_c), QColor(self.glow_c)
            c0.setAlpha(int(170 * (1 - (now - self.glow_t0) / 0.7)))
            c1.setAlpha(0)
            g.setColorAt(0, c0)
            g.setColorAt(1, c1)
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawRect(b)
        lip = 1 - max(s.x for s in self.fade.values())
        if lip > 0.02:
            self.draw_lip(p, b, now, min(1, lip))
        self.buttons = {}
        for mode, draw in (("pill", self.draw_pill), ("toast", self.draw_toast), ("open", self.draw_open),
                           ("settings", self.draw_settings), ("prompt", self.draw_prompt)):
            a = max(0.0, min(1.0, self.fade[mode].x))
            if a > 0.02:
                p.setOpacity(a)
                kept, self.buttons = self.buttons, {}
                draw(p, b, now)
                self.buttons = {**kept, **self.buttons} if mode == self.mode else kept  # a fading view isn't clickable
        if self.mind.x > 0.02:  # the model is thinking: its colours run round the island's edge, like a live mind
            k = min(1.0, self.mind.x)
            g = QConicalGradient(b.center(), 0 if self.calm else -now * 160 % 360)
            for pos, c in zip((0, 0.33, 0.66, 1), (*MIND, MIND[0])):
                c = QColor(c)
                c.setAlpha(int(230 * k))
                g.setColorAt(pos, c)
            p.setOpacity(1)
            p.setPen(QPen(QBrush(g), 3.2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        p.end()

    def draw_night(self, p, b, now, a):
        """Off the record: a midnight wash, a slow aurora and twinkling stars inside the island."""
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(22, 14, 52, int(185 * a)))
        p.drawRect(b)
        for i, (col, speed, phase) in enumerate(((NIGHT, 0.23, 0.0), (DUSK, 0.17, 2.1), (AURORA, 0.13, 4.2))):
            if self.calm:
                now = 0  # a still aurora
            cx = b.left() + b.width() * (0.5 + 0.42 * math.sin(now * speed + phase))
            cy = b.top() + b.height() * (0.4 + 0.35 * math.cos(now * speed * 1.3 + phase))
            g = QRadialGradient(QPointF(cx, cy), max(b.width(), b.height()) * (0.42 + 0.08 * math.sin(now * 0.5 + i)))
            c0, c1 = QColor(col), QColor(col)
            c0.setAlpha(int(85 * a))
            c1.setAlpha(0)
            g.setColorAt(0, c0)
            g.setColorAt(1, c1)
            p.setBrush(g)
            p.drawRect(b)
        for i in range(18):  # fixed spots spread by the golden ratio, each twinkling at its own pace
            tw = (math.sin(now * (1.4 + (i % 5) * 0.37) + i * 1.7) + 1) / 2
            p.setBrush(QColor(255, 255, 255, int(a * (25 + 130 * tw))))
            r = (0.55 + 1.0 * tw) * (1.6 if i % 6 == 0 else 1)
            p.drawEllipse(QPointF(b.left() + (i * 0.618034 % 1) * b.width(),
                                  b.top() + ((i * 0.381966 + 0.13) % 1) * b.height()), r, r)
        p.restore()

    def draw_lip(self, p, b, now, a):
        """A breathing glow line on the side of the lip that faces into the screen."""
        c = QColor(self.color())
        breathe = 0.55 + 0.45 * (math.sin(now * 2.2) + 1) / 2
        k = 2.2
        p1, p2 = {"top": (QPointF(b.left() + 18, b.bottom() - k), QPointF(b.right() - 18, b.bottom() - k)),
                  "bottom": (QPointF(b.left() + 18, b.top() + k), QPointF(b.right() - 18, b.top() + k)),
                  "left": (QPointF(b.right() - k, b.top() + 18), QPointF(b.right() - k, b.bottom() - 18)),
                  "right": (QPointF(b.left() + k, b.top() + 18), QPointF(b.left() + k, b.bottom() - 18))}[self.edge]
        g = QLinearGradient(p1, p2)
        for pos, alpha in ((0, 0), (0.5, int(255 * breathe * a)), (1, 0)):
            c.setAlpha(alpha)
            g.setColorAt(pos, QColor(c))
        p.setPen(QPen(g, k, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(p1, p2)

    def avatar(self, p, c, rad, now):
        """The mascot, inside the daily-goal ring. Click it and it tells you something about your day."""
        self.buttons["mascot"] = QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad)
        cursor = QPointF(self.mapFromGlobal(QCursor.pos())) if self.mode != "lip" else None
        self.mascot.draw(p, c, rad, now, cursor)

    def status(self):
        L = self.live
        if L.get("paused"):
            return "off the record", "nothing is being saved. hover again to come back"
        if L.get("idle", 0) > 300:
            return "on a break", "tracking resumes when you're back"
        if not L.get("client"):
            return "lowkey is listening", "first labels in about a minute"
        return L["client"], L.get("task", "")

    def session_s(self, now):
        start = self.live.get("session_start")
        return now - start if start and not self.live.get("paused") else 0

    def draw_pill(self, p, b, now):
        """Creature, name, then the time and today's money on the trailing edge. With an intention on, the name is
        what you said you'd do and the time is minutes on it, with a small ring against your estimate."""
        L, col = self.live, self.color()
        cy = b.top() + 21
        self.avatar(p, QPointF(b.left() + 25, cy), 15, now)
        fz = None if L.get("paused") else (L.get("focus") or {}).get("now")
        live = L.get("client") and not L.get("paused")
        right = b.right() - 100  # the time ends here; the money sits after it
        if live or fz:
            p.setFont(font(12.5, QFont.Normal, NUM))
            spent = round(fz["spent_s"] / 60) if fz else 0
            when = (f"{spent}/{fz['est_min']}m" if fz.get("est_min") else f"{spent}m") if fz else clock(self.session_s(now))
            tw = QFontMetricsF(p.font()).horizontalAdvance(when)
            p.setPen(DIM)
            p.drawText(QRectF(right - tw - 2, b.top(), tw + 2, 42), Qt.AlignVCenter | Qt.AlignRight, when)
            right -= tw + 8
            if fz:  # the ring sits right before the minutes it measures
                self.mini_ring(p, QPointF(right - 6, cy), 6.5, *self.focus_ring(fz))
                right -= 20
        if live:
            p.setFont(font(13.5, QFont.Bold, NUM))
            p.setPen(col)
            p.drawText(QRectF(b.right() - 96, b.top(), 82, 42), Qt.AlignVCenter | Qt.AlignRight, f"{self.cur}{L.get('money', 0):,.0f}")
        p.setPen(TXT)
        p.setFont(font(14, QFont.Bold))
        room = max(40.0, right - 8 - (b.left() + 48))
        name = QFontMetricsF(p.font()).elidedText(fz["text"] if fz else self.status()[0], Qt.ElideRight, room)
        p.drawText(QRectF(b.left() + 48, b.top(), room + 4, 42), Qt.AlignVCenter | Qt.AlignLeft, name)
        ex = b.left() + 48 + QFontMetricsF(p.font()).horizontalAdvance(name) + 12
        if not fz and live and L.get("idle", 0) < 300 and ex + 22 < right:  # a tiny live squiggle, when there's room
            sq = QPainterPath(QPointF(ex, cy))
            for i in range(1, 21):
                t = i / 20
                sq.lineTo(ex + 22 * t, cy + 4.2 * math.sin(t * 2 * math.pi * 1.5 - (0 if self.calm else now) * 6) * math.sin(t * math.pi))
            p.setPen(QPen(col, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(sq)

    def draw_toast(self, p, b, now):
        c = self.toast_color
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        pulse = 1 + 0.12 * math.sin(now * 8)
        p.drawEllipse(QPointF(b.left() + 24, b.top() + 23), 6 * pulse, 6 * pulse)
        p.setPen(TXT)
        p.setFont(font(14.5, QFont.Bold))
        p.drawText(QRectF(b.left() + 42, b.top(), b.width() - 56, 46), Qt.AlignVCenter | Qt.AlignLeft, self.toast_msg)
        age = now - (self.toast_until - self.toast_len)
        if age < 0.9 and not self.calm:  # one shimmer sweep when it pops out
            sx = b.left() - 80 + (b.width() + 160) * age / 0.9
            sh = QLinearGradient(sx - 60, 0, sx + 60, 0)
            sh.setColorAt(0, QColor(255, 255, 255, 0))
            sh.setColorAt(0.5, QColor(255, 255, 255, 38))
            sh.setColorAt(1, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(sh)
            p.drawRect(b)
        left = max(0.0, (self.toast_until - now) / self.toast_len)  # countdown bar, like a live activity
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 200))
        p.drawRoundedRect(QRectF(b.left() + 24, b.bottom() - 6, (b.width() - 48) * left, 2.5), 1.25, 1.25)

    def row(self, p, k, view="open"):
        """Stagger: row k fades/slides in a little after row k-1 (fade only under reduced motion)."""
        a = max(0.0, min(1.0, self.fade[view].x))
        t = max(0.0, min(1.0, (a - k * 0.09) / (1 - k * 0.09)))
        p.setOpacity(t)
        return 0 if self.calm else (1 - t) * 12

    def draw_open(self, p, b, now):
        """Laid out like a Live Activity on one 400 px column: header 16-56 (who, for how long, how much), info
        64-100, wave 108-146, footer 158-196. The footer keeps two quiet stats on the left and three round icon
        buttons on the right: go dark, open lowkey (the one filled, primary action) and more. Rarer actions wait
        behind more, which slides the footer over to them. Buttons carry no labels: hovering any control explains
        it in the info line, so the card itself can stay calm."""
        L, col = self.live, self.color()
        x, y0, W = b.left() + 20, b.top(), b.width() - 40
        paused = L.get("paused")

        # header: mascot | name over a status line | today's money on the trailing edge, where the pill keeps it
        y = y0 + self.row(p, 0)
        self.avatar(p, QPointF(x + 20, y + 36), 20, now)
        money = f"{self.cur}{max(0.0, self.money_view.x):,.0f}"
        mf, lf = font(19, QFont.Bold, NUM), font(11.5, QFont.Medium)
        mw = max(QFontMetricsF(mf).horizontalAdvance(money), QFontMetricsF(lf).horizontalAdvance("earned today"))
        hit = QRectF(x + W - mw - 10, y + 12, mw + 14, 46)
        self.buttons["money"] = hit
        self.wash(p, hit, self.hv("money"))
        flash = 0.0 if self.calm else max(0.0, 1 - (now - self.coin_t0) / 1.4)  # a fresh earning glows, then settles
        p.setFont(mf)
        p.setPen(mix(TXT, col, flash) if col.lightness() > 60 else TXT)
        p.drawText(QRectF(x + W - 200, y + 14, 196, 24), Qt.AlignRight | Qt.AlignVCenter, money)
        p.setFont(lf)
        p.setPen(DIM)
        p.drawText(QRectF(x + W - 200, y + 38, 196, 18), Qt.AlignRight | Qt.AlignVCenter, "earned today")

        title, sub = self.status()
        fz = None if paused else (L.get("focus") or {}).get("now")
        tw = hit.left() - 12 - (x + 52)
        p.setPen(TXT)
        p.setFont(font(23, QFont.Normal, SERIF, italic=True) if paused else font(17, QFont.ExtraBold))
        p.drawText(QRectF(x + 52, y + 14, tw, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(p.font()).elidedText(title, Qt.ElideRight, tw))
        # the status line: one dot says it all, and it pulses only while it's really recording
        idle = L.get("idle", 0) > 300
        live = bool(L.get("client")) and not paused and not idle
        dot = NIGHT if paused else col if live else GREY
        label = ("paused" if paused else "on a break" if idle else
                 f"this session  {clock(self.session_s(now))}" if L.get("client") else "listening")
        c = QPointF(x + 56, y + 47)
        if live and not self.calm:
            u = (now % 2.0) / 2.0
            p.setPen(QPen(QColor(dot.red(), dot.green(), dot.blue(), int(120 * (1 - u))), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, 3.2 + 4 * u, 3.2 + 4 * u)
        p.setPen(Qt.NoPen)
        p.setBrush(dot)
        p.drawEllipse(c, 3.2, 3.2)
        p.setPen(DIM)
        p.setFont(font(12, QFont.Normal, NUM))
        p.drawText(QRectF(x + 65, y + 38, tw - 13, 18), Qt.AlignLeft | Qt.AlignVCenter, label)

        # info line: an undo offer beats a fresh "done", then a hover hint, the mascot's reply, and the task
        y = y0 + self.row(p, 1)
        undo = self.undo and now < self.undo_until
        cap = None if (self.quip and self.cap_key == "mascot") else self.caption()
        if undo:
            src, text, ink, icon = "undo", "moved to side quests.", QColor(236, 238, 245), "info"
        elif now < self.notice_until:
            src, text, ink, icon = "notice:" + self.notice, self.notice, QColor(236, 238, 245), "check"
        elif cap:
            src, text, ink, icon = "cap:" + self.cap_key, cap, QColor(236, 238, 245), "info"
        elif self.quip:
            src, text, ink, icon = "quip:" + self.quip, self.quip, QColor(244, 244, 248), "bubble"
        elif fz:  # what you said you'd do, how long you've been on it, or that you've drifted
            fd = self.live.get("focus") or {}
            spent, est = round(fz["spent_s"] / 60), fz.get("est_min")
            drifting = fd.get("drift_min") and fd.get("what")
            text = (f"drifting · {fd['what']} {fd['drift_min']}m · you said: {fz['text']}" if drifting else
                    f"now: {fz['text']} · {spent}{f'/{est}' if est else ''} min")
            src, ink, icon = f"focus:{fz['id']}:{bool(drifting)}", QColor(236, 238, 245), "ring"
            self.ring = self.focus_ring(fz)
        else:
            src, text, ink, icon = "task", sub, QColor(214, 214, 220), None
        base = p.opacity()
        line, f = self.info_line(p, "open", src, text, ink, icon, x, y + 64, W, col, now,
                                 self.task_t0 if src == "task" and sub == self.task else None)
        if src == "task" or src.startswith("focus:"):  # the line itself opens your intentions in the dashboard
            self.buttons["intend"] = QRectF(x, y + 60, W, 40)
        if undo:  # the underline doubles as the countdown: it shrinks until the offer expires
            ux = line.left() + QFontMetricsF(f).horizontalAdvance("moved to side quests. ")
            uf = font(13.5, QFont.Bold)
            uw = QFontMetricsF(uf).horizontalAdvance("undo")
            hit = QRectF(ux - 6, y + 60, uw + 12, 26)
            self.buttons["undo"] = hit
            p.setFont(uf)
            p.setPen(mix(TXT, col, self.hv("undo")) if col.lightness() > 60 else TXT)
            p.drawText(QRectF(ux, line.top(), uw + 4, 18), Qt.AlignLeft | Qt.AlignVCenter, "undo")
            left = max(0.0, (self.undo_until - now) / UNDO_S)
            p.setPen(QPen(p.pen().color(), 1.5, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(ux, line.top() + 19), QPointF(ux + uw * left, line.top() + 19))
        p.setOpacity(base)

        # flow wave: your last hour as liquid; it ripples while you work and goes still, moonlit, when you're dark
        y = y0 + self.row(p, 2)
        wave = QRectF(x, y + 108, W, 38)
        self.buttons["flow"] = wave
        self.flow_wave(p, wave, col, now)

        # footer: "more" stays put on the trailing edge and slides the row between the main and the rarer actions
        y = y0 + self.row(p, 3)
        fy, base, m = y + 158, p.opacity(), max(0.0, min(1.0, self.more_s.x))
        self.icon_button(p, "more", QPointF(x + W - 18, fy + 19), col, now)
        on_more = m >= 0.5
        rows = [(self.footer_main, 1 - m, -16 * m, not on_more), (self.footer_more, m, 16 * (1 - m), on_more)]
        for draw, a, dx, active in sorted(rows, key=lambda r: r[3]):  # the row you're on is drawn last
            if a > 0.01:
                kept = dict(self.buttons)
                p.setOpacity(base * a)
                draw(p, x + (0 if self.calm else dx), fy, W, col, now)
                if not active:  # only the row you're on is clickable
                    self.buttons = kept
        p.setOpacity(base)

    def footer_main(self, p, x, fy, W, col, now):
        L, cy = self.live, fy + 19
        accent = col if col.lightness() > 60 else QColor("#7AA2FF")
        # today: a small activity ring filling towards your daily goal, then the time
        prog = min(1.0, L.get("today_s", 0) / self.goal) if self.goal else 0
        t_txt, nf, lf = fmt(L.get("today_s", 0)), font(14, QFont.Bold, NUM), font(12, QFont.Medium)
        tw, lw = QFontMetricsF(nf).horizontalAdvance(t_txt), QFontMetricsF(lf).horizontalAdvance("today")
        g = QRectF(x - 8, fy + 2, 40 + tw + lw, 34)
        self.buttons["today"] = g
        self.wash(p, g, self.hv("today"))
        rc = QPointF(x + 9, cy)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 34), 2.6))
        p.drawEllipse(rc, 7.5, 7.5)
        if prog > 0:
            p.setPen(QPen(accent, 2.6, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(rc.x() - 7.5, rc.y() - 7.5, 15, 15), 90 * 16, -round(prog * 360 * 16))
        p.setFont(nf)
        p.setPen(TXT)
        p.drawText(QRectF(x + 26, fy, tw + 4, 38), Qt.AlignLeft | Qt.AlignVCenter, t_txt)
        p.setFont(lf)
        p.setPen(DIM)
        p.drawText(QRectF(x + 30 + tw, fy + 1, lw + 4, 38), Qt.AlignLeft | Qt.AlignVCenter, "today")
        # to review: the one stat that asks for attention wears the theme colour, and only while it does
        pending = L.get("pending", 0)
        text = f"{pending} to review" if pending else "all reviewed"
        rf = font(13.5, QFont.Bold if pending else QFont.Medium)
        rw = QFontMetricsF(rf).horizontalAdvance(text)
        rg = QRectF(g.right() + 8, fy + 2, (14 if pending else 0) + rw + 16, 34)
        self.buttons["review"] = rg
        self.wash(p, rg, self.hv("review"))
        tx = rg.left() + 8
        if pending:
            glow = 0.5 if self.calm else (math.sin(now * 2.4) + 1) / 2
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), int(40 + 50 * glow)))
            p.drawEllipse(QPointF(tx + 4, cy), 6, 6)
            p.setBrush(accent)
            p.drawEllipse(QPointF(tx + 4, cy), 3.5, 3.5)
            tx += 14
        p.setFont(rf)
        p.setPen(TXT if pending else DIM)
        p.drawText(QRectF(tx, fy, rw + 4, 38), Qt.AlignLeft | Qt.AlignVCenter, text)
        self.icon_button(p, "dark", QPointF(x + W - 106, cy), col, now)
        self.icon_button(p, "open", QPointF(x + W - 62, cy), col, now, primary=True)

    def footer_more(self, p, x, fy, W, col, now):
        """The rarer actions. These get labels: there's room, and they're used too seldom to remember by icon."""
        items = (("personal", "not work"), ("pin", "unpin" if self.pinned else "pin"), ("gear", "settings"))
        f = font(13, QFont.Bold)
        widths = [QFontMetricsF(f).horizontalAdvance(lab) + 50 for _, lab in items]
        bx = x + W - 46 - sum(widths) - 8 * (len(items) - 1)
        base = p.opacity()
        for (key, lab), w in zip(items, widths):
            r = QRectF(bx, fy + 1, w, 36)
            bx += w + 8
            self.buttons[key] = r
            off = key in self.disabled
            h, pr = (0.0, 1.0) if off else (self.hv(key), self.pv(key))
            r2 = QRectF(r.center().x() - w * pr / 2, r.center().y() - 18 * pr, w * pr, 36 * pr)
            p.setOpacity(base * (0.38 if off else 1))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, int(14 + 22 * h)))
            p.drawRoundedRect(r2, r2.height() / 2, r2.height() / 2)
            self.glyph(p, key, QPointF(r2.left() + 20, r2.center().y()), col, now, h)
            p.setPen(TXT)
            p.setFont(f)
            p.drawText(r2.adjusted(36, 0, -8, 0), Qt.AlignLeft | Qt.AlignVCenter, lab)
            p.setOpacity(base)

    def wash(self, p, r, h):
        """The hover affordance for text you can click: a soft plate that fades in under the cursor."""
        if h > 0.01:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, int(16 * h)))
            p.drawRoundedRect(r, 12, 12)

    def icon_button(self, p, key, c, col, now, primary=False):
        """Round, 36 px, no label and almost no chrome: a faint disc that brightens on hover, a squish while
        held, and an icon that reacts. The primary one is filled with the theme colour."""
        off = key in self.disabled
        h, pr = (0.0, 1.0) if off else (self.hv(key), self.pv(key))
        self.buttons[key] = QRectF(c.x() - 18, c.y() - 18, 36, 36)
        r, base = 18 * pr, p.opacity()
        p.setOpacity(base * (0.38 if off else 1))
        p.setPen(Qt.NoPen)
        if primary:
            accent = col if col.lightness() > 60 else QColor("#7AA2FF")
            for g in range(3, 0, -1):  # a soft shadow that deepens on hover
                p.setBrush(QColor(0, 0, 0, int((16 + 20 * h) / g)))
                p.drawEllipse(c + QPointF(0, g * 0.8 + h), r + g * 0.6, r + g * 0.6)
            fill = QRadialGradient(c + QPointF(-r * 0.3, -r * 0.45), r * 1.7)
            fill.setColorAt(0, accent.lighter(round(118 + 10 * h)))
            fill.setColorAt(1, accent.darker(110))
            p.setBrush(fill)
        else:
            p.setBrush(QColor(255, 255, 255, int(14 + 24 * h)))
        p.drawEllipse(c, r, r)
        self.glyph(p, key, c, col, now, h)
        p.setOpacity(base)

    def glyph(self, p, key, c, col, now, h):
        """Each control's icon, and the small thing it does when you hover it."""
        tint, base = mix(jelly.PORCELAIN, col, 0.85 * h), p.opacity()
        p.save()
        if key == "dark":  # moon turns into sun: crossfade with a quarter turn
            d = max(0.0, min(1.0, self.dark.x))
            p.translate(c)
            p.save()
            p.setOpacity(base * (1 - d))
            p.rotate(-16 * h - 90 * d)
            jelly.moon(p, QPointF(0, 0), 11, now, tint)
            p.restore()
            p.setOpacity(base * d)
            p.rotate(90 * (1 - d))
            jelly.sun(p, QPointF(0, 0), 11 * (1 + 0.1 * h), 0 if self.calm else now * 0.4, tint)
        elif key == "personal":  # tilts like it's being picked up
            p.translate(c)
            p.rotate(-12 * h)
            jelly.gamepad(p, QPointF(0, 0), 10.5, now, tint)
        elif key == "pin":  # leans over when loose, stands up when it's holding the island out
            k = max(0.0, min(1.0, self.pin_s.x))
            jelly.pin(p, c, 9.5, mix(jelly.PORCELAIN, col, max(k, 0.85 * h)), 40 * (1 - self.pin_s.x) - 10 * h)
        elif key == "gear":  # turns a notch
            jelly.gear(p, c, 9, tint, 30 * h)
        elif key == "open":  # an arrow on the filled disc, leaning towards where it takes you
            n = 1.6 * h
            jelly.stroke(p, jelly.INK if col.lightness() > 140 or col.lightness() <= 60 else TXT, 2.3)
            o = c + QPointF(n, -n)
            p.drawLine(o + QPointF(-4.5, 4.5), o + QPointF(4.2, -4.2))
            p.drawPolyline([o + QPointF(-1.8, -4.8), o + QPointF(4.8, -4.8), o + QPointF(4.8, 1.8)])
        elif key == "more":  # three dots that turn into a close cross
            m = max(0.0, min(1.0, self.more_s.x))
            p.setPen(Qt.NoPen)
            p.setBrush(tint)
            p.setOpacity(base * (1 - m))
            for i in (-1, 0, 1):
                p.drawEllipse(c + QPointF(i * (5.5 + h), 0), 2.1, 2.1)
            p.setOpacity(base * m)
            p.translate(c)
            p.rotate(90 * (1 - m))
            jelly.stroke(p, tint, 2.2)
            p.drawLine(QPointF(-4.5, -4.5), QPointF(4.5, 4.5))
            p.drawLine(QPointF(-4.5, 4.5), QPointF(4.5, -4.5))
        p.restore()

    def flow_stats(self, now):
        """Active minutes in the last hour, and how long the current streak has run."""
        mins, m0 = self.live.get("minutes", {}), int(now // 60)
        vals = [min(1.0, mins.get(m0 - 59 + i, 0) / 60) for i in range(60)]
        streak = 0
        for v in reversed(vals):
            if v < 0.4:
                break
            streak += 1
        return vals, sum(v >= 0.4 for v in vals), streak

    def flow_wave(self, p, rect, col, now):
        vals, active_min, streak = self.flow_stats(now)
        smooth = [sum(vals[max(0, i - 2):i + 3]) / len(vals[max(0, i - 2):i + 3]) for i in range(60)]
        paused = self.live.get("paused")
        live = not paused and self.live.get("idle", 0) < 300
        if self.calm:
            now = 0  # still water
        accent = NIGHT if paused else col
        top, bottom = rect.top() + 6, rect.bottom() - 4
        amp = 0.0 if not live else 1.0
        pts = []
        for i, v in enumerate(smooth):
            x = rect.left() + rect.width() * i / 59
            level = v * (0.25 if paused else 1.0)                       # moonlit water lies low and calm
            ripple = (1.6 * amp + (0.6 if paused else 0)) * math.sin(now * (2.2 if live else 0.8) + i * 0.38)
            pts.append(QPointF(x, bottom - (bottom - top) * level + ripple * (0.4 + level)))
        line = QPainterPath(pts[0])
        for a, b2 in zip(pts, pts[1:]):                                  # midpoint smoothing: a liquid curve
            mid = QPointF((a.x() + b2.x()) / 2, (a.y() + b2.y()) / 2)
            line.quadTo(a, mid)
        line.lineTo(pts[-1])
        area = QPainterPath(line)
        area.lineTo(rect.right(), rect.bottom())
        area.lineTo(rect.left(), rect.bottom())
        area.closeSubpath()
        fill = QLinearGradient(0, top, 0, rect.bottom())
        fill.setColorAt(0, QColor(accent.red(), accent.green(), accent.blue(), 95))
        fill.setColorAt(1, QColor(accent.red(), accent.green(), accent.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(area)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 55), 6, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(line)                                                  # soft glow under the line
        p.setPen(QPen(accent, 2, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(line)
        if paused:  # starlight glinting on still water
            p.setPen(Qt.NoPen)
            for i in range(7):
                tw = (math.sin(now * 2 + i * 1.9) + 1) / 2
                gx = rect.left() + rect.width() * ((i * 0.618 + 0.1) % 1)
                p.setBrush(QColor(255, 255, 255, int(40 + 150 * tw)))
                p.drawEllipse(QPointF(gx, bottom - 2 + (i % 3)), 0.8 + 0.8 * tw, 0.8 + 0.8 * tw)
        # the "now" dot: pulses only while you're active
        nowp = pts[-1]
        if live and not self.calm:
            age = (now % 2.0) / 2.0
            ring = QColor(accent.red(), accent.green(), accent.blue(), int(130 * (1 - age)))
            p.setPen(QPen(ring, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(nowp, 4 + 9 * age, 4 + 9 * age)
        dot = QPainterPath()
        dot.addEllipse(nowp, 4.5, 4.5)
        jelly.jelly(p, dot, accent if live or paused else QColor("#8a8a94"), shadow=False)
        f = font(9.5, QFont.Medium, NUM)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 140))  # quiet but still readable
        p.drawText(QRectF(rect.left(), rect.top() - 4, 80, 12), Qt.AlignLeft | Qt.AlignVCenter, "60m ago")

    def info_line(self, p, view, src, text, ink, icon, x, top, W, col, now, t0=None):
        """The line that explains things. It fades and slides in when what it shows changes, then types itself
        out (captions at 90 chars/s, a new task at 80 from when it arrived). Returns the text rect and font."""
        st = self.lines.setdefault(view, [None, 0.0])
        if src != st[0]:
            st[:] = src, now
        age = now - st[1]
        ease_in = 1 - (1 - min(1.0, age / 0.22)) ** 3          # fade + slide in over 220 ms
        if self.calm:
            pass                                               # reduced motion: a plain fade, no typing
        elif icon:
            text = text[: int(age * 90)]
        elif t0 is not None:
            text = text[: int((now - t0) * 80)]
        p.setOpacity(p.opacity() * ease_in)
        tx = x + (0 if self.calm else (1 - ease_in) * 10)
        bright = col if col.lightness() > 60 else QColor("#7AA2FF")
        if icon == "info":
            jelly.info(p, QPointF(tx + 8, top + 9), 8, bright)
        elif icon == "check":  # a saved change: the tick draws itself in once
            jelly.check(p, QPointF(tx + 8, top + 9), 8.5, age, bright, not self.calm)
        elif icon == "bubble":
            jelly.bubble(p, QPointF(tx + 9, top + 8), 8.5, jelly.PORCELAIN)
        elif icon == "ring":
            self.mini_ring(p, QPointF(tx + 8, top + 9), 6.5, *self.ring)
        p.setPen(ink)
        f = font(13.5, QFont.Medium)
        p.setFont(f)
        line = QRectF(tx + (24 if icon else 0), top, W - (24 if icon else 0), 38)
        p.drawText(line, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, text)
        return line, f

    # ---------- intentions: the island speaks up, rarely ----------
    def watch_prompt(self, now):
        """A prompt that nobody answers retracts on its own (an ignored nudge counts as "later"), so the island
        never sits there nagging. The creature reacts when one appears: curious on a nudge, happy on a finish."""
        pr = (self.live.get("focus") or {}).get("prompt")
        if not pr:
            self.prompt_at = None
            return
        if pr["at"] != self.prompt_at:
            self.prompt_at = pr["at"]
            self.mascot.react({"nudge": "curious", "ask": "surprised", "done": "party"}.get(pr["kind"], "surprised"), 2.5)
        if not self.frameGeometry().contains(QCursor.pos()):
            if now - pr["at"] > {"nudge": 30, "ask": 90, "next": 25, "done": 8}.get(pr["kind"], 30):
                focus.respond("later" if pr["kind"] == "nudge" else "dismiss", now=now)

    def draw_prompt(self, p, b, now):
        """Three lines at most, and the answer is always one tap: a nudge when you've drifted, "how far did you
        get?" when you've moved on, and what's next when something wraps up."""
        pr = (self.live.get("focus") or {}).get("prompt") or self.last_prompt  # keep the words while it fades out
        if not pr:
            return
        self.last_prompt = pr
        it, kind = pr.get("item") or {}, pr["kind"]
        col = QColor(it.get("color") or "#9a9aa6")
        col = col if col.lightness() > 60 else QColor("#7AA2FF")
        x, y0, W = b.left() + 20, b.top(), b.width() - 40
        text, what = it.get("text", ""), pr.get("what")
        title, sub = {
            "nudge": (f"{pr.get('min', 0)} min on {what or 'something else'}", f"back to {text}?"),
            "ask": ("how far did you get?", f"{text} · you've moved on to {what}" if what else f"{text} · it keeps its place in line"),
            "next": (f"next up: {text}", it.get("reason", "") + (f" · nice, that took {focus.span(pr.get('spent', 0))}"
                                                                 if pr.get("done") else "")),
            "done": (f"done · {text}", f"{focus.span(pr.get('spent', 0))} on it. nothing else in line"),
        }[kind]
        y = y0 + self.row(p, 0, "prompt")
        c = QPointF(x + 18, y + 36)
        look = QPointF(c.x() + 30, c.y() + 140) if kind == "nudge" else None  # on a nudge it looks down at your screen
        self.mascot.draw(p, c, 18, now, look)
        p.setPen(TXT)
        p.setFont(font(15.5, QFont.ExtraBold))
        p.drawText(QRectF(x + 46, y + 16, W - 46, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(p.font()).elidedText(title, Qt.ElideRight, W - 46))
        p.setPen(DIM)
        p.setFont(font(13, QFont.Medium))
        p.drawText(QRectF(x + 46, y + 38, W - 46, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(p.font()).elidedText(sub, Qt.ElideRight, W - 46))
        y = y0 + self.row(p, 1, "prompt")
        acts = {"nudge": [("switch", "switch"), ("later", "later"), ("back", "back on it")],
                "ask": [("10", "just started"), ("50", "halfway"), ("80", "almost"), ("100", "done")],
                "next": [("later", "later"), ("start", "start it")],
                "done": [("ok", "nice")]}[kind]
        n, base = len(acts), p.opacity()
        bw = (W - 8 * (n - 1)) / n
        for i, (a, label) in enumerate(acts):
            key, primary = "p:" + a, i == n - 1
            r = QRectF(x + i * (bw + 8), y + 72, bw, 36)
            self.buttons[key] = r
            h, pr_ = self.hv(key), self.pv(key)
            r2 = QRectF(r.center().x() - bw * pr_ / 2, r.center().y() - 18 * pr_ - 1.5 * h, bw * pr_, 36 * pr_)
            p.setPen(Qt.NoPen)
            if primary:  # the answer it expects is filled with the intention's colour
                fill = QLinearGradient(0, r2.top(), 0, r2.bottom())
                fill.setColorAt(0, col.lighter(round(112 + 10 * h)))
                fill.setColorAt(1, col.darker(108))
                p.setBrush(fill)
                ink = jelly.INK if col.lightness() > 140 else TXT
            else:
                p.setBrush(QColor(255, 255, 255, int(16 + 24 * h)))
                ink = TXT
            p.drawRoundedRect(r2, r2.height() / 2, r2.height() / 2)
            p.setPen(ink)
            p.setFont(font(13.5 if n < 4 else 12.5, QFont.Bold))
            p.drawText(r2, Qt.AlignCenter, label)
        p.setOpacity(base)

    def focus_ring(self, fz):
        col = QColor(fz.get("color") or "#9a9aa6")
        est = fz.get("est_min")
        return (min(1.0, fz["spent_s"] / 60 / est) if est else 0.0), (col if col.lightness() > 60 else QColor("#7AA2FF"))

    def mini_ring(self, p, c, r, frac, col):
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 46), 2.4))
        p.drawEllipse(c, r, r)
        if frac > 0:
            p.setPen(QPen(col, 2.4, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), 90 * 16, -round(frac * 360 * 16))

    # ---------- settings, inside the island ----------
    def draw_settings(self, p, b, now):
        """Same 400 px column as the open card: header 18-46, info 54-72, then three rows of segmented
        controls at 86, 132 and 178. The content slides in from the right, like a page being pushed."""
        col = self.color()
        a = max(0.0, min(1.0, self.fade["settings"].x))
        x, y0, W = b.left() + 20 + (0 if self.calm else (1 - a) * 16), b.top(), b.width() - 40

        y = y0 + self.row(p, 0, "settings")
        h = self.hv("back")
        back_ = QRectF(x, y + 18, 28, 28)
        self.buttons["back"] = back_
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, int(14 + 22 * h)))
        p.drawEllipse(back_)
        c = back_.center() + QPointF(-0.5 - 1.8 * h, 0)  # the chevron leans the way it takes you
        jelly.stroke(p, mix(jelly.PORCELAIN, col, 0.85 * h), 2.2)
        p.drawPolyline([QPointF(c.x() + 2.5, c.y() - 5.5), QPointF(c.x() - 3, c.y()), QPointF(c.x() + 2.5, c.y() + 5.5)])
        p.setPen(TXT)
        p.setFont(font(17, QFont.ExtraBold))
        p.drawText(QRectF(x + 40, y + 18, W - 40, 28), Qt.AlignLeft | Qt.AlignVCenter, "island settings")
        h = self.hv("quit")  # the way out lives here, quietly, like a menu bar app's "Quit"
        qf = font(12.5, QFont.DemiBold)
        quit_ = QRectF(0, y + 20, QFontMetricsF(qf).horizontalAdvance("quit lowkey") + 24, 24)
        quit_.moveRight(x + W)
        self.buttons["quit"] = quit_
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, int(10 + 22 * h)))
        p.drawRoundedRect(quit_, 12, 12)
        p.setPen(mix(QColor(150, 150, 158), TXT, h))
        p.setFont(qf)
        p.drawText(quit_, Qt.AlignCenter, "quit lowkey")

        # info line: a fresh "saved" beats the hovered option, which beats the hint
        y = y0 + self.row(p, 1, "settings")
        cap = self.caption()
        if now < self.notice_until:
            src, text, icon = "notice:" + self.notice, self.notice, "check"
        elif cap:
            src, text, icon = "cap:" + self.cap_key, cap, "info"
        else:
            src, text, icon = "hint", "hover an option to preview it. click to apply", "info"
        base = p.opacity()
        self.info_line(p, "settings", src, text, QColor(236, 238, 245), icon, x, y + 54, W, col, now)
        p.setOpacity(base)

        for i, (k, label, opts) in enumerate(SETTINGS_UI):
            y = y0 + self.row(p, 2 + i, "settings")
            top = y + 86 + i * 46
            p.setPen(QColor(160, 160, 168))
            p.setFont(font(12.5, QFont.Medium))
            p.drawText(QRectF(x, top, 76, 34), Qt.AlignLeft | Qt.AlignVCenter, label)
            self.segmented(p, QRectF(x + 80, top, W - 80, 34), k, opts, col)
            p.setOpacity(base)

    def segmented(self, p, r, k, opts, col):
        """A segmented control: a glass thumb slides on a spring to the chosen option, and each label
        brightens as the thumb arrives under it."""
        cur, n, base = self.live["settings"].get(k), len(opts), p.opacity()
        sw = r.width() / n
        pick = next((j for j, o in enumerate(opts) if o[0] == cur), 0)
        thumb = self.thumbs.get(k)
        if thumb is None:
            thumb = self.thumbs[k] = Spring(pick, 300, 28)  # first sight: already in place
        thumb.target = pick
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 13))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        t = QRectF(r.left() + 3 + thumb.x * sw, r.top() + 3, sw - 6, r.height() - 6)
        rad = t.height() / 2
        for g in range(3, 0, -1):
            p.setBrush(QColor(0, 0, 0, 22 // g))
            p.drawRoundedRect(t.adjusted(-g * 0.6, g * 0.5, g * 0.6, g * 1.1), rad + g, rad + g)
        glass = QLinearGradient(0, t.top(), 0, t.bottom())
        glass.setColorAt(0, QColor(255, 255, 255, 52))
        glass.setColorAt(1, QColor(255, 255, 255, 30))
        rim = QLinearGradient(0, t.top(), 0, t.bottom())
        rim.setColorAt(0, QColor(255, 255, 255, 90))
        rim.setColorAt(1, QColor(255, 255, 255, 14))
        p.setPen(QPen(QBrush(rim), 1))
        p.setBrush(glass)
        p.drawRoundedRect(t.adjusted(0.5, 0.5, -0.5, -0.5), rad, rad)
        for j, (v, label, *_) in enumerate(opts):
            key = f"set:{k}:{v}"
            seg = QRectF(r.left() + j * sw, r.top(), sw, r.height())
            self.buttons[key] = seg
            off = key in self.disabled
            h = 0.0 if off else self.hv(key)
            near = max(0.0, 1 - abs(thumb.x - j))  # 1 when the thumb sits here
            if h > 0.01 and near < 0.99:  # a faint wash under the cursor, never on the chosen one
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, int(12 * h * (1 - near))))
                p.drawRoundedRect(seg.adjusted(3, 3, -3, -3), rad, rad)
            p.setOpacity(base * (0.38 if off else 1))
            ink = mix(QColor(150, 150, 158), TXT, max(near, 0.75 * h))
            p.setFont(font(13, QFont.Bold if near > 0.5 else QFont.DemiBold))
            tw_ = QFontMetricsF(p.font()).horizontalAdvance(label)
            gx = seg.center().x() - (tw_ + (20 if k == "edge" else 0)) / 2
            if k == "edge":  # a tiny screen with the island on that edge
                self.edge_glyph(p, QPointF(gx + 7, seg.center().y()), v, ink, mix(ink, col, near))
                gx += 20
            pr = self.pv(key)
            p.save()
            p.translate(seg.center())
            p.scale(pr, pr)  # squish while held
            p.translate(-seg.center())
            p.setPen(ink)
            p.drawText(QRectF(gx, seg.top(), tw_ + 4, seg.height()), Qt.AlignLeft | Qt.AlignVCenter, label)
            p.restore()
            p.setOpacity(base)

    def edge_glyph(self, p, c, edge, ink, accent):
        scr = QRectF(c.x() - 7, c.y() - 5, 14, 10)
        p.setPen(QPen(ink, 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(scr, 2.5, 2.5)
        bar = {"top": QRectF(c.x() - 3, scr.top() + 1.6, 6, 2), "bottom": QRectF(c.x() - 3, scr.bottom() - 3.6, 6, 2),
               "left": QRectF(scr.left() + 1.6, c.y() - 2.5, 2, 5), "right": QRectF(scr.right() - 3.6, c.y() - 2.5, 2, 5)}[edge]
        p.setPen(Qt.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(bar, 1, 1)

    # ---------- the hover preview ----------
    def place_peek(self, now, dt, moving):
        """Show the preview while an option is hovered (with the same hover intent as captions), and glide
        it along the island from option to option instead of closing and reopening."""
        key = self.cap_key if (self.mode == "settings" and not moving and (self.cap_key or "").startswith("set:")) else None
        if key and key != self.peek_key:
            self.peek_key, self.peek_t0 = key, now
        self.peek.target = 1.0 if key else 0.0
        self.peek.step(dt)
        seg = self.buttons.get(self.peek_key)
        if (self.peek.x < 0.01 and not key) or seg is None:
            self.peek_along = None
            if self.peek_win.isVisible():
                self.peek_win.hide()
            return
        g, body = self.mapToGlobal(seg.center()), self.body()
        tl, br = self.mapToGlobal(body.topLeft()), self.mapToGlobal(body.bottomRight())
        scr = self.screen().availableGeometry()
        ww, wh, side = PEEK_W + 2 * PEEK_M, PEEK_H + 2 * PEEK_M, self.edge in ("top", "bottom")
        along = g.x() if side else g.y()
        if self.peek_along is None:
            self.peek_along = Spring(along, 260, 26)
        self.peek_along.target = along
        self.peek_along.step(dt)
        a, gap = self.peek_along.x, 8 - PEEK_M + NUB
        if side:
            x = max(scr.left() + 4, min(scr.right() - 4 - ww, a - ww / 2))
            y = br.y() + gap if self.edge == "top" else tl.y() - gap - wh
            self.nub = a - x
        else:
            y = max(scr.top() + 4, min(scr.bottom() - 4 - wh, a - wh / 2))
            x = br.x() + gap if self.edge == "left" else tl.x() - gap - ww
            self.nub = a - y
        self.peek_win.setGeometry(round(x), round(y), ww, wh)
        if not self.peek_win.isVisible():
            self.peek_win.show()
        self.peek_win.update()

    def draw_peek(self, p, now):
        """A small card with an arrow at the option: a tiny screen acting the option out, and its name."""
        if not self.peek_key:
            return
        a = max(0.0, min(1.0, self.peek.x))
        _, k, v = self.peek_key.split(":")
        M, e = PEEK_M, self.edge
        card = QRectF(M, M, PEEK_W, PEEK_H)
        n = max(M + 22, min(M + (PEEK_W if e in ("top", "bottom") else PEEK_H) - 22, self.nub))
        tip, s1, s2 = {"top": ((n, M - NUB), (n - 9, M + 1), (n + 9, M + 1)),
                       "bottom": ((n, M + PEEK_H + NUB), (n - 9, M + PEEK_H - 1), (n + 9, M + PEEK_H - 1)),
                       "left": ((M - NUB, n), (M + 1, n - 9), (M + 1, n + 9)),
                       "right": ((M + PEEK_W + NUB, n), (M + PEEK_W - 1, n - 9), (M + PEEK_W - 1, n + 9))}[e]
        tip = QPointF(*tip)
        sc = 1.0 if self.calm else 0.9 + 0.1 * a  # grows out of its arrow
        p.translate(tip)
        p.scale(sc, sc)
        p.translate(-tip)
        p.setOpacity(a)
        p.setPen(Qt.NoPen)
        for i in range(6, 0, -1):
            p.setBrush(QColor(0, 0, 0, 11))
            p.drawRoundedRect(card.adjusted(-i * 1.3, -i * 1.3 + 2, i * 1.3, i * 1.3 + 3), 16 + i, 16 + i)
        shape = QPainterPath()
        shape.addRoundedRect(card, 16, 16)
        arrow = QPainterPath(QPointF(*s1))
        arrow.lineTo(tip)
        arrow.lineTo(QPointF(*s2))
        arrow.closeSubpath()
        shape = shape.united(arrow)
        g = QLinearGradient(0, card.top(), 0, card.bottom())
        g.setColorAt(0, QColor(20, 20, 22))
        g.setColorAt(1, QColor(6, 6, 8))
        p.setBrush(g)
        p.drawPath(shape)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(shape)
        S = QRectF(card.left() + 10, card.top() + 10, PEEK_W - 20, (PEEK_W - 20) * 10 / 16)
        self.mini(p, S, k, v, now)
        f = font(9.5, QFont.Bold, NUM)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
        p.setFont(f)
        p.setPen(QColor(235, 235, 240, 210))
        lab = QRectF(S.left() + 2, S.bottom() + 8, S.width() - 4, 16)
        p.drawText(lab, Qt.AlignLeft | Qt.AlignVCenter, OPTION[k, v][2].upper())
        col = self.color() if self.color().lightness() > 60 else TXT
        tag, ink = (("NOT ON MACOS", DIM) if self.peek_key in self.disabled else
                    ("CURRENT", col) if self.live["settings"].get(k) == v else ("", DIM))
        if tag:
            p.setPen(ink)
            p.drawText(lab, Qt.AlignRight | Qt.AlignVCenter, tag)

    def mini_rect(self, S, edge, tb, over, size, depth=1.0):
        """Where the island sits on the tiny screen: the same rules as place(), at a toy scale."""
        w, h = S.width() * MINI[size][0], max(3.0, S.height() * MINI[size][1])
        if size == "lip" and edge in ("left", "right"):
            w, h = h, w
        if edge in ("top", "bottom"):
            h *= depth
        else:
            w *= depth
        off = 0 if over or tb != edge else S.height() * 0.09 if edge in ("top", "bottom") else S.width() * 0.065
        x = {"left": S.left() + off, "right": S.right() - off - w}.get(edge, S.center().x() - w / 2)
        y = {"top": S.top() + off, "bottom": S.bottom() - off - h}.get(edge, S.center().y() - h / 2)
        return QRectF(x, y, w, h)

    def mini(self, p, S, k, v, now):
        """Act the option out on a tiny screen, like a short looping clip: a new edge tucks into the old one and
        blooms out of the new; the taskbar choice glides it over or under; the resting choice shows a cursor
        coming by. A dashed outline marks exactly where it will end up. Holds still under reduced motion."""
        st, col = self.live["settings"], self.color()
        col = col if col.lightness() > 60 else QColor("#7AA2FF")
        edge, over, rest, tb = self.edge, st.get("taskbar") == "over", st.get("rest", "lip"), self.live.get("taskbar")
        if k == "taskbar":
            tb = edge  # that choice only matters where the two share an edge, so show them sharing one
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(S, 9, 9)
        p.setClipPath(clip, Qt.IntersectClip)
        wall = QLinearGradient(S.topLeft(), S.bottomRight())
        for pos, c in ((0, "#2b5876"), (0.65, "#7b4397"), (1, "#dc6a49")):  # the dashboard previews' wallpaper
            wall.setColorAt(pos, QColor(c))
        p.setPen(Qt.NoPen)
        p.setBrush(wall)
        p.drawRect(S)
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(QRectF(S.left() + S.width() * 0.2, S.top() + S.height() * 0.3, S.width() * 0.44, S.height() * 0.42), 4, 4)
        if tb in EDGES:
            t = S.height() * 0.09 if tb in ("top", "bottom") else S.width() * 0.065
            bar = {"top": QRectF(S.left(), S.top(), S.width(), t), "bottom": QRectF(S.left(), S.bottom() - t, S.width(), t),
                   "left": QRectF(S.left(), S.top(), t, S.height()), "right": QRectF(S.right() - t, S.top(), t, S.height())}[tb]
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(16, 16, 16, 236))
            p.drawRect(bar)
            p.setBrush(QColor(216, 216, 216, 190))
            for i in range(4):  # a few app icons
                c = (QPointF(bar.left() + 9 + i * 8, bar.center().y()) if tb in ("top", "bottom")
                     else QPointF(bar.center().x(), bar.top() + 9 + i * 8))
                p.drawEllipse(c, 1.7, 1.7)
        same, calm = st.get(k) == v, self.calm
        T = now - self.peek_t0
        if k == "edge":
            dst = self.mini_rect(S, v, tb, over, rest)
            if same or calm:
                self.mini_island(p, dst, v, rest, col, 1.0, now, here=same)
            else:
                T %= 3.2
                self.mini_ghost(p, dst, 1 - ease((T - 1.2) / 0.3))
                e, d = ((edge, 1.0) if T < 0.45 else (edge, 1 - ease((T - 0.45) / 0.35)) if T < 0.8
                        else (v, back((T - 0.8) / 0.6)))
                self.mini_island(p, self.mini_rect(S, e, tb, over, rest, d), e, rest, col,
                                 min(1.0, T / 0.2, (3.2 - T) / 0.3), now)
        elif k == "taskbar":
            dst = self.mini_rect(S, edge, tb, v == "over", rest)
            if same or calm:
                self.mini_island(p, dst, edge, rest, col, 1.0, now, here=same)
            else:
                T %= 3.0
                self.mini_ghost(p, dst, 1 - ease((T - 1.0) / 0.3))
                r = lerp_rect(self.mini_rect(S, edge, tb, over, rest), dst, 0 if T < 0.5 else back((T - 0.5) / 0.55))
                self.mini_island(p, r, edge, rest, col, min(1.0, T / 0.2, (3.0 - T) / 0.3), now)
        else:
            hover = "pill" if v == "lip" else "open"  # hovering grows it one step; it rests at your choice
            home, big = self.mini_rect(S, edge, tb, over, v), self.mini_rect(S, edge, tb, over, hover)
            if calm:
                self.mini_island(p, home, edge, v, col, 1.0, now, here=same)
            else:
                T %= 3.6
                cu = ease((T - 0.5) / 0.6) if T < 2.2 else 1 - ease((T - 2.2) / 0.6)  # the cursor comes and goes
                iu = back((T - 1.1) / 0.45) if T < 2.35 else 1 - ease((T - 2.35) / 0.4)
                self.mini_island(p, lerp_rect(home, big, iu), edge, hover if iu > 0.5 else v, col, 1.0, now)
                start = QPointF(S.left() + S.width() * 0.62, S.top() + S.height() * 0.66)
                self.mini_cursor(p, start + (big.center() - start) * cu, min(1.0, T / 0.3, (3.6 - T) / 0.3))
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(S.adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)

    def mini_island(self, p, r, edge, size, col, alpha, now, here=False):
        if r.width() < 0.5 or r.height() < 0.5 or alpha <= 0:
            return
        rad = min(8.0, min(r.width(), r.height()) / 2)
        ext = {"top": r.adjusted(0, -rad, 0, 0), "bottom": r.adjusted(0, 0, 0, rad),
               "left": r.adjusted(-rad, 0, 0, 0), "right": r.adjusted(0, 0, rad, 0)}[edge]
        shape, box = QPainterPath(), QPainterPath()
        shape.addRoundedRect(ext, rad, rad)
        box.addRect(r)
        shape = shape.intersected(box)  # flush with the screen edge, rounded on the inside
        p.save()
        p.setOpacity(p.opacity() * alpha)
        if here and not self.calm:  # "you are here": a slow ring
            u = (now % 1.8) / 1.8
            p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), int(170 * (1 - u))), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(-2 - 5 * u, -2 - 5 * u, 2 + 5 * u, 2 + 5 * u), rad + 3, rad + 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 10, 10))
        p.drawPath(shape)
        if size == "lip":  # the breathing glow line on the inner side
            c = QColor(col)
            c.setAlpha(int(255 * (0.6 + 0.4 * (math.sin(now * 2.2) + 1) / 2)))
            k = 1.2
            a, b = {"top": (QPointF(r.left() + 6, r.bottom() - k), QPointF(r.right() - 6, r.bottom() - k)),
                    "bottom": (QPointF(r.left() + 6, r.top() + k), QPointF(r.right() - 6, r.top() + k)),
                    "left": (QPointF(r.right() - k, r.top() + 6), QPointF(r.right() - k, r.bottom() - 6)),
                    "right": (QPointF(r.left() + k, r.top() + 6), QPointF(r.left() + k, r.bottom() - 6))}[edge]
            p.setPen(QPen(c, 1.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(a, b)
        elif r.height() > 6 and r.width() > 24:  # a creature dot and a line of text, at toy scale
            d = min(3.0, r.height() * 0.24)
            cy = r.top() + min(r.height() / 2, 6)
            p.setBrush(col)
            p.drawEllipse(QPointF(r.left() + 3 + d * 2, cy), d, d)
            p.setBrush(QColor(255, 255, 255, 200))
            p.drawRoundedRect(QRectF(r.left() + 6 + d * 4, cy - 1, r.width() * 0.5, 2), 1, 1)
            if size == "open" and r.height() > 20:
                p.setBrush(QColor(255, 255, 255, 70))
                for i in range(2):
                    p.drawRoundedRect(QRectF(r.left() + 6, r.top() + 14 + i * 7, r.width() * (0.8 - 0.25 * i), 2), 1, 1)
        p.restore()

    def mini_ghost(self, p, r, alpha):
        if alpha <= 0:
            return
        pen = QPen(QColor(255, 255, 255, int(170 * min(1.0, alpha))), 1, Qt.CustomDashLine)
        pen.setDashPattern([3, 2.5])
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        rad = min(6.0, min(r.width(), r.height()) / 2)
        p.drawRoundedRect(r.adjusted(-1.5, -1.5, 1.5, 1.5), rad + 1.5, rad + 1.5)

    def mini_cursor(self, p, at, alpha):
        arrow = QPainterPath(at)
        for dx, dy in ((0, 10.5), (2.8, 8), (4.8, 12.2), (6.5, 11.4), (4.6, 7.3), (7.8, 7.3)):
            arrow.lineTo(at + QPointF(dx, dy))
        arrow.closeSubpath()
        p.save()
        p.setOpacity(p.opacity() * max(0.0, alpha))
        p.setPen(QPen(QColor(10, 10, 10), 0.9))
        p.setBrush(QColor(255, 255, 255))
        p.drawPath(arrow)
        p.restore()

    def hv(self, key):
        """0..1 hover amount for a control, eased by a spring (a touch of overshoot, then it holds)."""
        return max(0.0, self.hov.setdefault(key, Spring(0, 300, 26)).x)

    def pv(self, key):
        """Press scale for a control: 0.95 while held, springs back past 1.0 on release."""
        return self.prs.setdefault(key, Spring(1, 520, 26)).x

    def caption(self):
        """What the hovered control does, shown in place of the task line."""
        L, key = self.live, self.cap_key
        if key == "personal" and key in self.disabled:
            return ("you're off the record, so there's nothing to move" if L.get("paused") else
                    "already a side quest" if L.get("client") == PERSONAL else "nothing to move yet: no session labelled")
        if key == "pin":
            return "unpin: tuck back into the edge" if self.pinned else "pin: keep the pill out instead of tucking it away"
        if key and key.startswith("set:"):
            _, k, v = key.split(":")
            tb = L.get("taskbar")
            if key in self.disabled:
                return "macOS keeps its menu bar on top, so it hangs below"
            if k == "taskbar" and tb != self.edge:
                return ("your taskbar is hidden, so this changes nothing" if tb not in EDGES
                        else f"only matters on the {tb} edge, where your taskbar is")
            return OPTION[k, v][3]
        if key == "dark":
            return "resume tracking from right now" if L.get("paused") else "pause tracking. nothing is saved until you resume"
        pct = round(100 * L.get("today_s", 0) / self.goal) if self.goal else 0
        if key == "flow":
            _, active_min, streak = self.flow_stats(time.time())
            tail = f", in flow for {streak}m" if streak >= 5 and not L.get("paused") else ""
            return f"last hour: {active_min} of 60 minutes active{tail}"
        return {"personal": "moves this session to side quests, off the invoice",
                "open": "open the dashboard: review, bill, see your week",
                "today": f"billable time today, {pct}% of your {self.goal // 3600}h goal",
                "money": "earned today at your rates. click to make the invoice",
                "review": "sessions waiting for bill it / nah. click to review",
                "mascot": "click me and i'll tell you something about your day",
                "gear": "island settings: where it lives and how it rests",
                "more": "back to the main controls" if self.more else "more: not work, pin and settings",
                "back": "back to your session",
                "quit": "quit lowkey: stops tracking and closes the island"}.get(key)

    def open_page(self, hash_=""):
        (self.actions.get("open") or (lambda h="": webbrowser.open("http://127.0.0.1:7777/" + h)))(hash_)

    # ---------- interaction ----------
    def hit(self, pos):
        return next((k for k, r in self.buttons.items() if r.contains(pos)), None)

    def clickable(self, key):
        return key and key != "flow" and key not in self.disabled

    def mouseMoveEvent(self, e):
        hot = self.hit(e.position())
        if hot != self.hot:
            self.hot, self.hot_t = hot, time.time()
            if hot:
                self.notice_until = 0.0
        self.setCursor(Qt.PointingHandCursor if self.clickable(hot) else Qt.ArrowCursor)  # the hand only promises what works

    def leaveEvent(self, e):
        self.hot, self.hot_t = None, time.time()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            key = self.hit(e.position())
            self.pressed = key if self.clickable(key) else None
            if not key:
                self.click_open = True

    def mouseReleaseEvent(self, e):
        key, self.pressed = self.pressed, None
        if key and key == self.hit(e.position()):
            if key == "dark":
                self.live["paused"] = not self.live.get("paused")
                self.toast("off the record. nothing is saved" if self.live["paused"] else "back on the clock",
                           NIGHT if self.live["paused"] else QColor(self.live.get("color") or "#B8FF3B"))
            elif key == "personal":  # acts at once and offers undo, instead of asking "are you sure?"
                self.undo = self.actions["personal"]()
                self.undo_until = time.time() + UNDO_S
                self.more = False
                self.toast("marked as a side quest", GREY)
            elif key == "undo" and self.undo:
                self.undo()
                self.undo, self.toast_until = None, 0.0
                self.mascot.react("surprised", 1.5)
            elif key == "pin":
                self.pinned, self.more = not self.pinned, False
                self.notice = "pinned: it stays out as a pill" if self.pinned else "unpinned: it tucks back in"
                self.notice_until = time.time() + 2.6
            elif key == "more":
                self.more = not self.more
            elif key == "gear":
                self.in_settings = self.click_open = True
                self.more = False
            elif key == "quit":
                self.quitting = time.time()
            elif key == "intend":
                self.open_page("#intend")
            elif key.startswith("p:"):  # an answer to the island's question
                a, pr = key[2:], (self.live.get("focus") or {}).get("prompt") or {}
                if a.isdigit():
                    if a == "100":  # finished: a flash of its colour and a happy creature
                        self.glow_c, self.glow_t0 = QColor((pr.get("item") or {}).get("color") or "#B8FF3B"), time.time()
                        self.mascot.react("party", 2.5)
                    focus.respond("progress", int(a))
                else:
                    focus.respond({"ok": "dismiss"}.get(a, a))
            elif key == "back":
                self.in_settings = False
            elif key.startswith("set:"):  # applies at once; if it moves the island, it waits open where it lands
                _, k, v = key.split(":")
                if self.live["settings"].get(k) != v:
                    update_settings({k: v})
                    self.notice, self.notice_until = f"saved · {OPTION[k, v][2]}", time.time() + 2.6
                    self.hold_until = time.time() + 3.5
                self.peek_t0 = time.time()
            elif key == "mascot":
                self.mascot.say()
                self.click_open = True
            elif key in ("open", "today"):
                self.open_page()
            elif key == "money":
                self.open_page("#bill")
            elif key == "review":
                self.open_page("#review")

    def mouseDoubleClickEvent(self, e):
        if not self.hit(e.position()):
            self.pinned = not self.pinned
            self.toast("pinned. double-click to tuck away" if self.pinned else f"tucked into the {self.edge} edge", GREY, 2)

    def run(self):
        signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C in the terminal ends lowkey (Qt's loop would swallow it)
        self.app.exec()

