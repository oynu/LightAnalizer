"""Smoke tests for the premium neon-glass painting primitives (arrows, sniper scope, glass surfaces)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import chess
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from PySide6.QtCore import QPointF, QRectF

from ui.widgets import neon_fx
from ui.widgets.chessboard import ChessboardWidget
from ui.widgets.screen_hud import ScreenBoardOverlay
from core.types import CandidateMove


def _app():
    return QApplication.instance() or QApplication([])


def _painter(w=300, h=300):
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0, 0))
    return img, QPainter(img)


def test_arrow_stops_short_of_target_and_scope_draws():
    _app()
    img, p = _painter()
    sq = 60.0
    neon_fx.draw_premium_arrow(p, QPointF(30, 270), QPointF(270, 30), sq, QColor("#00F0FF"))
    neon_fx.draw_sniper_scope(p, QPointF(270, 30), sq, QColor("#00F0FF"), phase=1.2)
    p.end()
    assert neon_fx.scope_clearance(sq) > sq * 0.4          # visible gap reserved around the target
    assert img.pixelColor(150, 150).alpha() > 0            # shaft painted
    assert img.pixelColor(266, 34).alpha() > 0             # scope painted on the target


def test_adjacent_square_arrow_still_drawn():
    _app()
    img, p = _painter()
    neon_fx.draw_premium_arrow(p, QPointF(100, 150), QPointF(160, 150), 60.0, QColor("#FFB800"))
    p.end()
    assert any(img.pixelColor(x, 150).alpha() > 0 for x in range(105, 150))


def test_glass_helpers_do_not_crash():
    _app()
    img, p = _painter()
    neon_fx.paint_aurora(p, QRectF(0, 0, 300, 300))
    neon_fx.paint_glass_card(p, QRectF(10, 10, 200, 80), 14, QColor("#00F0FF"), glow=True)
    neon_fx.paint_glass_card(p, QRectF(10, 100, 200, 80))
    neon_fx.draw_glass_pill(p, QRectF(10, 200, 120, 26), QColor("#00FF9D"), "x", QFont("Consolas", 9))
    p.end()


def test_board_and_hud_render_with_candidates():
    _app()
    b = chess.Board()
    cands = [CandidateMove(move=m, san=b.san(m), rank=i + 1, score_cp=10, eval_str="+0.1")
             for i, m in enumerate([chess.Move.from_uci(u) for u in ("e2e4", "d2d4", "g1f3")])]
    w = ChessboardWidget(); w.resize(400, 400); w.set_board(b); w.set_candidate_moves(cands)
    assert not w.grab().isNull()
    h = ScreenBoardOverlay(); h.resize(400, 400); h.set_candidate_moves(cands)
    assert not h.grab().isNull()
