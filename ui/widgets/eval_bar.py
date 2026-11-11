"""
Vertical evaluation bar widget for chess position advantage.
"""
from __future__ import annotations
import math
from typing import Optional
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtCore import Qt, QRectF

class EvalBarWidget(QWidget):
    """
    Sleek vertical evaluation bar indicating White vs Black advantage.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(24)
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

        w = self.width()
        h = self.height()

        # Calculate white percentage using sigmoid formula
        # win% = 1 / (1 + 10^(-eval/400))
        eval_clamped = max(-1000.0, min(1000.0, self._eval_cp))
        white_pct = 1.0 / (1.0 + math.pow(10.0, -eval_clamped / 400.0))

        # Top is black if white_at_bottom=True
        if self._white_at_bottom:
            black_h = h * (1.0 - white_pct)
            white_h = h * white_pct

            # Top: Black
            painter.fillRect(QRectF(0, 0, w, black_h), QColor("#27272A"))
            # Bottom: White
            painter.fillRect(QRectF(0, black_h, w, white_h), QColor("#F4F4F5"))
        else:
            white_h = h * white_pct
            black_h = h * (1.0 - white_pct)

            # Top: White
            painter.fillRect(QRectF(0, 0, w, white_h), QColor("#F4F4F5"))
            # Bottom: Black
            painter.fillRect(QRectF(0, white_h, w, black_h), QColor("#27272A"))

        # Center indicator line
        painter.setPen(QColor("#71717A"))
        painter.drawLine(0, h // 2, w, h // 2)

        # Border
        painter.setPen(QColor("#3F3F46"))
        painter.drawRect(0, 0, w - 1, h - 1)

        painter.end()
