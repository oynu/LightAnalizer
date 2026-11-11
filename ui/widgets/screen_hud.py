"""
Screen HUD and On-Screen Live Move Overlay.
Renders high-visibility glowing neon candidate arrows and best-move notation
directly on top of the live game chessboard on the user's screen.
100% click-through (transparent for all mouse/keyboard input) and excluded
from screen capture so it never interferes with game interaction or vision recognition.
"""
from __future__ import annotations
import math
import sys
from typing import List, Optional, Tuple
import chess
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QPainterPath
)
from PySide6.QtCore import Qt, QPointF, QRectF, QRect
from core.types import CandidateMove, BoardCalibration


class ScreenBoardOverlay(QWidget):
    """
    Transparent, click-through on-screen HUD that draws live neon arrows and
    move recommendations directly on top of the physical board on screen.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("LightAnalizer - Screen HUD Overlay")
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.WindowTransparentForInput |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._white_at_bottom = True
        self._candidate_moves: List[CandidateMove] = []
        self._show_badge = True
        self._calibration: Optional[BoardCalibration] = None

        self._apply_os_clickthrough_and_capture_exclusion()

    def _apply_os_clickthrough_and_capture_exclusion(self) -> None:
        """
        Enforces true OS-level click-through and excludes this window from
        screen capture so vision detection never captures its own rendered arrows.
        """
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                hwnd = int(self.winId())

                # 1. WS_EX_TRANSPARENT + WS_EX_LAYERED: completely click-through
                GWL_EXSTYLE = -20
                WS_EX_TRANSPARENT = 0x00000020
                WS_EX_LAYERED = 0x00080000
                WS_EX_NOACTIVATE = 0x08000000
                WS_EX_TOOLWINDOW = 0x00000080

                user32 = ctypes.windll.user32
                styles = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(
                    hwnd,
                    GWL_EXSTYLE,
                    styles | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
                )

                # 2. WDA_EXCLUDEFROMCAPTURE (0x00000011): window is invisible to BitBlt/PrintWindow/Desktop Duplication
                user32.SetWindowDisplayAffinity(hwnd, 0x00000011)

                # 3. SWP_NOACTIVATE + HWND_TOPMOST: stays permanently on top without stealing focus
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_SHOWWINDOW = 0x0040
                SWP_NOACTIVATE = 0x0010
                user32.SetWindowPos(
                    hwnd,
                    wintypes.HWND(-1),
                    0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE
                )
            except Exception:
                pass

    def update_calibration(self, cal: BoardCalibration) -> None:
        """Positions and sizes the overlay exactly to match the calibrated chessboard on screen."""
        self._calibration = cal
        self._white_at_bottom = cal.orientation_white_bottom
        self.setGeometry(cal.x, cal.y, cal.width, cal.height)
        self._apply_os_clickthrough_and_capture_exclusion()
        self.update()

    def set_white_at_bottom(self, white_bottom: bool) -> None:
        """Sets board perspective (White at bottom vs Black at bottom)."""
        if self._white_at_bottom != white_bottom:
            self._white_at_bottom = white_bottom
            self.update()

    def set_candidate_moves(self, candidates: List[CandidateMove]) -> None:
        """Updates the candidate moves to display on screen."""
        self._candidate_moves = candidates
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_os_clickthrough_and_capture_exclusion()

    def _square_to_coords(self, sq: chess.Square) -> Tuple[int, int]:
        file_idx = chess.square_file(sq)
        rank_idx = chess.square_rank(sq)
        if self._white_at_bottom:
            col = file_idx
            row = 7 - rank_idx
        else:
            col = 7 - file_idx
            row = rank_idx
        return col, row

    def paintEvent(self, event) -> None:
        if not self._candidate_moves:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        b_size = min(w, h)
        sq_size = b_size / 8.0
        bx = (w - b_size) / 2.0
        by = (h - b_size) / 2.0

        # Subtle specular neon border around board perimeter
        border_pen = QPen(QColor(0, 240, 255, 70), 1.5)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(bx + 1, by + 1, b_size - 2, b_size - 2), 6, 6)

        # Draw candidate move arrows in rank order (Rank 3, Rank 2, then Rank 1 on top)
        base_colors = [
            QColor("#00F0FF"),   # 1st: Electric Cyan
            QColor("#A855F7"),   # 2nd: Neon Violet
            QColor("#FFB800")    # 3rd: Neon Amber
        ]

        cands = self._candidate_moves[:3]
        for idx in reversed(range(len(cands))):
            cand = cands[idx]
            if getattr(cand, "is_brilliant", False):
                color = QColor("#00FF9D")
            else:
                color = base_colors[idx]
            scale = 1.15 if idx == 0 else 0.95
            self._draw_neon_arrow(
                painter,
                cand.move.from_square,
                cand.move.to_square,
                bx, by, sq_size,
                color,
                scale_mult=scale,
                rank=idx + 1
            )

        # Draw move recommendation text badge for #1 best move
        if self._show_badge and cands:
            best = cands[0]
            self._draw_best_move_badge(painter, best, bx, by, sq_size)

        painter.end()

    def _draw_neon_arrow(
        self,
        painter: QPainter,
        from_sq: chess.Square,
        to_sq: chess.Square,
        bx: float,
        by: float,
        sq_size: float,
        color: QColor,
        scale_mult: float = 1.0,
        rank: int = 1
    ) -> None:
        c1, r1 = self._square_to_coords(from_sq)
        c2, r2 = self._square_to_coords(to_sq)

        x1 = bx + (c1 * sq_size) + (sq_size / 2.0)
        y1 = by + (r1 * sq_size) + (sq_size / 2.0)
        x2 = bx + (c2 * sq_size) + (sq_size / 2.0)
        y2 = by + (r2 * sq_size) + (sq_size / 2.0)

        angle = math.atan2(y2 - y1, x2 - x1)
        shaft_width = max(5.0, sq_size * 0.13) * scale_mult
        head_length = sq_size * 0.42 * scale_mult
        head_width = sq_size * 0.40 * scale_mult

        # Arrowhead positions
        tip_x = x2 - math.cos(angle) * (sq_size * 0.10)
        tip_y = y2 - math.sin(angle) * (sq_size * 0.10)
        base_x = tip_x - math.cos(angle) * head_length
        base_y = tip_y - math.sin(angle) * head_length

        start_x = x1 + math.cos(angle) * (sq_size * 0.12)
        start_y = y1 + math.sin(angle) * (sq_size * 0.12)

        # Aerodynamic swept-back chevron head
        sweep = head_length * 0.28
        left_x = base_x + math.sin(angle) * (head_width / 2.0) - math.cos(angle) * sweep
        left_y = base_y - math.cos(angle) * (head_width / 2.0) - math.sin(angle) * sweep
        right_x = base_x - math.sin(angle) * (head_width / 2.0) - math.cos(angle) * sweep
        right_y = base_y + math.cos(angle) * (head_width / 2.0) - math.sin(angle) * sweep

        arrow_head = QPolygonF([
            QPointF(tip_x, tip_y),
            QPointF(left_x, left_y),
            QPointF(base_x, base_y),
            QPointF(right_x, right_y)
        ])

        painter.save()

        # 1. Origin square glowing node
        r_outer = shaft_width * 1.5
        r_inner = shaft_width * 0.75
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 60)))
        painter.drawEllipse(QPointF(x1, y1), r_outer, r_outer)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(x1, y1), r_inner, r_inner)
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.drawEllipse(QPointF(x1, y1), r_inner * 0.4, r_inner * 0.4)

        # 2. Shaft - Multi-layer neon beam
        # Pass 1: Soft ambient bloom halo
        bloom_pen = QPen(
            QColor(color.red(), color.green(), color.blue(), 45),
            shaft_width + 12,
            Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin
        )
        painter.setPen(bloom_pen)
        painter.drawLine(QPointF(start_x, start_y), QPointF(base_x, base_y))

        # Pass 2: Radiant neon glow
        glow_pen = QPen(
            QColor(color.red(), color.green(), color.blue(), 110),
            shaft_width + 5,
            Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin
        )
        painter.setPen(glow_pen)
        painter.drawLine(QPointF(start_x, start_y), QPointF(base_x, base_y))

        # Pass 3: Solid neon beam
        core_pen = QPen(color, shaft_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(core_pen)
        painter.drawLine(QPointF(start_x, start_y), QPointF(base_x, base_y))

        # Pass 4: Laser specular core
        spec_pen = QPen(
            QColor(255, 255, 255, 210),
            max(1.5, shaft_width * 0.28),
            Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin
        )
        painter.setPen(spec_pen)
        painter.drawLine(QPointF(start_x, start_y), QPointF(base_x, base_y))

        # 3. Arrowhead
        # Pass 1: Head ambient bloom
        head_bloom_pen = QPen(
            QColor(color.red(), color.green(), color.blue(), 75),
            5,
            Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin
        )
        painter.setPen(head_bloom_pen)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 85)))
        painter.drawPolygon(arrow_head)

        # Pass 2: Head core
        painter.setPen(QPen(QColor(255, 255, 255, 140), 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(QBrush(color))
        painter.drawPolygon(arrow_head)

        # Pass 3: Specular chiseled ridge down tip
        ridge_pen = QPen(QColor(255, 255, 255, 230), max(1.2, shaft_width * 0.22), Qt.SolidLine, Qt.RoundCap)
        painter.setPen(ridge_pen)
        painter.drawLine(QPointF(tip_x, tip_y), QPointF(base_x, base_y))

        painter.restore()

    def _draw_best_move_badge(
        self,
        painter: QPainter,
        cand: CandidateMove,
        bx: float,
        by: float,
        sq_size: float
    ) -> None:
        """Renders an on-screen floating pill badge with the recommended SAN move & eval score."""
        c2, r2 = self._square_to_coords(cand.move.to_square)
        tx = bx + (c2 * sq_size) + (sq_size / 2.0)
        ty = by + (r2 * sq_size) + (sq_size / 2.0)

        # Position badge just above or below target square
        is_brill = getattr(cand, "is_brilliant", False)
        badge_w = max(115.0 if is_brill else 90.0, sq_size * (1.45 if is_brill else 1.25))
        badge_h = 24.0
        badge_x = tx - (badge_w / 2.0)
        badge_y = ty - (sq_size * 0.55) - badge_h
        if badge_y < by + 4:
            badge_y = ty + (sq_size * 0.55)

        badge_rect = QRectF(badge_x, badge_y, badge_w, badge_h)

        painter.save()
        # Glass pill backing
        border_col = QColor(0, 255, 157, 230) if is_brill else QColor(0, 240, 255, 180)
        painter.setPen(QPen(border_col, 1.4 if is_brill else 1.2))
        painter.setBrush(QBrush(QColor(10, 14, 24, 225)))
        painter.drawRoundedRect(badge_rect, 12, 12)

        # Text: "💎 !!: Bxh7+ +2.4" or "★ Nf3 +0.4"
        font = QFont("JetBrains Mono", 10, QFont.Bold)
        font.setStyleHint(QFont.Monospace)
        painter.setFont(font)

        text = f"💎 !! {cand.san}  {cand.eval_str}" if is_brill else f"★ {cand.san}  {cand.eval_str}"
        painter.setPen(QColor("#00FF9D") if is_brill else QColor("#00F0FF"))
        painter.drawText(badge_rect, Qt.AlignCenter, text)
        painter.restore()
