"""The island: a notch that hides in a screen edge (top by default) and springs open on hover.

PySide6 + QPainter: anti-aliased, per-pixel transparent, never takes keyboard focus.
States: lip (tucked away) -> pill (hover) -> open (keep hovering or click), plus "toast" pop-outs.
Double-click pins the pill open.
"""
import ctypes, math, sys, time, webbrowser

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QFontMetricsF, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QApplication, QWidget

TXT, DIM, FAINT = QColor(245, 245, 245), QColor(150, 150, 150), QColor(255, 255, 255, 16)
RED, GREY = QColor("#FF5A5A"), QColor("#7a7a7a")
SIZES = {"lip": (150, 8), "pill": (330, 42), "toast": (360, 48), "open": (440, 252)}
EAR, PAD = 10, 24  # concave ears where the notch meets the screen edge; room for the soft shadow


def fmt(s):
    m = int(s // 60)
    return f"{m}m" if m < 60 else f"{m // 60}h {m % 60:02d}m"


def clock(s):
    s = max(0, int(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


UI = ["Segoe UI Variable Display", "SF Pro Display", "Helvetica Neue", "Inter", "Ubuntu", "sans-serif"]
NUM = ["Bahnschrift", "SF Pro Rounded", "SF Pro Display", "Helvetica Neue", "DejaVu Sans", "sans-serif"]


def font(px, weight=QFont.Normal, families=UI):
    f = QFont()
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
        self.live, self.actions, self.cur, self.goal = live, actions, currency, goal_h * 3600
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)  # macOS hides tool windows when the app is inactive
        self.setMouseTracking(True)
        self.W, self.H = Spring(SIZES["lip"][0]), Spring(SIZES["lip"][1])
        self.fade = {m: Spring(0, 320, 34) for m in ("pill", "toast", "open")}
        self.mode, self.force, self.pinned, self.click_open = "lip", None, False, False
        self.hover_since = self.left_at = None
        self.toast_msg, self.toast_until, self.toast_color, self.toast_len = "", 0.0, GREY, 2.8
        self.seen_client, self.milestone = None, None
        self.task, self.task_t0 = "", 0.0
        self.buttons, self.hot, self.pressed = {}, None, None
        self.edge, self.over, self.rest, self.raised_at = "top", False, "lip", 0.0
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
            return RED
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
            self.seen_client = client
        step = int(L.get("money", 0) // 1000)
        if self.milestone is None:
            self.milestone = step
        elif step > self.milestone:
            self.milestone = step
            self.toast(f"{self.cur}{step * 1000:,} secured today", QColor("#B8FF3B"), 3.5)
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
        self.mode = self.pick_mode(now)
        tw, th = SIZES[self.mode]
        if self.mode == "lip" and self.edge in ("left", "right"):
            tw, th = th, tw  # a side lip stands upright
        self.W.target, self.H.target = tw, th
        for m, s in self.fade.items():
            s.target = 1.0 if m == self.mode else 0.0
        for s in (self.W, self.H, *self.fade.values()):
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
        for s in (self.W, self.H, *self.fade.values()):
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
        L, col = self.live, self.color()
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(c, rad - 3.5, rad - 3.5)
        if L.get("paused"):
            p.setBrush(QColor(17, 17, 17))
            for dx in (-0.22, 0.12):
                p.drawRoundedRect(QRectF(c.x() + dx * rad, c.y() - rad * 0.32, rad * 0.16, rad * 0.64), 1.5, 1.5)
        else:
            name = L.get("client") or "lowkey"
            initials = "".join(w[0] for w in name.replace("&", " ").split()[:2]).upper()
            p.setPen(QColor(17, 17, 17))
            p.setFont(font(rad * 0.72, QFont.Black))
            p.drawText(QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad), Qt.AlignCenter, initials)
        # daily goal ring
        ring = QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad)
        p.setPen(QPen(QColor(255, 255, 255, 34), 2.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(ring)
        prog = min(1.0, L.get("today_s", 0) / self.goal)
        if prog > 0:
            p.setPen(QPen(col, 2.4, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(ring, 90 * 16, -int(360 * 16 * prog))

    def status(self):
        L = self.live
        if L.get("paused"):
            return "gone dark", "not tracking anything"
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
        self.avatar(p, QPointF(b.left() + 25, cy), 13, now)
        title, _ = self.status()
        p.setPen(TXT)
        p.setFont(font(13.5, QFont.DemiBold))
        name = QFontMetricsF(p.font()).elidedText(title, Qt.ElideRight, 140)
        p.drawText(QRectF(b.left() + 46, b.top(), 150, 42), Qt.AlignVCenter | Qt.AlignLeft, name)
        if L.get("client") and not L.get("paused") and L.get("idle", 0) < 300:  # tiny "now playing" bars
            ex = b.left() + 46 + QFontMetricsF(p.font()).horizontalAdvance(name) + 12
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
        p.setFont(font(14, QFont.DemiBold))
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
        p.setFont(font(16, QFont.Bold))
        p.drawText(QRectF(x + 54, y + 14, 250, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(p.font()).elidedText(title, Qt.ElideRight, 250))
        p.setPen(DIM)
        p.setFont(font(12, QFont.Normal, NUM))
        p.drawText(QRectF(x + 54, y + 36, 250, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   f"this session  {clock(self.session_s(now))}" if L.get("client") and not L.get("paused") else "")

        # status badge
        label = "DARK" if L.get("paused") else "BREAK" if L.get("idle", 0) > 300 else "LIVE"
        badge = QRectF(b.right() - 82, y + 20, 62, 24)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(col.red(), col.green(), col.blue(), 40))
        p.drawRoundedRect(badge, 12, 12)
        p.setBrush(col)
        p.drawEllipse(QPointF(badge.left() + 13, badge.center().y()), 3.5 + 1.2 * (math.sin(now * 5) + 1) / 2, 3.5 + 1.2 * (math.sin(now * 5) + 1) / 2)
        p.setPen(col)
        p.setFont(font(11, QFont.Bold))
        p.drawText(badge.adjusted(22, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, label)

        # what the model thinks you're doing, typed in
        y = y0 + self.row(p, 1)
        shown = sub[: int((now - self.task_t0) * 80)] if sub == self.task else sub
        p.setPen(QColor(220, 220, 220))
        p.setFont(font(13))
        p.drawText(QRectF(x, y + 64, b.width() - 40, 38), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, shown)

        # activity equaliser: last 30 minutes, one bar per minute
        y = y0 + self.row(p, 2)
        self.bars(p, QRectF(x, y + 108, b.width() - 40, 34), col, now)

        # stat chips
        y = y0 + self.row(p, 3)
        cx = x
        for text in (f"today {fmt(L.get('today_s', 0))}", f"{self.cur}{L.get('money', 0):,.0f}", f"{L.get('pending', 0)} to review"):
            p.setFont(font(12, QFont.DemiBold, NUM))
            w = QFontMetricsF(p.font()).horizontalAdvance(text) + 20
            p.setPen(Qt.NoPen)
            p.setBrush(FAINT)
            p.drawRoundedRect(QRectF(cx, y + 152, w, 24), 12, 12)
            p.setPen(QColor(210, 210, 210))
            p.drawText(QRectF(cx, y + 152, w, 24), Qt.AlignCenter, text)
            cx += w + 8

        # buttons
        y = y0 + self.row(p, 4)
        bx = x
        for key, label, icon in (("dark", "resume" if L.get("paused") else "go dark", "play" if L.get("paused") else "pause"),
                                 ("personal", "not work", "slash"), ("open", "open lowkey", "arrow")):
            p.setFont(font(12.5, QFont.DemiBold))
            w = QFontMetricsF(p.font()).horizontalAdvance(label) + 50
            rect = QRectF(bx, y + 190, w, 36)
            self.buttons[key] = rect
            scale = 0.95 if self.pressed == key else 1.04 if self.hot == key else 1.0
            r2 = QRectF(rect.center().x() - rect.width() * scale / 2, rect.center().y() - rect.height() * scale / 2,
                        rect.width() * scale, rect.height() * scale)
            accent = RED if key == "dark" else col if key == "open" else GREY
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 70 if self.hot == key else 34))
            p.drawRoundedRect(r2, 18, 18)
            self.icon(p, icon, QPointF(r2.left() + 20, r2.center().y()), accent)
            p.setPen(TXT)
            p.drawText(r2.adjusted(34, 0, -12, 0), Qt.AlignVCenter | Qt.AlignLeft, label)
            bx += w + 10

    def bars(self, p, rect, col, now):
        mins, m0 = self.live.get("minutes", {}), int(now // 60)
        vals = [min(1.0, mins.get(m0 - 29 + i, 0) / 60) for i in range(30)]
        bw = rect.width() / 30
        active = not self.live.get("paused") and self.live.get("idle", 0) < 300
        p.setPen(Qt.NoPen)
        for i, v in enumerate(vals):
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

    def icon(self, p, kind, c, col):
        p.save()
        p.setPen(QPen(col, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        if kind == "pause":
            p.drawLine(QPointF(c.x() - 3, c.y() - 5), QPointF(c.x() - 3, c.y() + 5))
            p.drawLine(QPointF(c.x() + 3, c.y() - 5), QPointF(c.x() + 3, c.y() + 5))
        elif kind == "play":
            path = QPainterPath(QPointF(c.x() - 3, c.y() - 6))
            path.lineTo(c.x() + 5, c.y())
            path.lineTo(c.x() - 3, c.y() + 6)
            path.closeSubpath()
            p.setBrush(col)
            p.drawPath(path)
        elif kind == "slash":
            p.drawEllipse(c, 6, 6)
            p.drawLine(QPointF(c.x() - 4.2, c.y() + 4.2), QPointF(c.x() + 4.2, c.y() - 4.2))
        elif kind == "arrow":
            p.drawLine(QPointF(c.x() - 4, c.y() + 4), QPointF(c.x() + 4, c.y() - 4))
            p.drawLine(QPointF(c.x() - 1, c.y() - 4), QPointF(c.x() + 4, c.y() - 4))
            p.drawLine(QPointF(c.x() + 4, c.y() - 4), QPointF(c.x() + 4, c.y() + 1))
        p.restore()

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
                self.toast("gone dark. nothing is recorded" if self.live["paused"] else "back on the clock", self.color())
            elif key == "personal":
                self.actions["personal"]()
                self.toast("marked as a side quest", GREY)
            elif key == "open":
                webbrowser.open("http://127.0.0.1:7777")

    def mouseDoubleClickEvent(self, e):
        if not self.hit(e.position()):
            self.pinned = not self.pinned
            self.toast("pinned. double-click to tuck away" if self.pinned else "tucked into the top edge", GREY, 2)

    def run(self):
        self.app.exec()

