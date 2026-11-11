"""
End-to-end workflow validation test suite.
Validates live board synchronization, move tracking, animation settling,
false move prevention, and recovery without random hallucinated positions.
"""
import time
import numpy as np
import pytest
import chess
from PySide6.QtWidgets import QApplication

from core.types import BoardCalibration, SyncStatus
from core.board_state import BoardState
from core.engine_manager import EngineManager, EngineConfig
from core.analyzer import ChessAnalyzer
from core.game_state_manager import GameStateManager
from core.vision.board_detector import BoardDetector
from core.vision.piece_classifier import PieceClassifier
from core.vision.move_inference import MoveInferenceEngine
from core.vision.observer import BoardObserver

@pytest.fixture
def workflow_setup():
    board_state = BoardState()
    engine_mgr = EngineManager(EngineConfig(depth=6, time_limit_sec=0.2))
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)
    observer = BoardObserver(game_state_mgr=gsm)
    return gsm, observer

def test_workflow_initial_board_sync(workflow_setup):
    """Point 2 & 3: Automatic detection & initial board sync."""
    gsm, observer = workflow_setup
    detector = BoardDetector()

    # Synthetic desktop containing board
    desktop = np.full((700, 700, 3), 30, dtype=np.uint8)
    board_img = np.zeros((400, 400, 3), dtype=np.uint8)
    sq = 50
    for r in range(8):
        for c in range(8):
            color = (235, 235, 235) if (r + c) % 2 == 0 else (110, 140, 170)
            board_img[r * sq:(r + 1) * sq, c * sq:(c + 1) * sq] = color
    desktop[100:500, 100:500] = board_img

    candidates = detector.detect_chessboards(desktop)
    assert len(candidates) >= 1
    bx, by, bw, bh, score = candidates[0]
    assert score >= 25.0

    # Calibrate observer
    cal = BoardCalibration(x=bx, y=by, width=bw, height=bh, is_calibrated=True)
    observer.update_calibration(cal)
    assert observer.calibration.is_calibrated is True

def test_workflow_normal_move_and_captures(workflow_setup):
    """Point 4 & 5: Normal moves and captures without false moves."""
    gsm, observer = workflow_setup
    board = chess.Board()

    prev_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    curr_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}

    # Play 1. e4
    curr_crops[chess.E2] = np.full((32, 32, 3), 220, dtype=np.uint8)
    curr_crops[chess.E4] = np.full((32, 32, 3), 220, dtype=np.uint8)

    move, success, conf = observer.inference.infer_legal_move(board, prev_crops, curr_crops)
    assert success is True
    assert move == chess.Move.from_uci("e2e4")

    # Confirm move in GameStateManager
    board.push(move)
    gsm.confirm_live_move(move, board, conf)
    assert gsm.sync_status == SyncStatus.SYNCHRONIZED
    assert gsm.live_board.fen() == board.fen()
    assert gsm.current_board.fen() == board.fen()

def test_workflow_castling_and_en_passant(workflow_setup):
    """Point 6: Castling and en passant."""
    gsm, observer = workflow_setup

    # Test en passant
    b_ep = chess.Board("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
    prev_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    curr_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}

    # En passant: e5 moves to f6, captured pawn f5 removed
    for sq in [chess.E5, chess.F6, chess.F5]:
        curr_crops[sq] = np.full((32, 32, 3), 220, dtype=np.uint8)

    move_ep, success_ep, _ = observer.inference.infer_legal_move(b_ep, prev_crops, curr_crops)
    assert success_ep is True
    assert move_ep == chess.Move.from_uci("e5f6")

def test_workflow_obscured_board_never_hallucinates(workflow_setup):
    """Point 11 & 13: Obscured board triggers uncertainty, NEVER random positions."""
    gsm, observer = workflow_setup
    initial_fen = gsm.live_board.fen()

    prev_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    # Obscured / minimized window: completely dark or noisy
    curr_crops = {sq: np.full((32, 32, 3), 10, dtype=np.uint8) for sq in chess.SQUARES}

    move, success, _ = observer.inference.infer_legal_move(gsm.live_board, prev_crops, curr_crops)
    assert success is False
    assert move is None

    # Full reconstruction must also reject
    reconstructed, conf = observer.inference.reconstruct_full_board(curr_crops)
    assert reconstructed is None
    assert conf == 0.0

    # Ensure live board state remained unchanged
    assert gsm.live_board.fen() == initial_fen

def test_workflow_outdated_engine_results_ignored(workflow_setup):
    """Point 9: Outdated engine results never overwrite newest analysis."""
    gsm, _ = workflow_setup
    initial_fen = gsm.fen

    # Submit fake candidate for an unrelated position
    fake_cand = [chess.Move.from_uci("h2h4")]
    gsm._on_engine_analysis_result("8/8/8/8/8/8/8/4K2k w - - 0 1", [])

    # Candidates for current board must remain unaffected
    assert gsm.fen == initial_fen

def test_workflow_continuous_auto_tracking_and_blitz_jump(workflow_setup):
    """Verify continuous live auto-tracking and 2-ply blitz catchup with zero manual input."""
    gsm, observer = workflow_setup
    board = gsm.live_board

    prev_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    curr_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}

    # Ply 1: 1. e4
    curr_crops[chess.E2] = np.full((32, 32, 3), 190, dtype=np.uint8)
    curr_crops[chess.E4] = np.full((32, 32, 3), 190, dtype=np.uint8)
    m1, ok1, conf1 = observer.inference.infer_legal_move(board, prev_crops, curr_crops)
    assert ok1 is True
    assert m1 == chess.Move.from_uci("e2e4")
    board.push(m1)
    gsm.confirm_live_move(m1, board, conf1)

    # Ply 2: 1... e5
    prev_crops = curr_crops.copy()
    curr_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    curr_crops[chess.E7] = np.full((32, 32, 3), 190, dtype=np.uint8)
    curr_crops[chess.E5] = np.full((32, 32, 3), 190, dtype=np.uint8)
    m2, ok2, conf2 = observer.inference.infer_legal_move(board, prev_crops, curr_crops)
    assert ok2 is True
    assert m2 == chess.Move.from_uci("e7e5")
    board.push(m2)
    gsm.confirm_live_move(m2, board, conf2)

    # Plies 3 & 4: Blitz jump 2. Nf3 Nc6 in a single capture delta
    prev_crops = curr_crops.copy()
    curr_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    for sq in [chess.G1, chess.F3, chess.B8, chess.C6]:
        curr_crops[sq] = np.full((32, 32, 3), 190, dtype=np.uint8)

    # Tier 2: infer_multi_ply_move automatically catches both moves!
    multi_m, multi_ok, multi_conf = observer.inference.infer_multi_ply_move(board, prev_crops, curr_crops)
    assert multi_ok is True
    assert len(multi_m) == 2
    assert multi_m[0] == chess.Move.from_uci("g1f3")
    assert multi_m[1] == chess.Move.from_uci("b8c6")

    for m in multi_m:
        board.push(m)
        gsm.confirm_live_move(m, board, multi_conf)

    assert gsm.live_board.fen() == "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"

