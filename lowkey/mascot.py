"""The island's mascot: a Fluent Emoji 3D face that reacts to what you're doing.

Art: Microsoft Fluent Emoji (MIT) — https://github.com/microsoft/fluentui-emoji (see assets/mascot/LICENSE).
Behaviour is lowkey's: it picks a mood from your live state, breathes, tilts towards your cursor,
wobbles when its mood changes, falls asleep when you're away and has something to say when you click it.
"""
import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen, QPixmap

ART = Path(__file__).parent / "assets" / "mascot"
GOLD = QColor("#FFD23F")


def fmt(s):
    m = int(s // 60)
    return f"{m}m" if m < 60 else f"{m // 60}h {m % 60:02d}m"


class Mascot:
    def __init__(self, live, goal_s, currency="₹"):
        self.live, self.goal, self.cur = live, goal_s, currency
        self.art = {}
        self.mood, self.changed = "curious", 0.0
        self.event, self.event_until = None, 0.0
        self.quip, self.quip_until, self.quips_said = "", 0.0, 0
        self.partied_on = None

    def pix(self, mood):
        if mood not in self.art:
            self.art[mood] = QPixmap(str(ART / f"{mood}.png"))
        return self.art[mood]

    # ---------- moods ----------
    def react(self, mood, secs=3.0):
        """A short-lived mood for an event: salute on client switch, money on milestones, party on the goal."""
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
        return self.quip if now < self.quip_until else None

    # ---------- talking ----------
    def say(self):
        """Something useful about your day, chosen for the current mood. Clicking again cycles through lines."""
        L, now = self.live, time.time()
        client, s = L.get("client") or "work", self.session_s(now)
        pct = min(999, round(100 * L.get("today_s", 0) / self.goal)) if self.goal else 0
        lines = {
            "hiding": ["i saw nothing. you're off the clock 🙈", "nothing is being recorded right now"],
            "asleep": ["zzz… wake me when you're back", "paused while you're away. no fake hours"],
            "chilling": [f"side quest mode, {fmt(s)} in 😎", "this one isn't going on any invoice"],
            "locked_in": [f"{fmt(s)} straight on {client}. water break?", "locked in. i'll keep the receipts"],
            "curious": ["watching (respectfully). first labels in a minute", "add hints in clients.json so i know who's who"],
        }.get(self.mood, [])
        lines += [f"{self.cur}{L.get('money', 0):,.0f} secured today",
                  f"{pct}% of today's {self.goal // 3600}h goal",
                  f"{L.get('pending', 0)} sessions waiting for your vibe check"]
        if self.mood in ("working", "salute", "money", "party"):
            lines.insert(0, f"{fmt(s)} on {client} this session")
        self.quip = lines[self.quips_said % len(lines)]
        self.quips_said += 1
        self.quip_until = now + 4.5
        self.changed = now  # little wobble when it talks
        return self.quip

    # ---------- drawing ----------
    def draw(self, p, c, rad, now, cursor_x=None, ring_color=None):
        mood, t = self.mood, now - self.changed
        # goal ring behind the face
        ring = QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad)
        p.setPen(QPen(QColor(255, 255, 255, 34), max(1.6, rad * 0.1)))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(ring)
        prog = min(1.0, self.live.get("today_s", 0) / self.goal) if self.goal else 0
        if prog > 0 and ring_color is not None:
            p.setPen(QPen(ring_color, max(1.8, rad * 0.11), Qt.SolidLine, Qt.RoundCap))
            p.drawArc(ring, 90 * 16, -int(360 * 16 * prog))

        sleepy = mood == "asleep"
        breathe = 1 + (0.045 * math.sin(now * 1.3) if sleepy else 0.025 * math.sin(now * 2.4))
        wobble = 1 + 0.2 * math.exp(-6 * t) * math.sin(20 * t)        # squash-and-settle when the mood changes
        hop = -rad * 0.35 * abs(math.sin(now * 7)) if mood in ("party", "money") and t < 3 else 0
        tilt = 0.0
        if cursor_x is not None and mood not in ("asleep", "hiding"):
            tilt = max(-1.0, min(1.0, (cursor_x - c.x()) / 260)) * 12  # looks towards your cursor
        if mood == "salute":
            tilt += 6 * math.sin(now * 9) * math.exp(-2 * t)

        face = rad * 0.88
        p.save()
        p.translate(c.x(), c.y() + hop)
        p.rotate(tilt)
        p.scale(breathe * wobble, breathe / max(0.85, wobble ** 0.5))
        p.drawPixmap(QRectF(-face, -face, 2 * face, 2 * face), self.pix(mood), QRectF(0, 0, 256, 256))
        p.restore()

        if sleepy:
            self.draw_zzz(p, c, rad, now)
        elif mood in ("money", "party") and t < 4:
            self.draw_sparkles(p, c, rad, now)

    def draw_zzz(self, p, c, rad, now):
        for i in range(3):
            phase = (now * 0.45 + i / 3) % 1
            f = QFont()
            f.setFamilies(["Bahnschrift", "SF Pro Rounded", "Helvetica Neue", "sans-serif"])
            f.setPixelSize(max(7, round(rad * (0.35 + 0.35 * phase))))
            f.setWeight(QFont.Black)
            p.setFont(f)
            p.setPen(QColor(220, 220, 255, int(255 * (1 - phase))))
            p.drawText(QPointF(c.x() + rad * (0.55 + 0.5 * phase), c.y() - rad * (0.3 + 1.0 * phase)), "z")

    def draw_sparkles(self, p, c, rad, now):
        p.setPen(Qt.NoPen)
        for i in range(5):
            a = now * 2.4 + i * 2 * math.pi / 5
            d = rad * (1.15 + 0.15 * math.sin(now * 6 + i))
            s = rad * (0.13 + 0.06 * math.sin(now * 9 + i))
            x, y = c.x() + d * math.cos(a), c.y() + d * math.sin(a)
            star = QPainterPath(QPointF(x, y - s))
            for k in range(1, 8):
                r = s if k % 2 == 0 else s * 0.35
                star.lineTo(x + r * math.sin(k * math.pi / 4), y - r * math.cos(k * math.pi / 4))
            star.closeSubpath()
            p.setBrush(GOLD)
            p.drawPath(star)
