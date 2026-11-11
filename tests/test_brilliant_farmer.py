"""
Unit tests for the Brilliant Farmer (!!) move detection and recommendation system.
Tests competitive sacrifice detection: Greek Gift, Queen sacrifice, Exchange sacrifice,
Minor piece sacrifice, Stalemate desperado, competitive bounds, and candidate reordering.
"""
import pytest
import chess
from core.types import CandidateMove
from core.brilliant_farmer import BrilliantFarmer
from core.game_state_manager import GameStateManager
from core.board_state import BoardState
from core.engine_manager import EngineManager
from core.analyzer import ChessAnalyzer

def test_greek_gift_white_bishop_sacrifice():
    """
    Tests classic Greek Gift sacrifice: White Bishop takes h7 with check (Bxh7+)
    against a castled Black king on g8/h8.
    """
    farmer = BrilliantFarmer()
    # Position before Greek Gift: White has Bd3, Nf3, Qh5 available; Black king on g8, pawn on h7
    board = chess.Board("r1bq1rk1/ppp2ppp/2n1pn2/3p4/2PP4/3BPN2/PP1N1PPP/R2QK2R w KQ - 3 8")
    
    # Candidate moves
    bxh7 = CandidateMove(
        move=chess.Move.from_uci("d3h7"),
        san="Bxh7+",
        rank=2,
        score_cp=180,
        eval_str="+1.8",
        eval_diff=-0.10
    )
    o_o = CandidateMove(
        move=chess.Move.from_uci("e1g1"),
        san="O-O",
        rank=1,
        score_cp=190,
        eval_str="+1.9",
        eval_diff=0.0
    )
    
    processed = farmer.process_candidates(board, [o_o, bxh7])
    
    # Greek Gift sacrifice should be promoted to Rank 1 and flagged as brilliant
    assert len(processed) == 2
    assert processed[0].san == "Bxh7+"
    assert processed[0].rank == 1
    assert processed[0].is_best is True
    assert processed[0].is_brilliant is True
    assert "Greek Gift" in processed[0].brilliant_reason

def test_queen_sacrifice():
    """
    Tests Queen sacrifice into an attacked square leading to mate or winning attack.
    """
    farmer = BrilliantFarmer()
    # White has Qh6, g7 is attacked; Queen sacrifice on g7 or h7
    board = chess.Board("r1b2rk1/pp3ppp/4p3/3pP3/8/2N2Q2/PPP2PPP/R3KB1R w KQ - 0 12")
    
    # Candidate sacrificing Queen on f7 or similar
    qxf7 = CandidateMove(
        move=chess.Move.from_uci("f3f7"),
        san="Qxf7+",
        rank=1,
        score_cp=250,
        eval_str="+2.5",
        eval_diff=0.0
    )
    
    is_brill, reason = farmer.evaluate_move_brilliance(board, qxf7, qxf7)
    assert is_brill is True
    assert "Queen Sacrifice" in reason

def test_rook_exchange_sacrifice():
    """
    Tests Exchange sacrifice: Rook takes Knight/Bishop or undefended square attacked by minor/pawn.
    """
    farmer = BrilliantFarmer()
    # White Rook on e1 takes black knight on e7, defended by black piece
    board = chess.Board("r1bqk2r/ppppnppp/8/8/1b1PP3/8/PP1B1PPP/R2QKB1R w KQkq - 0 1")
    # Rook on c1 / e1
    board = chess.Board("4rk2/1p2nppp/p7/8/3R4/8/PP3PPP/4R1K1 w - - 0 1")
    
    # Rd7 or Rxe7
    rxe7 = CandidateMove(
        move=chess.Move.from_uci("e1e7"),
        san="Rxe7",
        rank=1,
        score_cp=120,
        eval_str="+1.2",
        eval_diff=0.0
    )
    
    is_brill, reason = farmer.evaluate_move_brilliance(board, rxe7, rxe7)
    assert is_brill is True
    assert "Exchange Sacrifice" in reason

def test_quiet_move_not_brilliant():
    """
    Ensures standard developing and quiet moves (e.g. O-O, Nf3, e4) are never marked brilliant.
    """
    farmer = BrilliantFarmer()
    board = chess.Board(chess.STARTING_FEN)
    
    e4 = CandidateMove(
        move=chess.Move.from_uci("e2e4"),
        san="e4",
        rank=1,
        score_cp=35,
        eval_str="+0.35",
        eval_diff=0.0
    )
    
    is_brill, reason = farmer.evaluate_move_brilliance(board, e4, e4)
    assert is_brill is False
    assert reason == ""

def test_overwhelming_advantage_excludes_brilliance():
    """
    When the evaluation is already +15.00 (+1500 cp), giving up material is just converting
    a completely crushed opponent, not a brilliant competitive sacrifice.
    """
    farmer = BrilliantFarmer()
    board = chess.Board("r1bq1rk1/ppp2ppp/2n1pn2/3p4/2PP4/3BPN2/PP1N1PPP/R2QK2R w KQ - 3 8")
    
    bxh7 = CandidateMove(
        move=chess.Move.from_uci("d3h7"),
        san="Bxh7+",
        rank=1,
        score_cp=1500,  # +15.00 pawns
        eval_str="+15.0",
        eval_diff=0.0
    )
    
    is_brill, _ = farmer.evaluate_move_brilliance(board, bxh7, bxh7)
    assert is_brill is False

def test_game_state_manager_brilliant_mode_toggle():
    """
    Tests GameStateManager toggling and candidate updating under brilliant mode.
    """
    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)
    
    assert gsm.brilliant_mode is False
    
    # Toggle on
    active = gsm.toggle_brilliant_mode()
    assert active is True
    assert gsm.brilliant_mode is True
    
    # Toggle off
    active = gsm.toggle_brilliant_mode()
    assert active is False
    assert gsm.brilliant_mode is False
