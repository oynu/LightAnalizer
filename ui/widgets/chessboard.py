"""
Interactive high-DPI vector chessboard widget.
Renders crisp pieces, rank/file coordinates, legal move hints, and colored candidate arrows.
"""
from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple, Callable, Set
import chess
import chess.svg
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPolygonF,
    QPainterPath
)
from PySide6.QtCore import Qt, QPointF, QRectF, QByteArray, QTimer
from PySide6.QtSvg import QSvgRenderer
from core.types import CandidateMove

class ChessboardWidget(QWidget):
    """
    Renders an 8x8 chessboard with crisp vector pieces, coordinates,
    move highlights, and candidate move arrows.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(120, 120)
        self.setMouseTracking(True)

        self._board = chess.Board()
        self._white_at_bottom = True
        self._selected_square: Optional[chess.Square] = None
        self._legal_moves_for_selected: List[chess.Move] = []
        self._last_move: Optional[chess.Move] = None

        self._candidate_moves: List[CandidateMove] = []
        self._highlighted_candidate_rank: Optional[int] = None
        self._threat_arrows: List[Tuple[chess.Square, chess.Square]] = []
        self._show_coordinates = True
        self._show_legal_moves = True
        self._show_arrows = True
        self._flash_squares: Set[chess.Square] = set()
        self._flash_alpha: int = 0
        self._flash_timer: QTimer = QTimer(self)
        self._flash_timer.setInterval(25)
        self._flash_timer.timeout.connect(self._step_flash)

        self._piece_renderers: Dict[Tuple[chess.PieceType, chess.Color], QSvgRenderer] = {}
        self._init_piece_renderers()

        self._on_move_made: Optional[Callable[[chess.Move], None]] = None

    def _init_piece_renderers(self) -> None:
        """Pre-initializes QSvgRenderer for all 12 piece types."""
        piece_types = [
            chess.PAWN, chess.KNIGHT, chess.BISHOP,
            chess.ROOK, chess.QUEEN, chess.KING
        ]
        for color in [chess.WHITE, chess.BLACK]:
            for pt in piece_types:
                p = chess.Piece(pt, color)
                svg_xml = chess.svg.piece(p, size=120)
                renderer = QSvgRenderer(QByteArray(svg_xml.encode('utf-8')))
                self._piece_renderers[(pt, color)] = renderer

    def set_on_move_made(self, cb: Callable[[chess.Move], None]) -> None:
        self._on_move_made = cb

    def set_board(self, board: chess.Board, last_move: Optional[chess.Move] = None) -> None:
        self._board = board.copy()
        self._selected_square = None
        self._legal_moves_for_selected = []
        self._last_move = last_move
        self.update()

    def set_candidate_moves(self, candidates: List[CandidateMove]) -> None:
        self._candidate_moves = candidates
        self.update()

    def set_highlighted_candidate_rank(self, rank: Optional[int]) -> None:
        if self._highlighted_candidate_rank != rank:
            self._highlighted_candidate_rank = rank
            self.update()

    def flash_move(self, from_sq: chess.Square, to_sq: chess.Square) -> None:
        self._flash_squares = {from_sq, to_sq}
        self._flash_alpha = 180
        if self._flash_timer is not None:
            self._flash_timer.start()
        self.update()

    def _step_flash(self) -> None:
        self._flash_alpha = max(0, self._flash_alpha - 20)
        if self._flash_alpha <= 0:
            if self._flash_timer:
                self._flash_timer.stop()
            self._flash_squares.clear()
        self.update()

    def toggle_coordinates(self) -> bool:
        self._show_coordinates = not self._show_coordinates
        self.update()
        return self._show_coordinates

    def toggle_legal_moves(self) -> bool:
        self._show_legal_moves = not self._show_legal_moves
        self.update()
        return self._show_legal_moves

    def toggle_arrows(self) -> bool:
        self._show_arrows = not self._show_arrows
        self.update()
        return self._show_arrows

    def set_threat_arrows(self, threats: List[Tuple[chess.Square, chess.Square]]) -> None:
        self._threat_arrows = threats
        self.update()

    def flip_orientation(self) -> None:
        self._white_at_bottom = not self._white_at_bottom
        self.update()

    def is_white_at_bottom(self) -> bool:
        return self._white_at_bottom

    def set_white_at_bottom(self, val: bool) -> None:
        if self._white_at_bottom != val:
            self._white_at_bottom = val
            self.update()

    def _get_board_geometry(self) -> Tuple[float, float, float, float]:
        """Returns (margin_x, margin_y, board_size, square_size) maintaining 1:1 aspect ratio."""
        w = self.width()
        h = self.height()
        margin = 18.0 if self._show_coordinates else 0.0
        avail_w = w - (margin * 2)
        avail_h = h - (margin * 2)
        board_size = max(100.0, min(avail_w, avail_h))
        sq_size = board_size / 8.0
        bx = (w - board_size) / 2.0
        by = (h - board_size) / 2.0
        return bx, by, board_size, sq_size

    def _square_to_coords(self, sq: chess.Square) -> Tuple[int, int]:
        """Returns (col, row) on screen (0..7, 0..7) based on orientation."""
        file_idx = chess.square_file(sq)
        rank_idx = chess.square_rank(sq)

        if self._white_at_bottom:
            col = file_idx
            row = 7 - rank_idx
        else:
            col = 7 - file_idx
            row = rank_idx
        return col, row

    def _coords_to_square(self, col: int, row: int) -> Optional[chess.Square]:
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        if self._white_at_bottom:
            file_idx = col
            rank_idx = 7 - row
        else:
            file_idx = 7 - col
            rank_idx = row
        return chess.square(file_idx, rank_idx)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        bx, by, b_size, sq_size = self._get_board_geometry()

        # 1. Background board container
        painter.fillRect(self.rect(), QColor("#121316"))

        # 2. Draw Squares
        light_color = QColor("#D1D5DB")
        dark_color = QColor("#4B5563")
        last_move_color = QColor(253, 224, 71, 75)
        selected_color = QColor(56, 189, 248, 100)

        for col in range(8):
            for row in range(8):
                sq = self._coords_to_square(col, row)
                if sq is None:
                    continue

                x = bx + (col * sq_size)
                y = by + (row * sq_size)
                rect = QRectF(x, y, sq_size, sq_size)

                # Base square color
                is_light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 != 0
                painter.fillRect(rect, light_color if is_light else dark_color)

                # Last move highlight
                if self._last_move and sq in [self._last_move.from_square, self._last_move.to_square]:
                    painter.fillRect(rect, last_move_color)

                # Live move synchronization flash
                if sq in self._flash_squares and self._flash_alpha > 0:
                    painter.fillRect(rect, QColor(52, 211, 153, self._flash_alpha))

                # Selected square highlight
                if self._selected_square == sq:
                    painter.fillRect(rect, selected_color)

        # 3. Draw Coordinates
        if self._show_coordinates:
            font = QFont("Segoe UI", int(max(9, sq_size * 0.18)), QFont.Bold)
            painter.setFont(font)
            coord_pen = QPen(QColor("#9CA3AF"))
            painter.setPen(coord_pen)

            files = ["a", "b", "c", "d", "e", "f", "g", "h"] if self._white_at_bottom else ["h", "g", "f", "e", "d", "c", "b", "a"]
            ranks = ["8", "7", "6", "5", "4", "3", "2", "1"] if self._white_at_bottom else ["1", "2", "3", "4", "5", "6", "7", "8"]

            # Files along bottom
            for col, f_txt in enumerate(files):
                x = bx + (col * sq_size)
                y = by + b_size + 14
                painter.drawText(QRectF(x, y - 10, sq_size, 20), Qt.AlignCenter, f_txt)

            # Ranks along left
            for row, r_txt in enumerate(ranks):
                x = bx - 18
                y = by + (row * sq_size)
                painter.drawText(QRectF(x, y, 16, sq_size), Qt.AlignCenter, r_txt)

        # 4. Draw Pieces
        for sq in chess.SQUARES:
            piece = self._board.piece_at(sq)
            if piece:
                col, row = self._square_to_coords(sq)
                x = bx + (col * sq_size)
                y = by + (row * sq_size)
                renderer = self._piece_renderers.get((piece.piece_type, piece.color))
                if renderer:
                    padding = sq_size * 0.05
                    piece_rect = QRectF(x + padding, y + padding, sq_size - (padding * 2), sq_size - (padding * 2))
                    renderer.render(painter, piece_rect)

        # 5. Draw Legal Move Hints
        if self._show_legal_moves and self._selected_square is not None:
            painter.setPen(Qt.NoPen)
            hint_color = QColor(16, 185, 129, 140)
            capture_color = QColor(239, 68, 68, 140)

            for m in self._legal_moves_for_selected:
                to_sq = m.to_square
                c_idx, r_idx = self._square_to_coords(to_sq)
                cx = bx + (c_idx * sq_size) + (sq_size / 2.0)
                cy = by + (r_idx * sq_size) + (sq_size / 2.0)

                if self._board.piece_at(to_sq) or self._board.is_en_passant(m):
                    # Capture ring
                    painter.setBrush(Qt.NoBrush)
                    pen = QPen(capture_color, max(2.5, sq_size * 0.08))
                    painter.setPen(pen)
                    radius = sq_size * 0.40
                    painter.drawEllipse(QPointF(cx, cy), radius, radius)
                else:
                    # Move dot
                    painter.setBrush(QBrush(hint_color))
                    painter.setPen(Qt.NoPen)
                    dot_radius = sq_size * 0.16
                    painter.drawEllipse(QPointF(cx, cy), dot_radius, dot_radius)

        # 6. Draw Candidate Move Arrows
        if self._show_arrows and self._candidate_moves:
            base_colors = [
                QColor(16, 185, 129),   # 1st: Emerald
                QColor(59, 130, 246),   # 2nd: Blue
                QColor(245, 158, 11)    # 3rd: Amber
            ]
            for idx, cand in enumerate(self._candidate_moves[:3]):
                rank = idx + 1
                color = QColor(base_colors[idx])
                is_hovered = (self._highlighted_candidate_rank == rank)
                has_hover = (self._highlighted_candidate_rank is not None)

                if is_hovered:
                    color.setAlpha(255)
                    scale = 1.35
                elif has_hover:
                    color.setAlpha(65)
                    scale = 0.85
                else:
                    color.setAlpha(210)
                    scale = 1.0

                self._draw_arrow(painter, cand.move.from_square, cand.move.to_square, bx, by, sq_size, color, scale_mult=scale, glow=is_hovered)

        # 7. Draw Threat Arrows
        if self._show_arrows and self._threat_arrows:
            threat_color = QColor(239, 68, 68, 190)
            for from_sq, to_sq in self._threat_arrows:
                self._draw_arrow(painter, from_sq, to_sq, bx, by, sq_size, threat_color)

        painter.end()

    def _draw_arrow(
        self,
        painter: QPainter,
        from_sq: chess.Square,
        to_sq: chess.Square,
        bx: float,
        by: float,
        sq_size: float,
        color: QColor,
        scale_mult: float = 1.0,
        glow: bool = False
    ) -> None:
        c1, r1 = self._square_to_coords(from_sq)
        c2, r2 = self._square_to_coords(to_sq)

        x1 = bx + (c1 * sq_size) + (sq_size / 2.0)
        y1 = by + (r1 * sq_size) + (sq_size / 2.0)
        x2 = bx + (c2 * sq_size) + (sq_size / 2.0)
        y2 = by + (r2 * sq_size) + (sq_size / 2.0)

        angle = math.atan2(y2 - y1, x2 - x1)
        shaft_width = max(3.5, sq_size * 0.10) * scale_mult
        head_length = sq_size * 0.32 * scale_mult
        head_width = sq_size * 0.30 * scale_mult

        # Shorten destination slightly so tip centers cleanly on destination square
        tip_x = x2 - math.cos(angle) * (sq_size * 0.15)
        tip_y = y2 - math.sin(angle) * (sq_size * 0.15)

        base_x = tip_x - math.cos(angle) * head_length
        base_y = tip_y - math.sin(angle) * head_length

        painter.save()

        if glow:
            glow_pen = QPen(QColor(color.red(), color.green(), color.blue(), 75), shaft_width + 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(glow_pen)
            painter.drawLine(QPointF(x1, y1), QPointF(base_x, base_y))

        pen = QPen(color, shaft_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(QPointF(x1, y1), QPointF(base_x, base_y))

        # Arrow head polygon
        left_x = base_x + math.sin(angle) * (head_width / 2.0)
        left_y = base_y - math.cos(angle) * (head_width / 2.0)
        right_x = base_x - math.sin(angle) * (head_width / 2.0)
        right_y = base_y + math.cos(angle) * (head_width / 2.0)

        arrow_head = QPolygonF([
            QPointF(tip_x, tip_y),
            QPointF(left_x, left_y),
            QPointF(right_x, right_y)
        ])
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(arrow_head)
        painter.restore()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return

        bx, by, b_size, sq_size = self._get_board_geometry()
        pos = event.position()
        mx, my = pos.x(), pos.y()

        col = int((mx - bx) // sq_size)
        row = int((my - by) // sq_size)
        sq = self._coords_to_square(col, row)

        if sq is None:
            self._selected_square = None
            self._legal_moves_for_selected = []
            self.update()
            return

        if self._selected_square is None:
            # Select piece if it belongs to side to move
            piece = self._board.piece_at(sq)
            if piece and piece.color == self._board.turn:
                self._selected_square = sq
                self._legal_moves_for_selected = [
                    m for m in self._board.legal_moves if m.from_square == sq
                ]
                self.update()
        else:
            # Try to make move
            move_candidate = None
            for m in self._legal_moves_for_selected:
                if m.to_square == sq:
                    move_candidate = m
                    break

            if move_candidate:
                if self._on_move_made:
                    self._on_move_made(move_candidate)
                self._selected_square = None
                self._legal_moves_for_selected = []
                self.update()
            else:
                # Re-select if clicking another piece of same turn
                piece = self._board.piece_at(sq)
                if piece and piece.color == self._board.turn:
                    self._selected_square = sq
                    self._legal_moves_for_selected = [
                        m for m in self._board.legal_moves if m.from_square == sq
                    ]
                else:
                    self._selected_square = None
                    self._legal_moves_for_selected = []
                self.update()
