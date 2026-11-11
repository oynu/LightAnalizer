"""
Automated tests for EngineManager, Stockfish UCI communication, MultiPV, and cancellation.
"""
import time
import pytest
import chess
from core.engine_manager import EngineManager, EngineConfig

def test_engine_initialization_and_multipv():
    config = EngineConfig(depth=8, time_limit_sec=1.0, multipv=3)
    mgr = EngineManager(config)
    
    assert mgr.start_engine()
    assert mgr.is_running()

    # Analyze starting position
    board = chess.Board()
    results = []

    def callback(fen, candidates):
        results.extend(candidates)

    mgr.add_result_callback(callback)
    mgr.request_analysis(board)

    # Wait for asynchronous completion
    for _ in range(50):
        if results:
            break
        time.sleep(0.1)

    assert len(results) >= 2
    # Verify candidates
    cand1 = results[0]
    cand2 = results[1]
    assert cand1.rank == 1
    assert cand1.is_best is True
    assert cand2.rank == 2
    assert cand2.is_best is False
    assert cand1.san != ""
    assert cand1.eval_str != ""
    assert cand1.eval_diff == 0.0

    mgr.stop_engine()
    assert not mgr.is_running()

def test_search_cancellation():
    config = EngineConfig(depth=14, time_limit_sec=3.0, multipv=3)
    mgr = EngineManager(config)
    mgr.start_engine()

    board = chess.Board()
    search_id_1 = mgr.request_analysis(board)

    # Quickly cancel by requesting a new position
    board2 = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    search_id_2 = mgr.request_analysis(board2)

    assert search_id_2 > search_id_1

    mgr.stop_engine()
