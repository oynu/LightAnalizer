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
        board_rect = QRectF(bx, by, b_size, b_size)

        # 1. Background board container - deep obsidian
        painter.fillRect(self.rect(), QColor("#080B12"))

        # Clip board squares to a sleek 12px squircle
        painter.save()
        board_clip = QPainterPath()
        board_clip.addRoundedRect(board_rect, 12, 12)
        painter.setClipPath(board_clip)

        # 2. Draw Squares - High-contrast crystal clear ivory cream and rich green
        light_color = QColor("#EBECD0")
        dark_color = QColor("#779956")
        last_move_fill = QColor(168, 85, 247, 95)
        last_move_border = QColor(168, 85, 247, 230)
        selected_fill = QColor(0, 240, 255, 95)
        selected_border = QColor(0, 240, 255, 230)

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

                # Last move highlight - Neon Violet wash + inner border
                if self._last_move and sq in [self._last_move.from_square, self._last_move.to_square]:
                    painter.fillRect(rect, last_move_fill)
                    painter.setPen(QPen(last_move_border, 1.5))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(rect.adjusted(0.75, 0.75, -0.75, -0.75))

                # Live move synchronization flash - Neon Emerald
                if sq in self._flash_squares and self._flash_alpha > 0:
                    painter.fillRect(rect, QColor(0, 255, 157, self._flash_alpha))

                # Selected square highlight - Neon Cyan wash + inner border
                if self._selected_square == sq:
                    painter.fillRect(rect, selected_fill)
                    painter.setPen(QPen(selected_border, 1.5))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(rect.adjusted(0.75, 0.75, -0.75, -0.75))

        # 4. Draw Pieces inside the clipped squircle
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
            hint_color = QColor(0, 240, 255, 190)   # Neon Cyan
            capture_color = QColor(255, 42, 133, 190) # Neon Rose

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

        painter.restore()

        # Specular glass border outline around board container
        specular_pen = QPen(QColor(255, 255, 255, 45), 1.5)
        painter.setPen(specular_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(board_rect, 12, 12)

        # 3. Draw Coordinates
        if self._show_coordinates:
            font = QFont("Segoe UI Variable Display", int(max(9, sq_size * 0.18)), QFont.Bold)
            font.setStyleHint(QFont.SansSerif)
            painter.setFont(font)
            coord_pen = QPen(QColor("#94A3B8"))
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

        # 6. Draw Candidate Move Arrows
        if self._show_arrows and self._candidate_moves:
            base_colors = [
                QColor("#00F0FF"),   # 1st: Electric Cyan
                QColor("#A855F7"),   # 2nd: Neon Violet
                QColor("#FFB800")    # 3rd: Neon Amber
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
                    color.setAlpha(120)
                    scale = 0.85
                else:
                    color.setAlpha(235)
                    scale = 1.05

                self._draw_arrow(painter, cand.move.from_square, cand.move.to_square, bx, by, sq_size, color, scale_mult=scale, glow=True)

        # 7. Draw Threat Arrows - Neon Rose
        if self._show_arrows and self._threat_arrows:
            threat_color = QColor(255, 42, 133, 220)
            for from_sq, to_sq in self._threat_arrows:
                self._draw_arrow(painter, from_sq, to_sq, bx, by, sq_size, threat_color, glow=True)

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
        shaft_width = max(4.5, sq_size * 0.12) * scale_mult
        head_length = sq_size * 0.40 * scale_mult
        head_width = sq_size * 0.38 * scale_mult

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
        r_outer = shaft_width * 1.4
        r_inner = shaft_width * 0.70
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 60)))
        painter.drawEllipse(QPointF(x1, y1), r_outer, r_outer)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(x1, y1), r_inner, r_inner)
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.drawEllipse(QPointF(x1, y1), r_inner * 0.4, r_inner * 0.4)

        # 2. Shaft - Multi-layer neon laser beam
        # Pass 1: Soft ambient bloom halo
        bloom_pen = QPen(
            QColor(color.red(), color.green(), color.blue(), 45),
            shaft_width + 10,
            Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin
        )
        painter.setPen(bloom_pen)
        painter.drawLine(QPointF(start_x, start_y), QPointF(base_x, base_y))

        # Pass 2: Radiant neon glow
        glow_pen = QPen(
            QColor(color.red(), color.green(), color.blue(), 110),
            shaft_width + 4,
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
