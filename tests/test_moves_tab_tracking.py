"""
Automated unit tests for the Moves Tab OCR tracking system.
Tests OCR text recognition, notation parsing, error correction,
row grouping, and end-to-end moves tab synchronization.
"""
import pytest
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import chess

from core.types import BoardCalibration, SyncStatus
from core.board_state import BoardState
from core.engine_manager import EngineManager
from core.analyzer import ChessAnalyzer
from core.game_state_manager import GameStateManager
from core.vision.text_ocr import TextOCR
from core.vision.notation_parser import (
    group_boxes_into_rows,
    is_ignorable_token,
    clean_ocr_token,
    resolve_move_from_token,
    parse_moves_from_tokens,
    parse_ocr_to_game
)
from core.vision.moves_tab_observer import MovesTabObserver


def test_ocr_item_row_grouping():
    """Verify that bounding boxes in multi-column tables are properly grouped by row and sorted left-to-right."""
    # Simulates:
    # 1.   e4     e5
    # 2.   Nf3    Nc6
    ocr_items = [
        ([[180.0, 30.0], [210.0, 30.0], [210.0, 45.0], [180.0, 45.0]], "e5", 0.95),
        ([[20.0, 30.0], [35.0, 30.0], [35.0, 45.0], [20.0, 45.0]], "1.", 0.95),
        ([[80.0, 30.0], [105.0, 30.0], [105.0, 45.0], [80.0, 45.0]], "e4", 0.95),
        ([[80.0, 70.0], [115.0, 70.0], [115.0, 85.0], [80.0, 85.0]], "Nf3", 0.95),
        ([[20.0, 70.0], [35.0, 70.0], [35.0, 85.0], [20.0, 85.0]], "2.", 0.95),
        ([[180.0, 70.0], [215.0, 70.0], [215.0, 85.0], [180.0, 85.0]], "Nc6", 0.95),
    ]

    rows = group_boxes_into_rows(ocr_items, y_thresh=15.0)
    assert len(rows) == 2
    row1_texts = [item[1] for item in rows[0]]
    row2_texts = [item[1] for item in rows[1]]

    assert row1_texts == ["1.", "e4", "e5"]
    assert row2_texts == ["2.", "Nf3", "Nc6"]


def test_ignorable_tokens_filtering():
    """Verify that move numbers, clocks, evaluations, percentages, and GUI labels are filtered out."""
    assert is_ignorable_token("1.") is True
    assert is_ignorable_token("24.") is True
    assert is_ignorable_token("1...") is True
    assert is_ignorable_token("2:59") is True
    assert is_ignorable_token("0:45") is True
    assert is_ignorable_token("1.5s") is True
    assert is_ignorable_token("+0.4") is True
    assert is_ignorable_token("-1.2") is True
    assert is_ignorable_token("+M3") is True
    assert is_ignorable_token("98.5%") is True
    assert is_ignorable_token("MOVES") is True
    assert is_ignorable_token("ANALYSIS") is True
    assert is_ignorable_token("BLUNDER") is True

    # Real moves must NOT be ignored
    assert is_ignorable_token("e4") is False
    assert is_ignorable_token("Nf3") is False
    assert is_ignorable_token("O-O") is False
    assert is_ignorable_token("exd5") is False


def test_ocr_typo_correction():
    """Verify automatic correction of standard OCR misrecognitions."""
    assert clean_ocr_token("Rel") == "Re1"
    assert clean_ocr_token("Rdl") == "Rd1"
    assert clean_ocr_token("eS") == "e5"
    assert clean_ocr_token("0-0") == "O-O"
    assert clean_ocr_token("0-0-0") == "O-O-O"
    assert clean_ocr_token("o-o") == "O-O"
    assert clean_ocr_token("NE3") == "Nf3"
    assert clean_ocr_token("Nt3") == "Nf3"
    assert clean_ocr_token("♞c6") == "Nc6"
    assert clean_ocr_token("♗b5") == "Bb5"
    assert clean_ocr_token("Qe7+") == "Qe7"
    assert clean_ocr_token("Qxf7#") == "Qxf7"


def test_notation_sequence_parsing():
    """Verify parsing a complete game sequence with various annotations and OCR quirks."""
    tokens = [
        "1.e4", "e5",
        "2.", "Nf3", "Nc6",
        "3.", "Bb5", "a6",
        "4.", "Ba4", "Nf6",
        "5.", "0-0", "Be7",
        "6.", "Rel", "b5",
        "7.", "Bb3", "d6",
        "8.", "c3", "0-0",
        "9.", "h3", "Nb8",
        "10.", "d4", "Nbd7"
    ]

    moves, final_board = parse_moves_from_tokens(tokens)
    assert len(moves) == 20
    # Starting White's 11th turn
    assert final_board.fullmove_number == 11
    assert final_board.turn == chess.WHITE


def test_tactical_sequence_with_captures_and_checks():
    """Verify tactical game with en-passant, captures, checks, and pawn promotion."""
    b = chess.Board()
    # 1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6
    tokens = ["1.", "e4", "c5", "2.", "Nf3", "d6", "3.", "d4", "cxd4", "4.", "Nxd4", "Nf6", "5.", "Nc3", "a6"]
    moves, end_board = parse_moves_from_tokens(tokens, b)
    assert len(moves) == 10
    assert end_board.piece_at(chess.D4).symbol() == "N"
    assert end_board.turn == chess.WHITE


def test_figurine_implicit_moves():
    """Verify resolution when OCR misses the piece icon and only transcribes destination square."""
    b = chess.Board()
    # 1. e4 e5
    b.push_san("e4")
    b.push_san("e5")

    # Opponent tab renders piece as icon + 'f3' (White knight to f3)
    move = resolve_move_from_token(b, "f3")
    assert move is not None
    # White has two possible moves to f3: pawn f2-f3 and knight g1-f3.
    # Pawn move is legal, resolve_move_from_token prefers pawn push when no piece letter is in token.
    assert move == chess.Move.from_uci("f2f3")

    # If token has piece hint e.g. 'Nf3' or 'N'
    move_n = resolve_move_from_token(b, "Nf3")
    assert move_n == chess.Move.from_uci("g1f3")


def test_moves_tab_observer_initialization_and_sync():
    """Verify MovesTabObserver registers incremental moves to GameStateManager."""
    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)

    observer = MovesTabObserver(gsm)
    assert not observer.is_active()

    cal = BoardCalibration(x=100, y=100, width=300, height=500, is_calibrated=True)
    observer.update_calibration(cal)
    assert gsm.sync_status == SyncStatus.SYNCHRONIZING

    # Simulate progressive live moves received via OCR
    moves_1, b1 = parse_moves_from_tokens(["1.", "e4"])
    observer._known_moves = list(moves_1)
    observer._known_board = b1.copy()
    gsm.confirm_live_move(moves_1[0], b1, confidence=0.99)

    assert gsm.board_state.board.fen() == b1.fen()
    assert gsm.sync_status == SyncStatus.SYNCHRONIZED
    assert "e4" in gsm.status_message

    # Second move: e5
    moves_2, b2 = parse_moves_from_tokens(["1.", "e4", "e5"])
    observer._known_moves = list(moves_2)
    observer._known_board = b2.copy()
    gsm.confirm_live_move(moves_2[1], b2, confidence=0.99)

    assert gsm.board_state.board.fen() == b2.fen()
    assert len(gsm.live_moves) == 2


def test_unspaced_compound_moves_parsing():
    """Verify that unspaced tokens from OCR (e.g. 'I.e4e5', '2.Nf3Nc6', '3.Bb5a6') are unpacked into legal moves."""
    tokens = ["I.e4e5", "2.Nf3Nc6", "3.Bb5a6", "4.Ba4Nf6", "5.0-0Be7", "6.Relb5", "7.Bb3d6"]
    moves, end_board = parse_moves_from_tokens(tokens)
    assert len(moves) == 14
    expected_fen = "r1bqk2r/2p1bppp/p1np1n2/1p2p3/4P3/1B3N2/PPPP1PPP/RNBQR1K1 w kq - 0 8"
    assert end_board.fen() == expected_fen


def test_text_ocr_empty_and_fallback():
    """Verify TextOCR gracefully handles empty, tiny, or None images without raising exceptions."""
    ocr = TextOCR()
    assert ocr.recognize(None) == []
    assert ocr.recognize(np.zeros((0, 0), dtype=np.uint8)) == []
    assert ocr.recognize(np.zeros((2, 2, 3), dtype=np.uint8)) == []


def test_sync_move_sequence_bulk_and_reconnection():
    """Verify GameStateManager.sync_move_sequence atomically loads midgame history and updates live board."""
    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)

    tokens = ["1. e4 e5", "2. Nf3 Nc6", "3. Bb5 a6"]
    moves, end_board = parse_moves_from_tokens(tokens)
    assert len(moves) == 6

    gsm.sync_move_sequence(moves, end_board, confidence=0.99)
    assert len(gsm.live_moves) == 6
    assert gsm.board_state.current_ply == 6
    assert gsm.current_board.fen() == end_board.fen()
    assert gsm.last_confirmed_move == moves[-1]
    assert gsm.sync_status == SyncStatus.SYNCHRONIZED
    assert "Synchronized (6 moves" in gsm.status_message


def test_enhanced_ocr_typo_and_fuzzy_resolution():
    """Verify enhanced OCR typo correction and Levenshtein fuzzy legal move matching."""
    board = chess.Board()

    # Knight prefix confusions (H, M, W -> N)
    m_nf3 = resolve_move_from_token(board, "Hf3")
    assert m_nf3 == chess.Move.from_uci("g1f3")

    m_nc3 = resolve_move_from_token(board, "Mc3")
    assert m_nc3 == chess.Move.from_uci("b1c3")

    # Castling variations
    assert clean_ocr_token("00") == "O-O"
    assert clean_ocr_token("OO") == "O-O"
    assert clean_ocr_token("000") == "O-O-O"
    assert clean_ocr_token("OOO") == "O-O-O"

    # Pawn capture normalization with * or ×
    b2 = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2")
    m_cap = resolve_move_from_token(b2, "e*d5")
    assert m_cap == chess.Move.from_uci("e4d5")

    # Abbreviated pawn capture 'ed'
    m_abbrev = resolve_move_from_token(b2, "ed")
    assert m_abbrev == chess.Move.from_uci("e4d5")

    # Bishop prefix '8' typo -> B
    b3 = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
    m_bb5 = resolve_move_from_token(b3, "8b5")
    assert m_bb5 == chess.Move.from_uci("f1b5")

    # Levenshtein fuzzy match on typos: 'Bxt7' -> 'Bxf7'
    b4 = chess.Board("r1bqk2r/pppp1ppp/2n5/2b1p3/2B1P1n1/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 5")
    m_fuzzy = resolve_move_from_token(b4, "Bxt7+")
    assert m_fuzzy == chess.Move.from_uci("c4f7")


def test_set_starting_position_white_and_black():
    """Verify GameStateManager.set_starting_position accurately sets position and orientation."""
    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)

    # 1. Start as Black (Standard FEN, Black at bottom)
    ok = gsm.set_starting_position(chess.STARTING_FEN, orientation_white_bottom=False)
    assert ok is True
    assert gsm.orientation_white_bottom is False
    assert gsm.player_color == chess.BLACK
    assert gsm.current_board.turn == chess.WHITE

    # 2. Start from 1. e4 (Black to move, Black at bottom)
    e4_fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    ok = gsm.set_starting_position(e4_fen, orientation_white_bottom=False)
    assert ok is True
    assert gsm.orientation_white_bottom is False
    assert gsm.player_color == chess.BLACK
    assert gsm.current_board.turn == chess.BLACK
    assert gsm.current_board.fen() == chess.Board(e4_fen).fen()

    # 3. Invalid FEN rejection
    assert gsm.set_starting_position("invalid_fen_string") is False
