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
from PySide6.QtCore import Qt, QPointF, QRectF, QRect, QTimer
import time
from ui.widgets.neon_fx import draw_premium_arrow, draw_sniper_scope, draw_glass_pill
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
        self._brilliant_count = 0
        self._show_badge = True
        self._calibration: Optional[BoardCalibration] = None

        # Gentle 25fps animation clock for the sniper scopes (only runs while moves are shown)
        self._fx_phase = 0.0
        self._fx_t0 = time.monotonic()
        self._fx_timer = QTimer(self)
        self._fx_timer.setInterval(40)
        self._fx_timer.timeout.connect(self._tick_fx)

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

    def _tick_fx(self) -> None:
        self._fx_phase = time.monotonic() - self._fx_t0
        if self._candidate_moves and self.isVisible():
            self.update()

    def hideEvent(self, event) -> None:
        self._fx_timer.stop()
        super().hideEvent(event)

    def set_candidate_moves(self, candidates: List[CandidateMove]) -> None:
        """Updates the candidate moves to display on screen."""
        self._candidate_moves = candidates
        if candidates and self.isVisible() and not self._fx_timer.isActive():
            self._fx_timer.start()
        self.update()

    def set_brilliant_count(self, count: int) -> None:
        """Updates the count of brilliant moves farmed in this match."""
        self._brilliant_count = count
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_os_clickthrough_and_capture_exclusion()
        if self._candidate_moves:
            self._fx_timer.start()

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

        # Whisper-thin neon frame hugging the board perimeter
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(0, 240, 255, 26), 4.0))
        painter.drawRoundedRect(QRectF(bx + 2, by + 2, b_size - 4, b_size - 4), 8, 8)
        painter.setPen(QPen(QColor(0, 240, 255, 78), 1.2))
        painter.drawRoundedRect(QRectF(bx + 1.5, by + 1.5, b_size - 3, b_size - 3), 7, 7)

        # On-screen match brilliant counter - glass pill in the top-right corner
        if getattr(self, "_brilliant_count", 0) > 0:
            pill_rect = QRectF(bx + b_size - 138, by + 8, 130, 26)
            font_cnt = QFont("JetBrains Mono", 9, QFont.Bold)
            font_cnt.setStyleHint(QFont.Monospace)
            draw_glass_pill(
                painter, pill_rect, QColor("#00FF9D"),
                f"💎 {self._brilliant_count} Farmed !!", font_cnt, QColor("#00FF9D")
            )

        # Candidate moves: arrows (rank 3 -> 1 so the best sits on top), then sniper scopes on targets
        base_colors = [QColor("#00F0FF"), QColor("#A855F7"), QColor("#FFB800")]
        scope_scales = [1.0, 0.86, 0.74]

        cands = self._candidate_moves[:3]
        drawn = []
        for idx in reversed(range(len(cands))):
            cand = cands[idx]
            color = QColor("#00FF9D") if getattr(cand, "is_brilliant", False) else base_colors[idx]
            drawn.append((idx, cand, color))
            self._draw_neon_arrow(
                painter,
                cand.move.from_square,
                cand.move.to_square,
                bx, by, sq_size,
                color,
                scale_mult=1.12 if idx == 0 else 0.92,
                rank=idx + 1
            )

        for idx, cand, color in drawn:
            c2, r2 = self._square_to_coords(cand.move.to_square)
            center = QPointF(bx + c2 * sq_size + sq_size / 2.0, by + r2 * sq_size + sq_size / 2.0)
            draw_sniper_scope(
                painter, center, sq_size, color,
                phase=self._fx_phase + idx * 0.7,
                scale=scope_scales[idx],
                opacity=1.0 if idx == 0 else 0.85,
                lock_on=(idx == 0),
                spin_dir=1.0 if idx % 2 == 0 else -1.0
            )

        # Recommendation badge for the #1 move
        if self._show_badge and cands:
            self._draw_best_move_badge(painter, cands[0], bx, by, sq_size)

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
        p1 = QPointF(bx + c1 * sq_size + sq_size / 2.0, by + r1 * sq_size + sq_size / 2.0)
        p2 = QPointF(bx + c2 * sq_size + sq_size / 2.0, by + r2 * sq_size + sq_size / 2.0)
        scope_scale = (1.0, 0.86, 0.74)[max(0, min(2, rank - 1))]
        draw_premium_arrow(
            painter, p1, p2, sq_size, color,
            scale=scale_mult, opacity=1.0, scope_scale=scope_scale
        )

    def _draw_best_move_badge(
        self,
        painter: QPainter,
        cand: CandidateMove,
        bx: float,
        by: float,
        sq_size: float
    ) -> None:
        """Floating glass capsule with the recommended SAN move and eval, anchored above the scope."""
        c2, r2 = self._square_to_coords(cand.move.to_square)
        tx = bx + (c2 * sq_size) + (sq_size / 2.0)
        ty = by + (r2 * sq_size) + (sq_size / 2.0)

        is_brill = getattr(cand, "is_brilliant", False)
        badge_w = max(122.0 if is_brill else 96.0, sq_size * (1.55 if is_brill else 1.3))
        badge_h = 26.0
        badge_x = min(max(tx - (badge_w / 2.0), bx + 4), bx + sq_size * 8 - badge_w - 4)
        badge_y = ty - (sq_size * 0.62) - badge_h
        if badge_y < by + 4:
            badge_y = ty + (sq_size * 0.62)

        accent = QColor("#00FF9D") if is_brill else QColor("#00F0FF")
        font = QFont("JetBrains Mono", 10, QFont.Bold)
        font.setStyleHint(QFont.Monospace)
        text = f"💎 !! {cand.san}  {cand.eval_str}" if is_brill else f"★ {cand.san}  {cand.eval_str}"
        draw_glass_pill(painter, QRectF(badge_x, badge_y, badge_w, badge_h), accent, text, font, accent)
