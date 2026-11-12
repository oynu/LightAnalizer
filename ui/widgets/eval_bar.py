"""
Vertical evaluation bar widget for chess position advantage.
"""
from __future__ import annotations
import math
from typing import Optional
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient, QPainterPath, QPen, QBrush
from PySide6.QtCore import Qt, QRectF, QPointF

class EvalBarWidget(QWidget):
    """
    Sleek vertical evaluation bar indicating White vs Black advantage,
    styled as an Apple VisionOS liquid-glass capsule with cyber neon accents.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(26)
        self.setMinimumHeight(240)
        self._eval_cp = 0.0  # Centipawns (+ for white, - for black)
        self._eval_str = "0.0"
        self._is_mate = False
        self._mate_in = 0
        self._white_at_bottom = True

    def set_evaluation(self, eval_str: str, score_cp: Optional[int] = None, mate_in: Optional[int] = None) -> None:
        self._eval_str = eval_str
        if mate_in is not None:
            self._is_mate = True
            self._mate_in = mate_in
            self._eval_cp = 1000.0 if mate_in > 0 else -1000.0
        elif score_cp is not None:
            self._is_mate = False
            self._eval_cp = float(score_cp)
        else:
            self._is_mate = False
            self._eval_cp = 0.0
        self.update()

    def set_white_at_bottom(self, val: bool) -> None:
        self._white_at_bottom = val
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = float(self.width())
        h = float(self.height())
        bar_rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        # Calculate white percentage using standard sigmoid formula
        eval_clamped = max(-1000.0, min(1000.0, self._eval_cp))
        white_pct = 1.0 / (1.0 + math.pow(10.0, -eval_clamped / 400.0))

        # Determine split position
        if self._white_at_bottom:
            split_y = h * (1.0 - white_pct)
            white_rect = QRectF(0, split_y, w, h - split_y)
            black_rect = QRectF(0, 0, w, split_y)
            white_is_top = False
        else:
            split_y = h * white_pct
            white_rect = QRectF(0, 0, w, split_y)
            black_rect = QRectF(0, split_y, w, h - split_y)
            white_is_top = True

        # Clip to 8px rounded capsule
        capsule_path = QPainterPath()
        capsule_path.addRoundedRect(bar_rect, 8.0, 8.0)
        painter.save()
        painter.setClipPath(capsule_path)

        # Background base: deep obsidian
        obsidian_color = QColor(8, 11, 18, 220)
        painter.fillRect(bar_rect, obsidian_color)

        # Advantage styling:
        # Neon gradient (#00F0FF -> #A855F7) on advantage side, obsidian on opposing side
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor("#00F0FF"))
        grad.setColorAt(1.0, QColor("#A855F7"))

        if self._eval_cp >= 0:
            # White advantage
            painter.fillRect(white_rect, grad)
            painter.fillRect(black_rect, obsidian_color)
        else:
            # Black advantage
            black_grad = QLinearGradient(0, 0, 0, h)
            black_grad.setColorAt(0.0, QColor("#A855F7"))
            black_grad.setColorAt(1.0, QColor("#00F0FF"))
            painter.fillRect(black_rect, black_grad)
            painter.fillRect(white_rect, obsidian_color)

        # Subtle graduation ticks (25 / 50 / 75 %)
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1.0))
        for frac in (0.25, 0.5, 0.75):
            ty = h * frac
            painter.drawLine(QPointF(w * 0.62, ty), QPointF(w, ty))

        # Glowing divider line at the evaluation split (soft bloom + bright core)
        for width, alpha in ((9.0, 26), (5.5, 60), (3.0, 140)):
            painter.setPen(QPen(QColor(0, 240, 255, alpha), width))
            painter.drawLine(QPointF(0, split_y), QPointF(w, split_y))

        split_pen_core = QPen(QColor(255, 255, 255, 230), 1.2)
        painter.setPen(split_pen_core)
        painter.drawLine(QPointF(0, split_y), QPointF(w, split_y))

        # Monospace tabular score text
        font = QFont("JetBrains Mono", 8, QFont.Bold)
        font.setStyleHint(QFont.Monospace)
        painter.setFont(font)

        # Draw eval text in the dominant section
        text_color = QColor("#080B12") if (
            (self._eval_cp >= 0 and not white_is_top and (h - split_y) > 28) or
            (self._eval_cp >= 0 and white_is_top and split_y > 28) or
            (self._eval_cp < 0 and white_is_top and (h - split_y) > 28) or
            (self._eval_cp < 0 and not white_is_top and split_y > 28)
        ) else QColor("#F8FAFC")

        painter.setPen(text_color)
        # Place text at top or bottom depending on which side has sufficient room
        if self._white_at_bottom:
            if white_pct >= 0.5:
                text_rect = QRectF(0, h - 22, w, 18)
            else:
                text_rect = QRectF(0, 4, w, 18)
        else:
            if white_pct >= 0.5:
                text_rect = QRectF(0, 4, w, 18)
            else:
                text_rect = QRectF(0, h - 22, w, 18)

        painter.drawText(text_rect, Qt.AlignCenter, self._eval_str)

        # Glass sheen: bright vertical highlight on the left edge + soft top gloss
        sheen = QLinearGradient(0, 0, w, 0)
        sheen.setColorAt(0.0, QColor(255, 255, 255, 70))
        sheen.setColorAt(0.35, QColor(255, 255, 255, 14))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(bar_rect, QBrush(sheen))
        painter.restore()

        # Specular glass rim (bright top-left, fading bottom-right)
        rim = QLinearGradient(0, 0, w, h)
        rim.setColorAt(0.0, QColor(255, 255, 255, 140))
        rim.setColorAt(0.5, QColor(0, 240, 255, 50))
        rim.setColorAt(1.0, QColor(168, 85, 247, 80))
        painter.setPen(QPen(QBrush(rim), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(bar_rect, 8.0, 8.0)

        painter.end()
