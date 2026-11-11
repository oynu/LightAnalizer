"""
Automated tests for GameReviewer post-game analysis and accuracy scoring.
"""
import pytest
import chess
from core.engine_manager import EngineManager, EngineConfig
from core.analyzer import ChessAnalyzer
from core.review import GameReviewer

def test_game_review_accuracy_and_critical_moments():
    config = EngineConfig(depth=6, time_limit_sec=0.2, multipv=1)
    engine_mgr = EngineManager(config)
    engine_mgr.start_engine()
    analyzer = ChessAnalyzer()
    reviewer = GameReviewer(engine_mgr, analyzer)

    # 4 plies: 1. e4 e5 2. Qh5 Nf6 (Nf6 blunders pawn e5 or forks)
    board = chess.Board()
    moves = ["e4", "e5", "Qh5", "Nf6"]
    history = []
    for san in moves:
        m = board.parse_san(san)
        history.append((board.copy(), m))
        board.push(m)

    report = reviewer.review_game(history)
    assert len(report.move_reviews) == 4
    assert len(report.eval_curve) == 4
    assert 0.0 <= report.white_accuracy <= 100.0
    assert 0.0 <= report.black_accuracy <= 100.0
    assert any(mr.classification in ["Best", "Excellent", "Good", "Inaccuracy", "Mistake", "Blunder"] for mr in report.move_reviews)

    engine_mgr.stop_engine()
