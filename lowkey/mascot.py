"""The island's mascot: a soft blob creature with pill eyes, drawn live with QPainter.

Style inspired by Bible Strong Avatar Lab's procedural avatars (https://github.com/smontlouis/bible-strong-avatar-lab);
this renderer is lowkey's own: no code or art is taken from it.

Each client gets its own creature (shape from its name, colour from clients.json) and it morphs when you switch.
Its eyes follow your cursor with a little perspective, it blinks on its own, and its mood follows your live state.
"""
import hashlib
import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen, QRadialGradient

# (exponent, width/height, egg): 2 = ellipse, ~3.5 = squircle; egg > 0 narrows the top
SHAPES = [(2.0, 1.0, 0.0), (3.6, 1.0, 0.0), (2.2, 0.86, 0.16), (2.6, 0.74, 0.0), (3.0, 1.18, 0.05)]
GOLD = QColor("#FFD23F")


def fmt(s):
    m = int(s // 60)
    return f"{m}m" if m < 60 else f"{m // 60}h {m % 60:02d}m"


def shape_for(name):
    """Same client, same creature: the shape is picked from a hash of the client's name."""
    if not name or name == "Personal":
        return SHAPES[0]
    return SHAPES[int(hashlib.md5(name.encode()).hexdigest(), 16) % len(SHAPES)]


class Smooth:
    """Critically damped follower used for morphing shape, colour and gaze."""

    def __init__(self, x, speed=8.0):
        self.x, self.speed = float(x), speed

    def to(self, target, dt):
        self.x += (target - self.x) * (1 - math.exp(-self.speed * dt))
        return self.x


class Mascot:
    def __init__(self, live, goal_s, currency="₹"):
        self.live, self.goal, self.cur = live, goal_s, currency
        self.mood, self.changed = "curious", 0.0
        self.event, self.event_until = None, 0.0
        self.quip, self.quip_until, self.quips_said = "", 0.0, 0
        self.partied_on = None
        n, aspect, egg = SHAPES[0]
        self.n, self.aspect, self.egg = Smooth(n, 5), Smooth(aspect, 5), Smooth(egg, 5)
        self.rgb = [Smooth(v, 5) for v in (122, 122, 122)]
        self.gx, self.gy = Smooth(0, 7), Smooth(0, 7)
        self.next_blink, self.blink_at, self.double = time.time() + 2, 0.0, False
        self.wander, self.wander_at = (0.0, 0.0), 0.0
        self.last, self.instant = time.time(), False
        self.calm = False  # the OS asked for reduced motion: no hops or squash, eyes and colour still change

    def snap(self):
        """Skip the morph on the next frame (screenshots, tests)."""
        self.instant = True

    # ---------- moods ----------
    def react(self, mood, secs=3.0):
        """Short-lived moods: wide eyes on a client switch, star eyes on milestones, party on the daily goal."""
        self.event, self.event_until = mood, time.time() + secs

    def session_s(self, now):
        start = self.live.get("session_start")
        return now - start if start else 0

    def pick(self, now):
        L = self.live
        if L.get("paused"):
            return "hiding"
        if L.get("idle", 0) > 300:
            return "asleep"
        if self.event and now < self.event_until:
            return self.event
        if not L.get("client"):
            return "curious"
        if L["client"] == "Personal":
            return "chilling"
        if self.session_s(now) > 90 * 60:
            return "locked_in"
        return "working"

    def update(self, now):
        today = time.strftime("%Y-%m-%d")
        if self.live.get("today_s", 0) >= self.goal and self.partied_on != today:
            self.partied_on = today
            self.react("party", 5)
        mood = self.pick(now)
        if mood != self.mood:
            self.mood, self.changed = mood, now
        if now >= self.next_blink and self.mood not in ("asleep", "hiding"):
            self.blink_at, self.double = now, random.random() < 0.22
            self.next_blink = now + random.uniform(2.4, 5.5)
        return self.quip if now < self.quip_until else None

    # ---------- talking ----------
    def say(self):
        """Something useful about your day, chosen for the current mood. Clicking again cycles through lines."""
        L, now = self.live, time.time()
        client, s = L.get("client") or "work", self.session_s(now)
        pct = min(999, round(100 * L.get("today_s", 0) / self.goal)) if self.goal else 0
        lines = {
            "hiding": ["i saw nothing. you're off the clock", "nothing is being recorded right now"],
            "asleep": ["zzz… wake me when you're back", "paused while you're away. no fake hours"],
            "chilling": [f"side quest mode, {fmt(s)} in", "this one isn't going on any invoice"],
            "locked_in": [f"{fmt(s)} straight on {client}. water break?", "locked in. i'll keep the receipts"],
            "curious": ["watching (respectfully). first labels in a minute", "add hints in clients.json so i know who's who"],
        }.get(self.mood, [])
        lines += [f"{self.cur}{L.get('money', 0):,.0f} secured today",
                  f"{pct}% of today's {self.goal // 3600}h goal",
                  f"{L.get('pending', 0)} sessions waiting for your vibe check"]
        if self.mood in ("working", "surprised", "money", "party"):
            lines.insert(0, f"{fmt(s)} on {client} this session")
        self.quip = lines[self.quips_said % len(lines)]
        self.quips_said += 1
        self.quip_until = now + 4.5
        self.changed = now  # a little hop when it talks
        return self.quip

    # ---------- drawing ----------
    def body_path(self, w, h, n, egg):
        P = QPainterPath()
        for i in range(73):
            t = 2 * math.pi * i / 72
            c, s = math.cos(t), math.sin(t)
            x = (w / 2) * math.copysign(abs(c) ** (2 / n), c)
            y = (h / 2) * math.copysign(abs(s) ** (2 / n), s)
            x *= 1 - egg * (-y / (h / 2))  # egg: narrower at the top (y < 0)
            P.lineTo(x, y) if i else P.moveTo(x, y)
        P.closeSubpath()
        return P

    def draw(self, p, c, rad, now, cursor=None, _ring=None):
        dt, self.last = (10.0 if self.instant else min(0.05, now - self.last)), now
        self.instant = False
        L, mood, t = self.live, self.mood, now - self.changed

        # morph towards this client's creature and colour
        tn, ta, te = shape_for(L.get("client"))
        n, aspect, egg = self.n.to(tn, dt), self.aspect.to(ta, dt), self.egg.to(te, dt)
        target = QColor("#3a3a3e") if L.get("client") == "Personal" else QColor(L.get("color") or "#8a8a8a")
        if mood == "hiding":  # moonlit: the client's colour washed in violet
            v = QColor("#9B8CFF")
            target = QColor(int(target.red() * 0.15 + v.red() * 0.85), int(target.green() * 0.15 + v.green() * 0.85),
                            int(target.blue() * 0.15 + v.blue() * 0.85)).darker(108)
        r, g, b = (ch.to(v, dt) for ch, v in zip(self.rgb, (target.red(), target.green(), target.blue())))
        base = QColor(int(r), int(g), int(b))
        dark_body = base.lightness() < 90

        # gaze: follow the cursor; when it's far away, glance around now and then
        gx, gy = 0.0, 0.0
        if cursor is not None and mood not in ("asleep", "hiding"):
            gx = max(-1.0, min(1.0, (cursor.x() - c.x()) / 180))
            gy = max(-1.0, min(1.0, (cursor.y() - c.y()) / 140))
        elif mood == "curious" or cursor is None:
            if now > self.wander_at:
                self.wander, self.wander_at = (random.uniform(-0.8, 0.8), random.uniform(-0.4, 0.3)), now + random.uniform(1.2, 3)
            gx, gy = self.wander
        if mood == "asleep":
            gx, gy = 0.0, 0.35
        gx, gy = self.gx.to(gx, dt), self.gy.to(gy, dt)

        # body motion: breathe, squash-and-settle on mood change, hop when excited
        breathe = 0.035 * math.sin(now * (1.3 if mood == "asleep" else 2.4))
        squash = 0.0 if self.calm else 0.22 * math.exp(-5 * t) * math.sin(18 * t)
        hop = 0.0
        if mood in ("party", "money", "surprised") and t < 2.5 and not self.calm:
            hop = -rad * 0.28 * abs(math.sin(now * 8)) * math.exp(-0.6 * t)
        size = rad * 1.9
        w = size * min(1.0, aspect) * (1 + squash + breathe * 0.5)
        h = size * min(1.0, 1 / aspect) * (1 - squash + breathe)

        p.save()
        p.translate(c.x() + gx * rad * 0.06, c.y() + hop + (size - h) * 0.35)
        p.rotate(gx * 5)
        body = self.body_path(w, h, n, egg)

        # contact shadow, then the lit body
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(QPointF(0, h * 0.5), w * 0.38, h * 0.07)
        grad = QRadialGradient(QPointF(-w * 0.22 - gx * w * 0.1, -h * 0.28), max(w, h) * 0.95)
        grad.setColorAt(0.0, base.lighter(132))
        grad.setColorAt(0.55, base)
        grad.setColorAt(1.0, base.darker(150))
        p.setBrush(grad)
        p.drawPath(body)
        rim = QRadialGradient(QPointF(-w * 0.18, -h * 0.32), max(w, h) * 0.3)  # soft specular highlight
        rim.setColorAt(0, QColor(255, 255, 255, 70))
        rim.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(rim)
        p.drawPath(body)

        self.draw_eyes(p, w, h, gx, gy, now, QColor(245, 245, 245) if dark_body else QColor(17, 17, 17))
        p.restore()

        if mood == "asleep":
            self.draw_zzz(p, c, rad, now)
        elif mood in ("money", "party") and t < 4:
            self.draw_sparkles(p, c, rad, now)

    def openness(self, now):
        """1 = open, 0 = closed. A blink takes 140 ms; sometimes it blinks twice."""
        for start in (self.blink_at, self.blink_at + 0.22 if self.double else None):
            if start is not None and 0 <= now - start < 0.14:
                return abs((now - start) / 0.07 - 1)
        return 1.0

    def draw_eyes(self, p, w, h, gx, gy, now, ink):
        mood, S = self.mood, min(w, h)
        spacing = S * 0.34 * (1 - 0.2 * abs(gx))        # eyes crowd together as it turns
        cx, cy = gx * S * 0.2, -S * 0.06 + gy * S * 0.1
        ew, eh = S * 0.13, S * 0.27
        o = self.openness(now)
        p.setPen(Qt.NoPen)
        p.setBrush(ink)
        for side in (-1, 1):
            x = cx + side * spacing / 2
            near = 1 + 0.12 * side * gx                  # the eye on the side it's turning to looks bigger
            ew2, eh2 = ew * near, eh * near
            pen = QPen(ink, ew2 * 0.55, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            if mood == "asleep" or o < 0.12:
                p.setPen(pen)
                p.drawLine(QPointF(x - ew2 * 0.7, cy + eh2 * 0.1), QPointF(x + ew2 * 0.7, cy + eh2 * 0.1))
                p.setPen(Qt.NoPen)
            elif mood in ("chilling", "party"):          # happy ^ ^
                p.setPen(pen)
                arc = QPainterPath(QPointF(x - ew2 * 0.6, cy + eh2 * 0.15))
                arc.quadTo(x, cy - eh2 * 0.55, x + ew2 * 0.6, cy + eh2 * 0.15)
                p.setBrush(Qt.NoBrush)
                p.drawPath(arc)
                p.setPen(Qt.NoPen)
                p.setBrush(ink)
            elif mood == "hiding":                       # squeezed > <
                p.setPen(pen)
                k = -side
                p.drawPolyline([QPointF(x - k * ew2 * 0.6, cy - eh2 * 0.3), QPointF(x + k * ew2 * 0.5, cy),
                                QPointF(x - k * ew2 * 0.6, cy + eh2 * 0.3)])
                p.setPen(Qt.NoPen)
            elif mood == "money":                        # star eyes
                star = QPainterPath()
                for k in range(8):
                    rr = eh2 * (0.55 if k % 2 == 0 else 0.2)
                    a = k * math.pi / 4 + now * 2
                    pt = QPointF(x + rr * math.sin(a), cy - rr * math.cos(a))
                    star.lineTo(pt) if k else star.moveTo(pt)
                star.closeSubpath()
                p.setBrush(GOLD if ink.lightness() < 128 else ink)
                p.drawPath(star)
                p.setBrush(ink)
            elif mood == "surprised":                    # wide round eyes
                p.drawEllipse(QPointF(x, cy), ew2 * 0.85 * o, ew2 * 0.85 * max(o, 0.2))
            else:
                if mood == "locked_in":                  # narrowed, slanted: determined
                    p.save()
                    p.translate(x, cy + eh2 * 0.1)
                    p.rotate(-side * 20)
                    bw, bh = ew2 * 1.5, max(ew2 * 0.62 * o, ew2 * 0.2)
                    p.drawRoundedRect(QRectF(-bw / 2, -bh / 2, bw, bh), bh / 2, bh / 2)
                    p.restore()
                    continue
                hh = eh2 * o
                if mood == "curious" and side == 1:      # one small eye, like it's squinting at you
                    p.drawEllipse(QPointF(x, cy + eh2 * 0.1), ew2 * 0.5, ew2 * 0.5 * max(o, 0.2))
                    continue
                p.save()
                p.translate(x, cy)
                p.drawRoundedRect(QRectF(-ew2 / 2, -hh / 2, ew2, hh), ew2 / 2, min(ew2, hh) / 2)
                p.restore()

    def draw_zzz(self, p, c, rad, now):
        for i in range(3):
            phase = (now * 0.45 + i / 3) % 1
            f = QFont()
            f.setFamilies(["Bricolage Grotesque", "Bahnschrift", "SF Pro Rounded", "sans-serif"])
            f.setPixelSize(max(7, round(rad * (0.35 + 0.35 * phase))))
            f.setWeight(QFont.Black)
            p.setFont(f)
            p.setPen(QColor(220, 220, 255, int(255 * (1 - phase))))
            p.drawText(QPointF(c.x() + rad * (0.6 + 0.5 * phase), c.y() - rad * (0.3 + 1.0 * phase)), "z")

    def draw_sparkles(self, p, c, rad, now):
        p.setPen(Qt.NoPen)
        p.setBrush(GOLD)
        for i in range(5):
            a = now * 2.4 + i * 2 * math.pi / 5
            d = rad * (1.2 + 0.15 * math.sin(now * 6 + i))
            s = rad * (0.14 + 0.06 * math.sin(now * 9 + i))
            x, y = c.x() + d * math.cos(a), c.y() + d * math.sin(a)
            star = QPainterPath(QPointF(x, y - s))
            for k in range(1, 8):
                rr = s if k % 2 == 0 else s * 0.35
                star.lineTo(x + rr * math.sin(k * math.pi / 4), y - rr * math.cos(k * math.pi / 4))
            star.closeSubpath()
            p.drawPath(star)
