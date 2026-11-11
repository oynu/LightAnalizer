"""
Tests for GambitsAndTraps database, opening trap detection, and MouseMoveController.
"""
import pytest
import chess
from core.gambits import GambitsAndTraps
from core.brilliant_farmer import BrilliantFarmer
from core.mouse_controller import MouseMoveController
from core.types import BoardCalibration, CandidateMove

def test_evans_gambit_detection():
    """1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 -> 4. b4! (Evans Gambit)"""
    gt = GambitsAndTraps()
    board = chess.Board()
    for move in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"]:
        board.push_san(move)

    match = gt.find_gambit_or_trap(board)
    assert match is not None
    move, name, sac_type, idea = match
    assert move == chess.Move.from_uci("b2b4")
    assert name == "Evans Gambit"
    assert "Pawn Sacrifice" in sac_type

def test_smith_morra_gambit_detection():
    """1. e4 c5 2. d4 cxd4 -> 3. c3! (Smith-Morra)"""
    gt = GambitsAndTraps()
    board = chess.Board()
    for move in ["e4", "c5", "d4", "cxd4"]:
        board.push_san(move)

    match = gt.find_gambit_or_trap(board)
    assert match is not None
    move, name, _, _ = match
    assert move == chess.Move.from_uci("c2c3")
    assert "Smith-Morra" in name

def test_fried_liver_knight_sacrifice_detection():
    """1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 -> 6. Nxf7!"""
    gt = GambitsAndTraps()
    board = chess.Board()
    for move in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "Ng5", "d5", "exd5", "Nxd5"]:
        board.push_san(move)

    match = gt.find_gambit_or_trap(board)
    assert match is not None
    move, name, sac_type, _ = match
    assert move == chess.Move.from_uci("g5f7")
    assert "Fried Liver" in name
    assert "Knight Sacrifice" in sac_type

def test_stafford_gambit_detection():
    """1. e4 e5 2. Nf3 Nf6 3. Nxe5 -> 3... Nc6! (Stafford)"""
    gt = GambitsAndTraps()
    board = chess.Board()
    for move in ["e4", "e5", "Nf3", "Nf6", "Nxe5"]:
        board.push_san(move)

    match = gt.find_gambit_or_trap(board)
    assert match is not None
    move, name, _, _ = match
    assert move == chess.Move.from_uci("b8c6")
    assert "Stafford" in name

def test_brilliant_farmer_promotes_gambit():
    """Verify BrilliantFarmer process_candidates elevates Evans Gambit to Rank 1 as Brilliant."""
    farmer = BrilliantFarmer()
    board = chess.Board()
    for move in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"]:
        board.push_san(move)

    # Candidate moves where Stockfish only suggested quiet moves (e.g. d3, O-O)
    d3 = CandidateMove(
        move=chess.Move.from_uci("d2d3"),
        san="d3",
        rank=1,
        score_cp=40,
        eval_str="+0.4",
        eval_diff=0.0
    )
    o_o = CandidateMove(
        move=chess.Move.from_uci("e1g1"),
        san="O-O",
        rank=2,
        score_cp=35,
        eval_str="+0.35",
        eval_diff=-0.05
    )

    processed = farmer.process_candidates(board, [d3, o_o])
    assert len(processed) >= 2
    # Evans Gambit b4 must be injected and promoted to Rank 1!
    top = processed[0]
    assert top.san == "b4"
    assert top.rank == 1
    assert top.is_best is True
    assert top.is_brilliant is True
    assert "Evans Gambit" in top.brilliant_reason

def test_mouse_controller_coordinates():
    """Test screen coordinate calculation for white and black board perspectives."""
    mc = MouseMoveController()
    cal_white = BoardCalibration(
        x=100,
        y=100,
        width=800,
        height=800,
        orientation_white_bottom=True,
        is_calibrated=True
    )
    # e2 square: file e (4), rank 2 (1).
    # col = 4, row = 7 - 1 = 6.
    # center_x = 100 + 4*100 + 50 = 550
    # center_y = 100 + 6*100 + 50 = 750
    x, y = mc.get_square_coords(cal_white, chess.E2)
    assert x == 550
    assert y == 750

    # e4 square: file e (4), rank 4 (3).
    # col = 4, row = 7 - 3 = 4.
    # center_x = 550, center_y = 100 + 4*100 + 50 = 550
    x4, y4 = mc.get_square_coords(cal_white, chess.E4)
    assert x4 == 550
    assert y4 == 550

    # Test Black at bottom
    cal_black = BoardCalibration(
        x=0,
        y=0,
        width=800,
        height=800,
        orientation_white_bottom=False,
        is_calibrated=True
    )
    # In Black perspective, e8 (file 4, rank 7) is at col = 7 - 4 = 3, row = 7.
    bx, by = mc.get_square_coords(cal_black, chess.E8)
    assert bx == 350
    assert by == 750

def test_mouse_controller_normalized_coords():
    """Test normalized 0..65535 coordinate conversion."""
    mc = MouseMoveController()
    norm_x, norm_y = mc._to_normalized_coords(0, 0)
    assert 0 <= norm_x <= 65535
    assert 0 <= norm_y <= 65535

def test_mouse_controller_rejects_uncalibrated():
    """MouseMoveController must reject execution if board is not calibrated."""
    mc = MouseMoveController()
    uncal = BoardCalibration(is_calibrated=False)
    res = mc.execute_move_async(uncal, chess.Move.from_uci("e2e4"))
    assert res is False

