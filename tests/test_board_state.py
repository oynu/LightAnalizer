"""
Automated tests for BoardState, chess rules, moves, and game history.
"""
import pytest
import chess
from core.board_state import BoardState

def test_initial_starting_position():
    bs = BoardState()
    assert bs.board.fen() == chess.STARTING_FEN
    assert bs.current_ply == 0
    assert bs.total_plies == 0
    assert bs.board.turn == chess.WHITE
    assert not bs.is_game_over()

def test_ordinary_moves_and_captures():
    bs = BoardState()
    assert bs.push_san("e4")
    assert bs.push_san("e5")
    assert bs.push_san("Nf3")
    assert bs.push_san("Nc6")
    assert bs.push_san("d4")
    assert bs.push_san("exd4")  # capture
    assert bs.current_ply == 6
    assert bs.total_plies == 6
    assert bs.board.piece_at(chess.D4).piece_type == chess.PAWN
    assert bs.board.piece_at(chess.D4).color == chess.BLACK

def test_castling_kingside_and_queenside():
    # Test Kingside castling
    bs = BoardState()
    for san in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "O-O"]:
        assert bs.push_san(san)
    assert bs.board.piece_at(chess.G1).piece_type == chess.KING
    assert bs.board.piece_at(chess.F1).piece_type == chess.ROOK

    # Test Queenside castling from custom FEN
    fen_queenside = "r3k2r/pppq1ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPPQ1PPP/R3K2R w KQkq - 0 8"
    bs_q = BoardState(fen_queenside)
    assert bs_q.push_san("O-O-O")
    assert bs_q.board.piece_at(chess.C1).piece_type == chess.KING
    assert bs_q.board.piece_at(chess.D1).piece_type == chess.ROOK

def test_en_passant():
    fen_ep = "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3"
    bs = BoardState(fen_ep)
    assert bs.push_san("exf6")
    assert bs.board.piece_at(chess.F6).piece_type == chess.PAWN
    assert bs.board.piece_at(chess.F5) is None  # Captured pawn removed

def test_pawn_promotion():
    fen_promo = "8/4P3/8/8/8/8/8/4K2k w - - 0 1"
    bs = BoardState(fen_promo)
    assert bs.push_san("e8=Q")
    assert bs.board.piece_at(chess.E8).piece_type == chess.QUEEN

def test_check_and_checkmate():
    # Scholar's mate
    bs = BoardState()
    for san in ["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6", "Qxf7#"]:
        assert bs.push_san(san)
    assert bs.board.is_checkmate()
    assert bs.is_game_over()
    assert bs.game_result() == "1-0"

def test_stalemate():
    fen_stalemate = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
    bs = BoardState(fen_stalemate)
    assert bs.board.is_stalemate()
    assert bs.is_game_over()
    assert bs.game_result() == "1/2-1/2"

def test_threefold_repetition():
    bs = BoardState()
    moves = [
        "Nf3", "Nf6", "Ng1", "Ng8",
        "Nf3", "Nf6", "Ng1", "Ng8"
    ]
    for m in moves:
        bs.push_san(m)
    assert bs.board.can_claim_threefold_repetition()

def test_navigation_and_stepping():
    bs = BoardState()
    for m in ["e4", "e5", "Nf3", "Nc6"]:
        bs.push_san(m)
    assert bs.current_ply == 4

    assert bs.step_backward()
    assert bs.current_ply == 3
    assert bs.board.turn == chess.BLACK

    assert bs.step_forward()
    assert bs.current_ply == 4

    bs.go_to_start()
    assert bs.current_ply == 0
    assert bs.board.fen() == chess.STARTING_FEN

    bs.go_to_end()
    assert bs.current_ply == 4

def test_pgn_import_export():
    pgn_sample = """[Event "Test Match"]
[Site "Local"]
[Date "2026.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O 1-0"""
    bs = BoardState()
    assert bs.load_pgn(pgn_sample)
    assert bs.headers["White"] == "Player1"
    assert bs.headers["Black"] == "Player2"
    assert bs.total_plies == 9
    exported = bs.export_pgn()
    assert "Bb5" in exported
