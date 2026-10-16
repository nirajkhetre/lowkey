"""Jelly icons: soft, glossy 3D-ish icons drawn with the same light as the island's creatures.

Every icon is a QPainterPath filled with a radial "jelly" gradient, a specular highlight and a contact shadow,
plus a few live details: the clock shows the real time, the coin flips, the check draws itself in.
"""
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen, QRadialGradient, QTransform

INK = QColor(28, 26, 36)
PORCELAIN = QColor("#E9E9F0")  # the neutral jelly every icon uses at rest


def jelly(p, path, base, shadow=True):
    box = path.boundingRect()
    p.setPen(Qt.NoPen)
    if shadow:
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(QPointF(box.center().x(), box.bottom() + box.height() * 0.05), box.width() * 0.34, box.height() * 0.09)
    g = QRadialGradient(QPointF(box.left() + box.width() * 0.32, box.top() + box.height() * 0.26), max(box.width(), box.height()) * 0.95)
    g.setColorAt(0, base.lighter(140))
    g.setColorAt(0.55, base)
    g.setColorAt(1, base.darker(150))
    p.setBrush(g)
    p.drawPath(path)
    hl = QRadialGradient(QPointF(box.left() + box.width() * 0.3, box.top() + box.height() * 0.24), max(box.width(), box.height()) * 0.34)
    hl.setColorAt(0, QColor(255, 255, 255, 160))
    hl.setColorAt(1, QColor(255, 255, 255, 0))
    p.setBrush(hl)
    p.drawPath(path)


def star(p, c, r, color):
    s = QPainterPath(QPointF(c.x(), c.y() - r))
    for k in range(1, 8):
        rr = r if k % 2 == 0 else r * 0.32
        s.lineTo(c.x() + rr * math.sin(k * math.pi / 4), c.y() - rr * math.cos(k * math.pi / 4))
    s.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(s)


def stroke(p, color, w):
    p.setPen(QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)


def moon(p, c, s, now, color=PORCELAIN):
    body = QPainterPath()
    body.addEllipse(c, s * 0.82, s * 0.82)
    bite = QPainterPath()
    bite.addEllipse(QPointF(c.x() + s * 0.42, c.y() - s * 0.3), s * 0.66, s * 0.66)
    jelly(p, body.subtracted(bite), color)
    stroke(p, INK, s * 0.11)  # a sleepy closed eye
    eye = QPainterPath(QPointF(c.x() - s * 0.6, c.y() + s * 0.12))
    eye.quadTo(c.x() - s * 0.45, c.y() + s * 0.3, c.x() - s * 0.3, c.y() + s * 0.14)
    p.drawPath(eye)
    for (dx, dy, r, ph) in ((0.62, -0.62, 0.24, 0.0), (0.86, 0.08, 0.15, 2.0)):
        tw = 0.75 + 0.25 * math.sin(now * 3 + ph)
        star(p, QPointF(c.x() + s * dx, c.y() + s * dy), s * r * tw, QColor(255, 255, 255, 235))


def sun(p, c, s, now, color=PORCELAIN):
    p.save()
    p.translate(c)
    p.rotate(now * 28)
    p.setPen(Qt.NoPen)
    p.setBrush(color.darker(118))
    for k in range(8):
        p.rotate(45)
        p.drawRoundedRect(QRectF(-s * 0.09, -s * 0.98, s * 0.18, s * 0.3), s * 0.09, s * 0.09)
    p.restore()
    body = QPainterPath()
    body.addEllipse(c, s * 0.58, s * 0.58)
    jelly(p, body, color)
    stroke(p, INK, s * 0.1)  # happy ^ ^
    for side in (-1, 1):
        a = QPainterPath(QPointF(c.x() + side * s * 0.22 - s * 0.1, c.y() + s * 0.02))
        a.quadTo(c.x() + side * s * 0.22, c.y() - s * 0.14, c.x() + side * s * 0.22 + s * 0.1, c.y() + s * 0.02)
        p.drawPath(a)


def gamepad(p, c, s, now, color=PORCELAIN):
    pad = QPainterPath()
    pad.addRoundedRect(QRectF(c.x() - s * 0.88, c.y() - s * 0.48, s * 1.76, s * 0.88), s * 0.42, s * 0.42)
    for side in (-1, 1):
        grip = QPainterPath()
        grip.addEllipse(QPointF(c.x() + side * s * 0.56, c.y() + s * 0.28), s * 0.34, s * 0.34)
        pad = pad.united(grip)
    jelly(p, pad, color)
    p.setPen(Qt.NoPen)
    p.setBrush(INK if color.lightness() > 150 else QColor(255, 255, 255, 235))
    dx, dy, arm, th = c.x() - s * 0.45, c.y() - s * 0.04, s * 0.27, s * 0.11
    p.drawRoundedRect(QRectF(dx - arm, dy - th / 2, arm * 2, th), th / 2, th / 2)
    p.drawRoundedRect(QRectF(dx - th / 2, dy - arm, th, arm * 2), th / 2, th / 2)
    p.drawEllipse(QPointF(c.x() + s * 0.36, c.y() - s * 0.13), s * 0.1, s * 0.1)
    p.drawEllipse(QPointF(c.x() + s * 0.56, c.y() + s * 0.06), s * 0.1, s * 0.1)


def open_tile(p, c, s, now, color, nudge=0.0):
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(c.x() - s * 0.72, c.y() - s * 0.72, s * 1.44, s * 1.44), s * 0.42, s * 0.42)
    jelly(p, tile, color)
    ink = INK if color.lightness() > 150 else QColor(255, 255, 255)
    stroke(p, ink, s * 0.17)
    o = QPointF(c.x() + nudge * s * 0.12, c.y() - nudge * s * 0.12)
    p.drawLine(QPointF(o.x() - s * 0.24, o.y() + s * 0.24), QPointF(o.x() + s * 0.24, o.y() - s * 0.24))
    p.drawPolyline([QPointF(o.x() - s * 0.06, o.y() - s * 0.26), QPointF(o.x() + s * 0.26, o.y() - s * 0.26),
                    QPointF(o.x() + s * 0.26, o.y() + s * 0.06)])


def clock(p, c, s, now, color):
    rim = QPainterPath()
    rim.addEllipse(c, s * 0.82, s * 0.82)
    jelly(p, rim, color)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 235))
    p.drawEllipse(c, s * 0.56, s * 0.56)
    t = time.localtime(now)  # the hands show the real time
    for frac, length, width in (((t.tm_hour % 12 + t.tm_min / 60) / 12, 0.3, 0.12), ((t.tm_min + t.tm_sec / 60) / 60, 0.44, 0.09)):
        a = frac * 2 * math.pi
        stroke(p, INK, s * width)
        p.drawLine(c, QPointF(c.x() + s * length * math.sin(a), c.y() - s * length * math.cos(a)))
    p.setPen(Qt.NoPen)
    p.setBrush(color.darker(120))
    p.drawEllipse(c, s * 0.08, s * 0.08)


def coin(p, c, s, now, flip_t0=0.0, symbol="₹", color=PORCELAIN):
    age = now - flip_t0
    squash = abs(math.cos(min(age, 0.9) / 0.9 * 2 * math.pi)) if age < 0.9 else 1.0  # flips once when you earn
    w = s * 0.82 * max(0.12, squash)
    face = QPainterPath()
    face.addEllipse(c, w, s * 0.82)
    jelly(p, face, color)
    stroke(p, color.darker(135), s * 0.09)
    p.drawEllipse(c, w * 0.8, s * 0.66)
    if squash > 0.45:
        f = QFont()
        f.setFamilies(["Bricolage Grotesque", "Segoe UI", "sans-serif"])
        f.setPixelSize(max(6, round(s * 0.95)))
        f.setWeight(QFont.Black)
        p.setFont(f)
        p.setPen(INK if color.lightness() > 150 else color.darker(200))
        p.save()
        p.translate(c)
        p.scale(max(0.12, squash), 1)
        p.drawText(QRectF(-s, -s, 2 * s, 2 * s), Qt.AlignCenter, symbol)
        p.restore()


def check(p, c, s, now, color, active=True):
    box = QPainterPath()
    box.addRoundedRect(QRectF(c.x() - s * 0.72, c.y() - s * 0.72, s * 1.44, s * 1.44), s * 0.4, s * 0.4)
    jelly(p, box, color)
    t = min(1.0, (now % 3.2) / 0.55) if active else 1.0  # the tick draws itself in, every few seconds
    a, b, d = QPointF(c.x() - s * 0.32, c.y() + s * 0.02), QPointF(c.x() - s * 0.08, c.y() + s * 0.28), QPointF(c.x() + s * 0.36, c.y() - s * 0.26)
    stroke(p, INK if color.lightness() > 150 else QColor(255, 255, 255), s * 0.17)
    k = min(1.0, t / 0.4)
    p.drawLine(a, QPointF(a.x() + (b.x() - a.x()) * k, a.y() + (b.y() - a.y()) * k))
    if t > 0.4:
        k2 = (t - 0.4) / 0.6
        p.drawLine(b, QPointF(b.x() + (d.x() - b.x()) * k2, b.y() + (d.y() - b.y()) * k2))


def pin(p, c, s, color, tilt=45.0):
    """A pushpin: leans over when loose, stands straight up when it's holding something."""
    p.save()
    p.translate(c)
    p.rotate(tilt)
    stroke(p, color.darker(160), s * 0.13)
    p.drawLine(QPointF(0, s * 0.1), QPointF(0, s * 0.9))
    head = QPainterPath()
    head.addRoundedRect(QRectF(-s * 0.32, -s * 0.62, s * 0.64, s * 0.5), s * 0.16, s * 0.16)
    head.addRoundedRect(QRectF(-s * 0.56, -s * 0.16, s * 1.12, s * 0.3), s * 0.15, s * 0.15)
    jelly(p, head.simplified(), color, shadow=False)
    p.restore()


def gear(p, c, s, color, turn=0.0):
    """A cog with eight soft teeth; it turns a notch when you hover it."""
    cog = QPainterPath()
    cog.addEllipse(c, s * 0.64, s * 0.64)
    tooth = QPainterPath()
    tooth.addRoundedRect(QRectF(-s * 0.17, -s * 0.94, s * 0.34, s * 0.42), s * 0.1, s * 0.1)
    for k in range(8):
        cog = cog.united(QTransform().translate(c.x(), c.y()).rotate(turn + k * 45).map(tooth))
    hub = QPainterPath()
    hub.addEllipse(c, s * 0.26, s * 0.26)
    jelly(p, cog.subtracted(hub), color, shadow=False)


def info(p, c, s, color):
    dot = QPainterPath()
    dot.addEllipse(c, s, s)
    jelly(p, dot, color, shadow=False)
    ink = INK if color.lightness() > 150 else QColor(255, 255, 255)
    p.setPen(Qt.NoPen)
    p.setBrush(ink)
    p.drawEllipse(QPointF(c.x(), c.y() - s * 0.42), s * 0.15, s * 0.15)
    p.drawRoundedRect(QRectF(c.x() - s * 0.13, c.y() - s * 0.16, s * 0.26, s * 0.62), s * 0.13, s * 0.13)


def bubble(p, c, s, color):
    b = QPainterPath()
    b.addRoundedRect(QRectF(c.x() - s, c.y() - s * 0.8, s * 2, s * 1.45), s * 0.6, s * 0.6)
    tail = QPainterPath(QPointF(c.x() - s * 0.55, c.y() + s * 0.5))
    tail.lineTo(c.x() - s * 0.75, c.y() + s * 1.05)
    tail.lineTo(c.x() - s * 0.1, c.y() + s * 0.6)
    tail.closeSubpath()
    jelly(p, b.united(tail), color, shadow=False)
    p.setPen(Qt.NoPen)
    p.setBrush(INK)
    for dx in (-0.42, 0, 0.42):
        p.drawEllipse(QPointF(c.x() + dx * s, c.y() - s * 0.08), s * 0.12, s * 0.12)
