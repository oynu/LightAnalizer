"""
Premium neon-glass rendering primitives shared by the analysis board and the on-screen HUD.

  * draw_premium_arrow  - tapered, gradient "liquid glass" arrow with bloom, specular streak and rim light.
                          It deliberately stops short of the target square so the scope can sit on it.
  * draw_sniper_scope   - animated sniper reticle (glass disc, rotating arcs, crosshair ticks, mil-dots,
                          dashed inner ring, pulsing core and lock-on corner brackets) for the target square.
  * draw_glass_pill     - glossy glass capsule with neon rim used for badges / counters.
  * paint_glass_card    - frosted glass card surface with specular rim and optional neon accent.
  * paint_aurora        - deep obsidian background with soft cyan / violet aurora glows.

Pure painting code: no engine, board-detection or game logic lives here.
"""
from __future__ import annotations
import math
from typing import Optional
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import (
    QPainter, QPainterPath, QPen, QBrush, QColor, QLinearGradient, QRadialGradient, QFont
)

SCOPE_RADIUS = 0.33       # scope radius as a fraction of one square
SCOPE_TICK_OUT = 1.32     # crosshair ticks extend to this multiple of the radius
ARROW_GAP = 0.07          # visible gap (in squares) between arrow tip and scope
ARROW_TAIL = 0.17         # arrow starts this far (in squares) from the origin square center


def rgba(c: QColor, a: float) -> QColor:
    return QColor(c.red(), c.green(), c.blue(), max(0, min(255, int(a))))


def lighten(c: QColor, f: float) -> QColor:
    return QColor(
        int(c.red() + (255 - c.red()) * f),
        int(c.green() + (255 - c.green()) * f),
        int(c.blue() + (255 - c.blue()) * f),
        c.alpha()
    )


def scope_clearance(sq: float, scope_scale: float = 1.0) -> float:
    """Distance from target-square center where the arrow tip must stop."""
    return sq * (SCOPE_RADIUS * scope_scale * SCOPE_TICK_OUT + ARROW_GAP)


# ----------------------------------------------------------------------------------------------
# Arrow
# ----------------------------------------------------------------------------------------------
def draw_premium_arrow(
    painter: QPainter,
    p1: QPointF,
    p2: QPointF,
    sq: float,
    color: QColor,
    scale: float = 1.0,
    opacity: float = 1.0,
    scope_scale: float = 1.0,
    with_origin: bool = True
) -> None:
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    dist = math.hypot(dx, dy)
    if dist < 1.0:
        return
    ux, uy = dx / dist, dy / dist
    nx, ny = -uy, ux

    tail = sq * ARROW_TAIL
    tip_clear = scope_clearance(sq, scope_scale)
    length = max(sq * 0.22, dist - tail - tip_clear)

    T = QPointF(p1.x() + ux * tail, p1.y() + uy * tail)
    P = QPointF(T.x() + ux * length, T.y() + uy * length)

    shaft_w = max(5.0, sq * 0.15) * scale
    head_len = min(sq * 0.34 * scale, length * 0.62)
    head_hw = sq * 0.19 * scale
    w0 = shaft_w * 0.26
    w1 = shaft_w * 0.50

    N = QPointF(P.x() - ux * head_len, P.y() - uy * head_len)
    sweep = head_len * 0.12

    def pt(base: QPointF, side: float, w: float, back: float = 0.0) -> QPointF:
        return QPointF(base.x() + nx * side * w - ux * back, base.y() + ny * side * w - uy * back)

    path = QPainterPath()
    path.moveTo(pt(T, -1, w0))
    path.lineTo(pt(N, -1, w1))
    path.lineTo(pt(N, -1, head_hw, sweep))
    path.lineTo(P)
    path.lineTo(pt(N, 1, head_hw, sweep))
    path.lineTo(pt(N, 1, w1))
    path.lineTo(pt(T, 1, w0))
    path.quadTo(QPointF(T.x() - ux * w0 * 2.2, T.y() - uy * w0 * 2.2), pt(T, -1, w0))
    path.closeSubpath()

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)

    # 1. Bloom: stacked soft outlines around the whole silhouette
    painter.setBrush(Qt.NoBrush)
    for extra, alpha in ((2.7, 16), (1.7, 30), (0.95, 58)):
        painter.setPen(QPen(rgba(color, alpha * opacity), shaft_w * extra, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)

    # 2. Body: gradient from translucent tail to hot, lightened head
    body = QLinearGradient(T, P)
    body.setColorAt(0.00, rgba(color, 55 * opacity))
    body.setColorAt(0.30, rgba(color, 175 * opacity))
    body.setColorAt(0.75, rgba(color, 240 * opacity))
    body.setColorAt(1.00, rgba(lighten(color, 0.22), 255 * opacity))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(body))
    painter.drawPath(path)

    # 3. Glass sheen: specular streak along the upper edge of the shaft
    off = -1.0 if ny > 0 else 1.0
    sx0 = T.x() + ux * length * 0.10 + nx * off * shaft_w * 0.16
    sy0 = T.y() + uy * length * 0.10 + ny * off * shaft_w * 0.16
    sx1 = N.x() + nx * off * shaft_w * 0.16
    sy1 = N.y() + ny * off * shaft_w * 0.16
    sheen = QLinearGradient(QPointF(sx0, sy0), QPointF(sx1, sy1))
    sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
    sheen.setColorAt(0.55, QColor(255, 255, 255, int(190 * opacity)))
    sheen.setColorAt(1.0, QColor(255, 255, 255, int(120 * opacity)))
    painter.setPen(QPen(QBrush(sheen), max(1.2, shaft_w * 0.20), Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(sx0, sy0), QPointF(sx1, sy1))

    # 4. Rim light + chiseled head ridge
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255, int(125 * opacity)), 1.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPath(path)
    painter.setPen(QPen(QColor(255, 255, 255, int(170 * opacity)), max(1.0, shaft_w * 0.14), Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(P, pt(N, 0, 0, -head_len * 0.05))

    # 5. Origin marker: thin ring + core dot (does not hide the piece)
    if with_origin:
        r = sq * 0.095 * scale
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(rgba(color, 55 * opacity), max(3.0, r * 0.9)))
        painter.drawEllipse(p1, r, r)
        painter.setPen(QPen(rgba(lighten(color, 0.1), 215 * opacity), max(1.3, sq * 0.022)))
        painter.drawEllipse(p1, r, r)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, int(235 * opacity))))
        painter.drawEllipse(p1, max(1.3, sq * 0.024), max(1.3, sq * 0.024))

    painter.restore()


# ----------------------------------------------------------------------------------------------
# Sniper scope
# ----------------------------------------------------------------------------------------------
def draw_sniper_scope(
    painter: QPainter,
    center: QPointF,
    sq: float,
    color: QColor,
    phase: float = 0.0,
    scale: float = 1.0,
    opacity: float = 1.0,
    lock_on: bool = True,
    spin_dir: float = 1.0
) -> None:
    R = sq * SCOPE_RADIUS * scale
    if R < 3:
        return
    pulse = 0.5 + 0.5 * math.sin(phase * 4.2)
    lw = max(1.3, sq * 0.026)

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.translate(center)

    # Glass lens disc
    lens = QRadialGradient(QPointF(0, 0), R)
    lens.setColorAt(0.0, rgba(color, 8 * opacity))
    lens.setColorAt(0.70, rgba(color, 28 * opacity))
    lens.setColorAt(1.0, rgba(color, 78 * opacity))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(lens))
    painter.drawEllipse(QPointF(0, 0), R, R)

    # Outer ring (glow + core)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(rgba(color, 42 * opacity), lw * 3.6))
    painter.drawEllipse(QPointF(0, 0), R, R)
    painter.setPen(QPen(rgba(lighten(color, 0.12), 235 * opacity), lw))
    painter.drawEllipse(QPointF(0, 0), R, R)

    # Rotating outer arcs
    ar = R * 1.20
    arc_rect = QRectF(-ar, -ar, ar * 2, ar * 2)
    painter.save()
    painter.rotate(phase * 48.0 * spin_dir)
    for width, alpha in ((lw * 3.4, 40), (lw * 1.5, 225)):
        pen = QPen(rgba(color, alpha * opacity), width, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        for k in range(4):
            painter.drawArc(arc_rect, int((k * 90 + 24) * 16), int(42 * 16))
    painter.restore()

    # Dashed inner ring rotating the opposite way
    ir = R * 0.62
    dash = QPen(rgba(color, 150 * opacity), max(1.0, lw * 0.8))
    dash.setStyle(Qt.CustomDashLine)
    dash.setDashPattern([1.6, 3.2])
    dash.setDashOffset(-phase * 9.0 * spin_dir)
    painter.setPen(dash)
    painter.drawEllipse(QPointF(0, 0), ir, ir)

    # Crosshair ticks with a clear center + mil-dots
    t_out, t_in = R * SCOPE_TICK_OUT, R * 0.40
    for ang in (0.0, 90.0, 180.0, 270.0):
        rad = math.radians(ang)
        c, s = math.cos(rad), math.sin(rad)
        p_out = QPointF(c * t_out, s * t_out)
        p_in = QPointF(c * t_in, s * t_in)
        painter.setPen(QPen(rgba(color, 40 * opacity), lw * 3.2, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(p_out, p_in)
        painter.setPen(QPen(rgba(lighten(color, 0.2), 235 * opacity), lw, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(p_out, p_in)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, int(190 * opacity))))
        md = R * 0.74
        painter.drawEllipse(QPointF(c * md, s * md), max(0.9, lw * 0.55), max(0.9, lw * 0.55))
        painter.setBrush(Qt.NoBrush)

    # Pulsing core
    core_r = max(2.0, sq * 0.04) * (1.0 + 0.22 * pulse)
    core = QRadialGradient(QPointF(0, 0), core_r * 2.6)
    core.setColorAt(0.0, rgba(color, 230 * opacity))
    core.setColorAt(1.0, rgba(color, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(core))
    painter.drawEllipse(QPointF(0, 0), core_r * 2.6, core_r * 2.6)
    painter.setBrush(QBrush(QColor(255, 255, 255, int(245 * opacity))))
    painter.drawEllipse(QPointF(0, 0), core_r * 0.62, core_r * 0.62)

    # Lock-on corner brackets of the target square (best move)
    if lock_on:
        half = sq * 0.46 - sq * 0.012 * pulse
        arm = sq * 0.16
        bracket = QPainterPath()
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            cx, cy = sx * half, sy * half
            bracket.moveTo(cx - sx * arm, cy)
            bracket.lineTo(cx, cy)
            bracket.lineTo(cx, cy - sy * arm)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(rgba(color, (46 + 20 * pulse) * opacity), lw * 3.4, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
        painter.drawPath(bracket)
        painter.setPen(QPen(rgba(lighten(color, 0.15), (205 + 50 * pulse) * opacity), max(1.5, lw * 1.25), Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
        painter.drawPath(bracket)

    painter.restore()


# ----------------------------------------------------------------------------------------------
# Glass pill / card / aurora
# ----------------------------------------------------------------------------------------------
def draw_glass_pill(
    painter: QPainter,
    rect: QRectF,
    accent: QColor,
    text: str,
    font: QFont,
    text_color: Optional[QColor] = None,
    glow: bool = True
) -> None:
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    rad = rect.height() / 2.0

    if glow:
        for grow, alpha in ((6.0, 14), (3.5, 26), (1.8, 44)):
            painter.setPen(QPen(rgba(accent, alpha), grow))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, rad, rad)

    body = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    body.setColorAt(0.0, QColor(30, 38, 62, 238))
    body.setColorAt(1.0, QColor(10, 13, 24, 242))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(body))
    painter.drawRoundedRect(rect, rad, rad)

    # Top gloss
    gloss_rect = QRectF(rect.x() + 2, rect.y() + 1.5, rect.width() - 4, rect.height() * 0.46)
    gloss = QLinearGradient(gloss_rect.topLeft(), gloss_rect.bottomLeft())
    gloss.setColorAt(0.0, QColor(255, 255, 255, 62))
    gloss.setColorAt(1.0, QColor(255, 255, 255, 4))
    painter.setBrush(QBrush(gloss))
    painter.drawRoundedRect(gloss_rect, rad * 0.8, rad * 0.8)

    # Specular neon rim
    rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
    rim.setColorAt(0.0, rgba(lighten(accent, 0.45), 230))
    rim.setColorAt(0.5, rgba(accent, 150))
    rim.setColorAt(1.0, rgba(accent, 70))
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QBrush(rim), 1.2))
    painter.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6), rad, rad)

    painter.setFont(font)
    painter.setPen(text_color or lighten(accent, 0.15))
    painter.drawText(rect, Qt.AlignCenter, text)
    painter.restore()


def paint_glass_card(
    painter: QPainter,
    rect: QRectF,
    radius: float = 14.0,
    accent: Optional[QColor] = None,
    strength: float = 1.0,
    glow: bool = False
) -> None:
    """Frosted liquid-glass surface: body gradient, top sheen, specular rim and optional neon accent."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    r = rect.adjusted(1.0, 1.0, -1.0, -1.0)

    if accent is not None and glow:
        for grow, alpha in ((7.0, 10), (4.0, 20), (2.0, 34)):
            painter.setPen(QPen(rgba(accent, alpha * strength), grow))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(r, radius, radius)

    body = QLinearGradient(r.topLeft(), r.bottomRight())
    body.setColorAt(0.0, QColor(255, 255, 255, int(30 * strength)))
    body.setColorAt(1.0, QColor(255, 255, 255, int(7 * strength)))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(12, 16, 28, 150)))
    painter.drawRoundedRect(r, radius, radius)
    painter.setBrush(QBrush(body))
    painter.drawRoundedRect(r, radius, radius)

    if accent is not None:
        tint = QLinearGradient(r.topLeft(), r.bottomRight())
        tint.setColorAt(0.0, rgba(accent, 40 * strength))
        tint.setColorAt(1.0, rgba(accent, 6 * strength))
        painter.setBrush(QBrush(tint))
        painter.drawRoundedRect(r, radius, radius)

    sheen_rect = QRectF(r.x() + 1, r.y() + 1, r.width() - 2, r.height() * 0.5)
    sheen = QLinearGradient(sheen_rect.topLeft(), sheen_rect.bottomLeft())
    sheen.setColorAt(0.0, QColor(255, 255, 255, int(30 * strength)))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    clip = QPainterPath()
    clip.addRoundedRect(r, radius, radius)
    painter.setClipPath(clip)
    painter.setBrush(QBrush(sheen))
    painter.drawRect(sheen_rect)
    painter.setClipping(False)

    rim = QLinearGradient(r.topLeft(), r.bottomRight())
    if accent is not None:
        rim.setColorAt(0.0, rgba(lighten(accent, 0.4), 235 * strength))
        rim.setColorAt(0.55, rgba(accent, 120 * strength))
        rim.setColorAt(1.0, rgba(accent, 55 * strength))
    else:
        rim.setColorAt(0.0, QColor(255, 255, 255, int(120 * strength)))
        rim.setColorAt(0.5, QColor(255, 255, 255, int(38 * strength)))
        rim.setColorAt(1.0, QColor(255, 255, 255, int(14 * strength)))
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QBrush(rim), 1.1))
    painter.drawRoundedRect(r, radius, radius)
    painter.restore()


def paint_aurora(painter: QPainter, rect: QRectF) -> None:
    """Deep obsidian base with soft cyan / violet / emerald aurora glows (premium backdrop)."""
    w, h = rect.width(), rect.height()
    base = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    base.setColorAt(0.0, QColor(11, 15, 27))
    base.setColorAt(1.0, QColor(6, 8, 15))
    painter.fillRect(rect, QBrush(base))

    big = max(w, h)
    for cx, cy, rad, col, alpha in (
        (0.10, -0.05, 0.95, QColor(0, 240, 255), 34),
        (1.00, 1.05, 0.95, QColor(168, 85, 247), 36),
        (0.95, 0.08, 0.55, QColor(0, 255, 157), 11),
    ):
        g = QRadialGradient(QPointF(w * cx, h * cy), big * rad)
        g.setColorAt(0.0, QColor(col.red(), col.green(), col.blue(), alpha))
        g.setColorAt(1.0, QColor(col.red(), col.green(), col.blue(), 0))
        painter.fillRect(rect, QBrush(g))


class AuroraBackground(QWidget):
    """Central widget that paints the obsidian aurora backdrop behind all glass panels."""

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        paint_aurora(painter, QRectF(self.rect()))
        painter.end()
