"""The island: a notch that hides in a screen edge (top by default) and springs open on hover.

PySide6 + QPainter: anti-aliased, per-pixel transparent, never takes keyboard focus.
States: lip (tucked away) -> pill (hover) -> open (keep hovering or click), plus "toast" pop-outs.
Double-click pins the pill open.
"""
import ctypes, math, sys, time, webbrowser

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QFontMetricsF, QFontDatabase, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient, QTransform
from PySide6.QtWidgets import QApplication, QWidget

from . import jelly
from .mascot import Mascot

TXT, DIM, FAINT = QColor(245, 245, 245), QColor(150, 150, 150), QColor(255, 255, 255, 16)
GREY = QColor("#7a7a7a")
NIGHT, DUSK, AURORA = QColor("#9B8CFF"), QColor("#FF7AD9"), QColor("#4FD1C5")  # "off the record"


def mix(a, b, t):
    return QColor(*(round(x + (y - x) * t) for x, y in zip(a.getRgb()[:3], b.getRgb()[:3])))
SIZES = {"lip": (150, 8), "pill": (330, 42), "toast": (360, 48), "open": (440, 252)}
FONTS = Path(__file__).parent / "web" / "fonts"  # Bricolage Grotesque, Instrument Serif, Geist Mono (all OFL)
EAR, PAD = 10, 24  # concave ears where the notch meets the screen edge; room for the soft shadow


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
        self.fade = {m: Spring(0, 320, 34) for m in ("pill", "toast", "open")}
        self.dark = Spring(0, 90, 19)  # 0 = on the record, 1 = midnight
        self.mode, self.force, self.pinned, self.click_open = "lip", None, False, False
        self.hover_since = self.left_at = None
        self.toast_msg, self.toast_until, self.toast_color, self.toast_len = "", 0.0, GREY, 2.8
        self.seen_client, self.milestone = None, None
        self.task, self.task_t0 = "", 0.0
        self.mascot, self.quip = Mascot(live, self.goal, currency), None
        self.buttons, self.hot, self.pressed = {}, None, None
        self.edge, self.over, self.rest, self.raised_at = "top", False, "lip", 0.0
        self.hov, self.prs = {}, {}  # hover and press springs per control
        self.line_src, self.line_t0 = None, 0.0
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
        resting = "pill" if self.pinned or self.rest == "pill" else "lip"
        base = "toast" if now < self.toast_until else resting
        if self.frameGeometry().contains(QCursor.pos()):
            self.left_at = None
            self.hover_since = self.hover_since or now
            dwell = now - self.hover_since
            if self.click_open or dwell > 0.6:
                return "open"
            return "pill" if dwell > 0.12 else self.mode
        self.hover_since, self.click_open = None, False
        self.left_at = self.left_at or now
        return base if now - self.left_at > 0.35 else self.mode  # small grace so it doesn't flicker

    def tick(self):
        now = time.time()
        dt, self.last = min(0.033, now - self.last), now
        st = self.live.get("settings") or {}
        self.edge = st.get("edge", "top") if st.get("edge") in ("top", "bottom", "left", "right") else "top"
        self.over, self.rest = st.get("taskbar") == "over", st.get("rest", "lip")
        self.watch_events(now)
        self.quip = self.mascot.update(now)
        self.mode = self.pick_mode(now)
        tw, th = SIZES[self.mode]
        if self.mode == "lip" and self.edge in ("left", "right"):
            tw, th = th, tw  # a side lip stands upright
        self.W.target, self.H.target = tw, th
        for m, s in self.fade.items():
            s.target = 1.0 if m == self.mode else 0.0
        self.dark.target = 1.0 if self.live.get("paused") else 0.0
        self.money_view.target = float(self.live.get("money", 0))
        if self.last_money is not None and self.live.get("money", 0) > self.last_money + 0.5:
            self.coin_t0 = now  # the coin flips when you earn
        self.last_money = self.live.get("money", 0)
        self.money_view.step(dt)
        for k, sp in self.hov.items():
            sp.target = 1.0 if self.hot == k else 0.0
            sp.step(dt)
        for k, sp in self.prs.items():
            sp.target = 0.95 if self.pressed == k else 1.0  # squish while held, springs back on release
            sp.step(dt)
        for s in (self.W, self.H, self.dark, *self.fade.values()):
            s.step(dt)
        self.place()
        self.update()

    def place(self):
        """Attach to the chosen edge. By default the island hangs from the *work area*, so a taskbar on
        the same edge (or the macOS menu bar) pushes it inward instead of covering it. With taskbar="over"
        it sits on the physical screen edge and is re-raised above the taskbar on Windows."""
        scr = QGuiApplication.primaryScreen()
        full, work = scr.geometry(), scr.availableGeometry()
        side = ("top" if work.top() > full.top() else "bottom" if work.bottom() < full.bottom()
                else "left" if work.left() > full.left() else "right" if work.right() < full.right() else "none")
        self.live["taskbar"] = side
        edge, w, h = self.edge, self.W.x, max(1.0, self.H.x)
        over = self.over and side == edge
        a = full if over else work
        if edge in ("top", "bottom"):
            ww, wh = w + 2 * (EAR + PAD), h + PAD
            x = a.center().x() - ww / 2
            y = a.top() if edge == "top" else a.bottom() + 1 - wh
        else:
            ww, wh = w + PAD, h + 2 * (EAR + PAD)
            y = a.center().y() - wh / 2
            x = a.left() if edge == "left" else a.right() + 1 - ww
        self.setGeometry(round(x), round(y), round(ww), round(wh))
        if over and sys.platform == "win32" and time.time() - self.raised_at > 0.4:
            # the taskbar is also "always on top"; whoever was raised last wins, so keep winning
            ctypes.windll.user32.SetWindowPos(int(self.winId()), -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
            self.raised_at = time.time()

    def settle(self):
        """Jump straight to the target state (used for screenshots/tests)."""
        self.tick()
        self.mascot.snap()
        for s in (self.W, self.H, self.dark, *self.fade.values()):
            s.snap()
        self.place()

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
        lip = 1 - max(s.x for s in self.fade.values())
        if lip > 0.02:
            self.draw_lip(p, b, now, min(1, lip))
        self.buttons = {}
        for mode, draw in (("pill", self.draw_pill), ("toast", self.draw_toast), ("open", self.draw_open)):
            a = max(0.0, min(1.0, self.fade[mode].x))
            if a > 0.02:
                p.setOpacity(a)
                draw(p, b, now)
        p.end()

    def draw_night(self, p, b, now, a):
        """Off the record: a midnight wash, a slow aurora and twinkling stars inside the island."""
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(22, 14, 52, int(185 * a)))
        p.drawRect(b)
        for i, (col, speed, phase) in enumerate(((NIGHT, 0.23, 0.0), (DUSK, 0.17, 2.1), (AURORA, 0.13, 4.2))):
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
        L, col = self.live, self.color()
        cy = b.top() + 21
        self.avatar(p, QPointF(b.left() + 25, cy), 15, now)
        title, _ = self.status()
        p.setPen(TXT)
        p.setFont(font(14, QFont.Bold))
        name = QFontMetricsF(p.font()).elidedText(title, Qt.ElideRight, 140)
        p.drawText(QRectF(b.left() + 48, b.top(), 150, 42), Qt.AlignVCenter | Qt.AlignLeft, name)
        if L.get("client") and not L.get("paused") and L.get("idle", 0) < 300:  # tiny "now playing" bars
            ex = b.left() + 48 + QFontMetricsF(p.font()).horizontalAdvance(name) + 12
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            for i in range(4):
                hh = 4 + 9 * (math.sin(now * (5 + i * 1.7) + i) + 1) / 2
                p.drawRoundedRect(QRectF(ex + i * 5, cy - hh / 2, 3, hh), 1.5, 1.5)
        if L.get("client") and not L.get("paused"):
            p.setFont(font(13.5, QFont.Bold, NUM))
            p.setPen(col)
            p.drawText(QRectF(b.right() - 96, b.top(), 82, 42), Qt.AlignVCenter | Qt.AlignRight, f"{self.cur}{L.get('money', 0):,.0f}")
            p.setPen(DIM)
            p.setFont(font(12.5, QFont.Normal, NUM))
            p.drawText(QRectF(b.right() - 176, b.top(), 76, 42), Qt.AlignVCenter | Qt.AlignRight, clock(self.session_s(now)))

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
        if age < 0.9:  # one shimmer sweep when it pops out
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

    def row(self, p, k):
        """Stagger: row k fades/slides in a little after row k-1."""
        a = max(0.0, min(1.0, self.fade["open"].x))
        t = max(0.0, min(1.0, (a - k * 0.09) / (1 - k * 0.09)))
        p.setOpacity(t)
        return (1 - t) * 12

    def draw_open(self, p, b, now):
        L, col = self.live, self.color()
        x, y0 = b.left() + 20, b.top()
        y = y0 + self.row(p, 0)
        self.avatar(p, QPointF(x + 21, y + 34), 21, now)
        title, sub = self.status()
        p.setPen(TXT)
        p.setFont(font(23, QFont.Normal, SERIF, italic=True) if L.get("paused") else font(17, QFont.ExtraBold))
        p.drawText(QRectF(x + 54, y + 12, 250, 26), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(p.font()).elidedText(title, Qt.ElideRight, 250))
        p.setPen(DIM)
        p.setFont(font(12, QFont.Normal, NUM))
        p.drawText(QRectF(x + 54, y + 36, 250, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   f"this session  {clock(self.session_s(now))}" if L.get("client") and not L.get("paused") else "")

        # status badge
        paused = L.get("paused")
        label = "OFF RECORD" if paused else "BREAK" if L.get("idle", 0) > 300 else "LIVE"
        bf = font(10.5, QFont.Bold, NUM)
        bf.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        p.setFont(bf)
        bw = QFontMetricsF(p.font()).horizontalAdvance(label) + 34
        badge = QRectF(b.right() - 20 - bw, y + 20, bw, 24)
        p.setPen(Qt.NoPen)
        if paused:
            fill = QLinearGradient(badge.topLeft(), badge.topRight())
            fill.setColorAt(0, QColor(155, 140, 255, 70))
            fill.setColorAt(1, QColor(255, 122, 217, 70))
            p.setBrush(fill)
            p.drawRoundedRect(badge, 12, 12)
            jelly.moon(p, QPointF(badge.left() + 12, badge.center().y()), 7.5, now)
            p.setPen(TXT)
        else:
            p.setBrush(QColor(col.red(), col.green(), col.blue(), 40))
            p.drawRoundedRect(badge, 12, 12)
            p.setBrush(col)
            pulse = 3.5 + 1.2 * (math.sin(now * 5) + 1) / 2
            p.drawEllipse(QPointF(badge.left() + 13, badge.center().y()), pulse, pulse)
            p.setPen(col)
        p.drawText(badge.adjusted(22, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, label)

        # what the model thinks you're doing, typed in
        y = y0 + self.row(p, 1)
        talking = bool(self.quip)
        cap = None if (talking and self.hot == "mascot") else self.caption()  # its reply wins over the hint
        if cap:
            src, text, ink, icon = "cap:" + self.hot, cap, QColor(236, 238, 245), "info"
        elif talking:
            src, text, ink, icon = "quip:" + self.quip, self.quip, QColor(244, 244, 248), "bubble"
        else:
            src, text, ink, icon = "task", sub, QColor(214, 214, 220), None
        if src != self.line_src:
            self.line_src, self.line_t0 = src, now
        age = now - self.line_t0
        ease = 1 - (1 - min(1.0, age / 0.22)) ** 3          # fade + slide in over 220 ms
        if icon:
            text = text[: int(age * 90)]                    # captions and replies type themselves out
        elif sub == self.task:
            text = sub[: int((now - self.task_t0) * 80)]
        base = p.opacity()
        p.setOpacity(base * ease)
        tx = x + (1 - ease) * 10
        if icon == "info":
            jelly.info(p, QPointF(tx + 8, y + 71), 8, col if col.lightness() > 60 else QColor("#7AA2FF"))
        elif icon == "bubble":
            jelly.bubble(p, QPointF(tx + 9, y + 70), 8.5, jelly.PORCELAIN)
        p.setPen(ink)
        p.setFont(font(13.5, QFont.Medium))
        p.drawText(QRectF(tx + (24 if icon else 0), y + 62, b.width() - 40 - (24 if icon else 0), 40),
                   Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, text)
        p.setOpacity(base)

        # activity equaliser: last 30 minutes, one bar per minute
        y = y0 + self.row(p, 2)
        self.bars(p, QRectF(x, y + 108, b.width() - 40, 34), col, now)

        # stat chips: icon + value; lift on hover, "today" fills towards your goal, "to review" pulses
        y = y0 + self.row(p, 3)
        cx = x
        prog = min(1.0, L.get("today_s", 0) / self.goal) if self.goal else 0
        pending = L.get("pending", 0)
        for key, icon, text in (("today", "clock", fmt(L.get("today_s", 0))),
                                ("money", "coin", f"{max(0.0, self.money_view.x):,.0f}"),
                                ("review", "check", f"{pending} to review")):
            h = self.hv(key)
            chip_font = font(13, QFont.Bold)
            p.setFont(chip_font)
            w = QFontMetricsF(chip_font).horizontalAdvance(text) + 46
            self.buttons[key] = QRectF(cx, y + 148, w, 28)
            r = QRectF(cx, y + 148 - 2.5 * h, w, 28)
            pill = QPainterPath()
            pill.addRoundedRect(r, 14, 14)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, int(16 + 18 * h)))
            p.drawPath(pill)
            if key == "today" and prog > 0:
                fill = QLinearGradient(r.topLeft(), r.topRight())
                fill.setColorAt(0, QColor(col.red(), col.green(), col.blue(), 85))
                fill.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 25))
                p.save()
                p.setClipPath(pill, Qt.IntersectClip)
                p.setBrush(fill)
                p.drawRect(QRectF(r.left(), r.top(), r.width() * prog, r.height()))
                p.restore()
            edge = None
            if key == "review" and pending:
                edge = QColor(col.red(), col.green(), col.blue(), int(50 + 100 * (math.sin(now * 2.4) + 1) / 2))
            if h > 0.01:
                edge = QLinearGradient(r.topLeft(), r.bottomRight())
                edge.setColorAt(0, QColor(col.red(), col.green(), col.blue(), int(230 * h)))
                edge.setColorAt(1, QColor(255, 255, 255, int(70 * h)))
            if edge is not None:
                p.setPen(QPen(QBrush(edge), 1.3))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r.adjusted(0.7, 0.7, -0.7, -0.7), 13.3, 13.3)
            ic = QPointF(r.left() + 17, r.center().y())
            tint = mix(jelly.PORCELAIN, col, 0.85 * h)
            if icon == "clock":
                jelly.clock(p, ic, 9.5, now, tint)
            elif icon == "coin":
                jelly.coin(p, ic, 9.5, now, self.coin_t0, self.cur, tint)
            else:  # the one chip that asks for attention wears the theme colour
                jelly.check(p, ic, 9.5, now, col if pending else QColor("#6b6b78"), bool(pending))
            p.setFont(chip_font)  # the coin draws its own ₹, so set ours again
            p.setPen(QColor(238, 238, 238))
            p.drawText(r.adjusted(32, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
            cx += w + 8

        # buttons: lift on hover, the icon reacts once and holds, press squishes, state changes morph
        y = y0 + self.row(p, 4)
        bx = x
        d = max(0.0, min(1.0, self.dark.x))  # 0 = "go dark", 1 = "resume": the dark button morphs between them
        base = p.opacity()
        for key in ("dark", "personal", "open"):
            h, pr = self.hv(key), self.pv(key)
            f = font(13.5, QFont.Bold)
            p.setFont(f)
            fm = QFontMetricsF(f)
            if key == "dark":
                w = fm.horizontalAdvance("go dark") * (1 - d) + fm.horizontalAdvance("resume") * d + 58
            else:
                w = fm.horizontalAdvance("not work" if key == "personal" else "open lowkey") + 58
            accent = mix(QColor(255, 255, 255), col, h)          # neutral at rest, the theme colour on hover
            tint = mix(jelly.PORCELAIN, col, 0.85 * h)           # icons follow the same rule
            rect = QRectF(bx, y + 186, w, 38)
            self.buttons[key] = rect
            lift = 1.6 * h
            r2 = QRectF(rect.center().x() - w * pr / 2, rect.center().y() - 19 * pr - lift, w * pr, 38 * pr)
            rad = r2.height() / 2
            p.setPen(Qt.NoPen)
            for g in range(3, 0, -1):  # a soft shadow that deepens as the button rises
                p.setBrush(QColor(0, 0, 0, int((14 + 22 * h) / g)))
                p.drawRoundedRect(r2.adjusted(-g, g * 1.1 + lift * 0.7, g, g * 1.5 + lift), rad + g, rad + g)
            glass = QLinearGradient(0, r2.top(), 0, r2.bottom())
            glass.setColorAt(0, QColor(255, 255, 255, int(24 + 12 * h)))
            glass.setColorAt(1, QColor(255, 255, 255, int(6 + 6 * h)))
            edge = QLinearGradient(0, r2.top(), 0, r2.bottom())
            edge.setColorAt(0, QColor(accent.red(), accent.green(), accent.blue(), int(70 + 170 * h)))
            edge.setColorAt(1, QColor(accent.red(), accent.green(), accent.blue(), int(18 + 80 * h)))
            p.setPen(QPen(QBrush(edge), 1.25))
            p.setBrush(glass)
            p.drawRoundedRect(r2.adjusted(0.6, 0.6, -0.6, -0.6), rad - 0.6, rad - 0.6)
            p.setPen(QPen(QColor(255, 255, 255, int(28 + 30 * h)), 1))  # top sheen, like light on glass
            p.drawLine(QPointF(r2.left() + rad, r2.top() + 1.6), QPointF(r2.right() - rad, r2.top() + 1.6))

            ic = QPointF(r2.left() + 21, r2.center().y())
            if key == "dark":  # moon turns into sun: crossfade with a quarter turn
                p.save()
                p.setOpacity(base * (1 - d))
                p.translate(ic)
                p.rotate(-16 * h - 90 * d)
                p.translate(-ic.x(), -ic.y())
                jelly.moon(p, ic, 12.5, now, tint)
                p.restore()
                p.save()
                p.setOpacity(base * d)
                p.translate(ic)
                p.rotate(90 * (1 - d))
                p.translate(-ic.x(), -ic.y())
                jelly.sun(p, ic, 12.5 * (1 + 0.1 * h), now * 0.4, tint)
                p.restore()
            elif key == "personal":  # tilts like it's being picked up
                p.save()
                p.translate(ic)
                p.rotate(-12 * h)
                p.translate(-ic.x(), -ic.y())
                jelly.gamepad(p, ic, 12.5, now, tint)
                p.restore()
            else:  # the arrow slides towards where it will take you
                jelly.open_tile(p, ic, 12.5, now, tint, h)

            p.setFont(f)
            p.setPen(TXT)
            lab = QRectF(r2.left() + 41, r2.top(), r2.width() - 48, r2.height())
            if key == "dark":  # labels swap with a short vertical slide
                p.setOpacity(base * (1 - d))
                p.drawText(lab.translated(0, -7 * d), Qt.AlignVCenter | Qt.AlignLeft, "go dark")
                p.setOpacity(base * d)
                p.drawText(lab.translated(0, 7 * (1 - d)), Qt.AlignVCenter | Qt.AlignLeft, "resume")
                p.setOpacity(base)
            else:
                p.drawText(lab, Qt.AlignVCenter | Qt.AlignLeft, "not work" if key == "personal" else "open lowkey")
            bx += w + 10

    def bars(self, p, rect, col, now):
        mins, m0 = self.live.get("minutes", {}), int(now // 60)
        vals = [min(1.0, mins.get(m0 - 29 + i, 0) / 60) for i in range(30)]
        bw = rect.width() / 30
        paused = self.live.get("paused")
        active = not paused and self.live.get("idle", 0) < 300
        p.setPen(Qt.NoPen)
        for i, v in enumerate(vals):
            if paused:  # moonlit: low, still, breathing together
                hh = max(3.0, rect.height() * v * 0.42 * (0.82 + 0.18 * math.sin(now * 1.1 + i * 0.22)))
                col = DUSK if i % 7 == 3 else NIGHT
            else:
                wiggle = 1 + (0.18 * math.sin(now * 6 + i * 0.9) if active and v > 0 else 0)
                hh = max(3.0, rect.height() * v * 0.92 * wiggle)
            g = QLinearGradient(0, rect.bottom() - hh, 0, rect.bottom())
            top = QColor(col)
            bottom = QColor(col)
            bottom.setAlpha(70)
            g.setColorAt(0, top)
            g.setColorAt(1, bottom)
            p.setBrush(g if v > 0 else QBrush(FAINT))
            p.drawRoundedRect(QRectF(rect.left() + i * bw + 1.5, rect.bottom() - hh, bw - 3, hh), 2, 2)

    def hv(self, key):
        """0..1 hover amount for a control, eased by a spring (a touch of overshoot, then it holds)."""
        return max(0.0, self.hov.setdefault(key, Spring(0, 300, 26)).x)

    def pv(self, key):
        """Press scale for a control: 0.95 while held, springs back past 1.0 on release."""
        return self.prs.setdefault(key, Spring(1, 520, 26)).x

    def caption(self):
        """What the hovered control does, shown in place of the task line."""
        L, key = self.live, self.hot
        if key == "dark":
            return "resume tracking from right now" if L.get("paused") else "pause tracking. nothing is saved until you resume"
        pct = round(100 * L.get("today_s", 0) / self.goal) if self.goal else 0
        return {"personal": "not work? moves this session to side quests, off the invoice",
                "open": "open the dashboard: review sessions, send the bill, see your week",
                "today": f"billable time today, {pct}% of your {self.goal // 3600}h goal",
                "money": "earned today at your client rates. click to make the invoice",
                "review": "sessions waiting for bill it / nah. click to review them",
                "mascot": "click me and i'll tell you something about your day"}.get(key)

    def open_page(self, hash_=""):
        (self.actions.get("open") or (lambda h="": webbrowser.open("http://127.0.0.1:7777/" + h)))(hash_)

    # ---------- interaction ----------
    def hit(self, pos):
        return next((k for k, r in self.buttons.items() if r.contains(pos)), None)

    def mouseMoveEvent(self, e):
        self.hot = self.hit(e.position())
        self.setCursor(Qt.PointingHandCursor if self.hot else Qt.ArrowCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.pressed = self.hit(e.position())
            if not self.pressed:
                self.click_open = True

    def mouseReleaseEvent(self, e):
        key, self.pressed = self.pressed, None
        if key and key == self.hit(e.position()):
            if key == "dark":
                self.live["paused"] = not self.live.get("paused")
                self.toast("off the record. nothing is saved" if self.live["paused"] else "back on the clock",
                           NIGHT if self.live["paused"] else QColor(self.live.get("color") or "#B8FF3B"))
            elif key == "personal":
                self.actions["personal"]()
                self.toast("marked as a side quest", GREY)
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
            self.toast("pinned. double-click to tuck away" if self.pinned else "tucked into the top edge", GREY, 2)

    def run(self):
        self.app.exec()

