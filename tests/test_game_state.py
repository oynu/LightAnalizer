"""
Automated tests for GameStateManager authoritative state coordination and engine versioning.
"""
import pytest
import chess
from core.types import SyncStatus, CandidateMove
from core.board_state import BoardState
from core.engine_manager import EngineManager, EngineConfig
from core.analyzer import ChessAnalyzer
from core.game_state_manager import GameStateManager

@pytest.fixture
def gsm():
    board_state = BoardState()
    engine_mgr = EngineManager(EngineConfig(depth=6, time_limit_sec=0.2))
    analyzer = ChessAnalyzer()
    return GameStateManager(board_state, engine_mgr, analyzer)

def test_initial_state(gsm):
    assert gsm.live_board.fen() == chess.STARTING_FEN
    assert gsm.sync_status == SyncStatus.BOARD_UNAVAILABLE
    assert gsm.is_exploring_variation is False
    assert gsm.last_confirmed_move is None

def test_status_transitions(gsm):
    gsm.update_sync_status(SyncStatus.SYNCHRONIZING, "Detecting...")
    assert gsm.sync_status == SyncStatus.SYNCHRONIZING

    gsm.update_sync_status(SyncStatus.POSITION_UNCERTAIN, "Ambiguous", rejection_reason="Noisy frame")
    assert gsm.sync_status == SyncStatus.POSITION_UNCERTAIN
    assert gsm._rejection_reason == "Noisy frame"

def test_confirm_live_move(gsm):
    b = chess.Board()
    m = chess.Move.from_uci("e2e4")
    b.push(m)

    gsm.confirm_live_move(m, b, confidence=0.95)
    assert gsm.sync_status == SyncStatus.SYNCHRONIZED
    assert gsm.live_board.fen() == b.fen()
    assert gsm.current_board.fen() == b.fen()
    assert gsm.last_confirmed_move == m
    assert gsm.is_exploring_variation is False

def test_user_variation_exploration_and_return_to_live(gsm):
    # Establish live game at move 1. e4
    b_live = chess.Board()
    m_e4 = chess.Move.from_uci("e2e4")
    b_live.push(m_e4)
    gsm.confirm_live_move(m_e4, b_live, confidence=0.95)

    # User plays an experimental analysis move on the board
    m_e5 = chess.Move.from_uci("e7e5")
    gsm.user_played_analysis_move(m_e5)

    assert gsm.is_exploring_variation is True
    assert gsm.current_board.fen() != gsm.live_board.fen()

    # User clicks 'Return to Live Game'
    gsm.return_to_live_game()
    assert gsm.is_exploring_variation is False
    assert gsm.current_board.fen() == gsm.live_board.fen()

def test_stale_engine_results_discarded(gsm):
    # If engine returns analysis for an outdated FEN, it must be ignored
    outdated_fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    fake_cand = [CandidateMove(move=chess.Move.from_uci("g1f3"), san="Nf3", rank=1, is_best=True)]

    # Board is on starting position, not outdated_fen
    gsm._on_engine_analysis_result(outdated_fen, fake_cand)

    # Latest candidates must remain empty / unaffected
    assert len(gsm.candidates) == 0
