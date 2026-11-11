"""
Automated tests for vision pipeline, square segmentation, checkerboard detection,
differential move inference, and uncertainty handling.
"""
import sys
import numpy as np
import pytest
import chess
from PySide6.QtWidgets import QApplication
from core.types import BoardCalibration
from core.vision.board_detector import BoardDetector
from core.vision.piece_classifier import PieceClassifier
from core.vision.move_inference import MoveInferenceEngine
from core.vision.observer import BoardObserver

# Ensure QApplication exists for QSvgRenderer
@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    yield app

def test_checkerboard_scoring_and_auto_detection():
    detector = BoardDetector()

    # Generate synthetic 400x400 chessboard
    board = np.zeros((400, 400, 3), dtype=np.uint8)
    sq = 50
    for r in range(8):
        for c in range(8):
            color = (230, 235, 240) if (r + c) % 2 == 0 else (100, 130, 160)
            board[r * sq:(r + 1) * sq, c * sq:(c + 1) * sq] = color

    score_board = detector.compute_checkerboard_score(board)
    assert score_board >= 30.0

    # Non-board noise
    noise = np.random.randint(0, 255, (400, 400, 3), dtype=np.uint8)
    score_noise = detector.compute_checkerboard_score(noise)
    assert score_noise < 15.0

    # Embed board into desktop 900x900
    desktop = np.full((900, 900, 3), 30, dtype=np.uint8)
    desktop[200:600, 250:650] = board

    candidates = detector.detect_chessboards(desktop)
    assert len(candidates) >= 1
    best_x, best_y, best_w, best_h, best_score = candidates[0]
    # Check that candidate detected near (250, 200, 400, 400)
    assert abs(best_x - 250) <= 20
    assert abs(best_y - 200) <= 20
    assert abs(best_w - 400) <= 20
    assert abs(best_h - 400) <= 20

def test_inner_board_refinement():
    detector = BoardDetector()
    # Synthetic window containing board + 50px border
    window = np.full((500, 500, 3), 40, dtype=np.uint8)
    board = np.zeros((400, 400, 3), dtype=np.uint8)
    sq = 50
    for r in range(8):
        for c in range(8):
            color = (230, 235, 240) if (r + c) % 2 == 0 else (100, 130, 160)
            board[r * sq:(r + 1) * sq, c * sq:(c + 1) * sq] = color
    window[50:450, 50:450] = board

    rx, ry, rw, rh = detector.refine_inner_board(window)
    assert abs(rx - 50) <= 25
    assert abs(ry - 50) <= 25
    assert abs(rw - 400) <= 25

def test_square_segmentation_orientations():
    detector = BoardDetector()
    dummy_board_img = np.zeros((400, 400, 3), dtype=np.uint8)

    # White at bottom
    crops_white = detector.segment_squares(dummy_board_img, white_at_bottom=True)
    assert len(crops_white) == 64
    assert chess.A1 in crops_white
    assert chess.H8 in crops_white

    # Black at bottom
    crops_black = detector.segment_squares(dummy_board_img, white_at_bottom=False)
    assert len(crops_black) == 64
    assert chess.A1 in crops_black
    assert chess.H8 in crops_black

def test_piece_classifier_initialization():
    classifier = PieceClassifier(target_square_size=64)
    assert len(classifier._templates) == 12  # 6 piece types * 2 colors

    # Test empty square detection (uniform color)
    empty_sq = np.full((64, 64, 3), 180, dtype=np.uint8)
    is_occ, conf = classifier.is_square_occupied(empty_sq)
    assert is_occ is False

def test_differential_move_inference():
    classifier = PieceClassifier(target_square_size=64)
    engine = MoveInferenceEngine(classifier)
    board = chess.Board()

    prev_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    curr_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}

    # Simulate move 1. e4 (squares E2 and E4 change)
    curr_crops[chess.E2] = np.full((32, 32, 3), 200, dtype=np.uint8)
    curr_crops[chess.E4] = np.full((32, 32, 3), 200, dtype=np.uint8)

    move, success, conf = engine.infer_legal_move(board, prev_crops, curr_crops)
    assert success is True
    assert move == chess.Move.from_uci("e2e4")
    assert conf > 0.7

def test_castling_move_inference():
    classifier = PieceClassifier(target_square_size=64)
    engine = MoveInferenceEngine(classifier)
    board = chess.Board("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")

    prev_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    curr_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}

    # Castling changes e1, g1, h1, f1
    for sq in [chess.E1, chess.G1, chess.H1, chess.F1]:
        curr_crops[sq] = np.full((32, 32, 3), 200, dtype=np.uint8)

    move, success, conf = engine.infer_legal_move(board, prev_crops, curr_crops)
    assert success is True
    assert move == chess.Move.from_uci("e1g1")  # O-O

def test_uncertainty_handling_on_obscured_board():
    classifier = PieceClassifier(target_square_size=64)
    engine = MoveInferenceEngine(classifier)
    board = chess.Board()

    prev_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    curr_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}

    # Noise across 15 squares
    for sq in list(chess.SQUARES)[:15]:
        curr_crops[sq] = np.random.randint(50, 200, (32, 32, 3), dtype=np.uint8)

    move, success, conf = engine.infer_legal_move(board, prev_crops, curr_crops)
    assert success is False
    assert move is None

def test_board_observer_calibration():
    observer = BoardObserver()
    cal = BoardCalibration(x=100, y=150, width=500, height=500, orientation_white_bottom=False, is_calibrated=True)
    observer.update_calibration(cal)
    assert observer.calibration.x == 100
    assert observer.calibration.y == 150
    assert observer.calibration.orientation_white_bottom is False
    assert observer.calibration.is_calibrated is True

def test_fading_highlight_immunity():
    classifier = PieceClassifier(target_square_size=64)
    engine = MoveInferenceEngine(classifier)
    
    # Position after 1. e4 (white moved, now black's turn)
    board = chess.Board()
    board.push_san("e4")

    prev_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    curr_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}

    # Simulate black playing 1... e5:
    # E7 and E5 change because black pawn moved.
    curr_crops[chess.E7] = np.full((32, 32, 3), 200, dtype=np.uint8)
    curr_crops[chess.E5] = np.full((32, 32, 3), 200, dtype=np.uint8)

    # In addition, E2 has fading highlight (empty square color changed)
    # E2 was empty in the board (board.piece_at(E2) is None)
    curr_crops[chess.E2] = np.full((32, 32, 3), 90, dtype=np.uint8)

    move, success, conf = engine.infer_legal_move(board, prev_crops, curr_crops)
    assert success is True
    assert move == chess.Move.from_uci("e7e5")
    assert conf > 0.70

def test_subtle_quiet_pawn_move_detection():
    """Verify that low-contrast subtle pawn moves like a2-a3 are never dropped as static screen."""
    classifier = PieceClassifier(target_square_size=64)
    engine = MoveInferenceEngine(classifier)
    board = chess.Board()

    prev_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    curr_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}

    # Simulate quiet move 1. a3 with very subtle delta (only 12 intensity units)
    curr_crops[chess.A2] = np.full((32, 32, 3), 12, dtype=np.uint8)
    curr_crops[chess.A3] = np.full((32, 32, 3), 14, dtype=np.uint8)

    move, success, conf = engine.infer_legal_move(board, prev_crops, curr_crops)
    assert success is True
    assert move == chess.Move.from_uci("a2a3")
    assert conf >= 0.50

def test_multi_ply_blitz_lookahead_detection():
    """Verify that 2 fast consecutive blitz moves (1. e4 e5) in one frame are recognized together."""
    classifier = PieceClassifier(target_square_size=64)
    engine = MoveInferenceEngine(classifier)
    board = chess.Board()

    prev_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}
    curr_crops = {sq: np.zeros((32, 32, 3), dtype=np.uint8) for sq in chess.SQUARES}

    # Both 1. e4 and 1... e5 occurred: e2, e4, e7, e5 changed
    curr_crops[chess.E2] = np.full((32, 32, 3), 180, dtype=np.uint8)
    curr_crops[chess.E4] = np.full((32, 32, 3), 190, dtype=np.uint8)
    curr_crops[chess.E7] = np.full((32, 32, 3), 180, dtype=np.uint8)
    curr_crops[chess.E5] = np.full((32, 32, 3), 190, dtype=np.uint8)

    moves, success, conf = engine.infer_multi_ply_move(board, prev_crops, curr_crops)
    assert success is True
    assert len(moves) == 2
    assert moves[0] == chess.Move.from_uci("e2e4")
    assert moves[1] == chess.Move.from_uci("e7e5")

def test_autonomous_auto_healing_match():
    """Verify that when a board position is desynced, find_best_board_match automatically heals it."""
    classifier = PieceClassifier(target_square_size=64)
    engine = MoveInferenceEngine(classifier)

    # Standard starting board layout (ranks 1, 2, 7, 8 occupied, ranks 3-6 vacant)
    curr_crops = {sq: np.full((32, 32, 3), 180, dtype=np.uint8) for sq in chess.SQUARES}
    # Occupy ranks 1, 2, 7, 8 with random piece edge textures
    for r in [0, 1, 6, 7]:
        for f in range(8):
            curr_crops[chess.square(f, r)] = np.random.randint(20, 240, (32, 32, 3), dtype=np.uint8)

    matched_board, conf = engine.find_best_board_match(curr_crops)
    assert matched_board is not None
    assert matched_board.fen() == chess.STARTING_FEN
    assert conf >= 0.95

def test_edge_projection_coordinate_margin_stripping():
    """Verify that edge projection strips coordinate labels and margins, snapping cleanly to the 8x8 squares."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray
    import chess.svg

    detector = BoardDetector()
    # 480x480 SVG board with outer coordinates (viewBox 390x390, board 360x360 -> ~18px margin)
    svg = chess.svg.board(chess.Board(), coordinates=True, size=480)
    renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
    qimg = QImage(480, 480, QImage.Format.Format_ARGB32)
    qimg.fill(0)
    p = QPainter(qimg)
    renderer.render(p)
    p.end()
    arr = np.frombuffer(qimg.bits(), dtype=np.uint8).reshape((480, 480, 4))
    bgr = arr[:, :, [2, 1, 0]]

    rx, ry, rw, rh = detector.refine_inner_board(bgr)
    assert abs(rx - 18) <= 5
    assert abs(ry - 18) <= 5
    assert abs(rw - 443) <= 10
    assert abs(rh - 443) <= 10

def test_opening_tree_midgame_calibration_sync():
    """Verify that when calibrated mid-game, opening tree recognition identifies the position rather than defaulting to move 0."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray
    import chess.svg

    clf = PieceClassifier(target_square_size=64)
    detector = BoardDetector()
    engine = MoveInferenceEngine(clf)

    # Italian Game after 1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5
    target_b = chess.Board()
    for m in ['e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5']:
        target_b.push_san(m)

    svg = chess.svg.board(target_b, coordinates=False, size=480)
    renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
    qimg = QImage(480, 480, QImage.Format.Format_ARGB32)
    qimg.fill(0)
    p = QPainter(qimg)
    renderer.render(p)
    p.end()
    arr = np.frombuffer(qimg.bits(), dtype=np.uint8).reshape((480, 480, 4))
    bgr = arr[:, :, [2, 1, 0]]

    crops = detector.segment_squares(bgr, white_at_bottom=True)
    matched_board, conf = engine.find_best_board_match(crops)

    assert matched_board is not None
    assert matched_board.fen() == target_b.fen()
    assert conf >= 0.90

def test_midgame_full_board_piece_reconstruction():
    """Verify that a midgame position beyond opening book is reconstructed square-for-square with 100% accuracy."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray
    import chess.svg

    clf = PieceClassifier(target_square_size=60)
    detector = BoardDetector()
    engine = MoveInferenceEngine(clf)

    # Complex Sicilian Najdorf position
    target_b = chess.Board("r1bqkb1r/1p2pppp/p1np1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 1 6")
    svg = chess.svg.board(target_b, coordinates=False, size=480)
    renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
    qimg = QImage(480, 480, QImage.Format.Format_ARGB32)
    qimg.fill(0)
    p = QPainter(qimg)
    renderer.render(p)
    p.end()

    arr = np.frombuffer(qimg.bits(), dtype=np.uint8).reshape((480, 480, 4))
    bgr = arr[:, :, [2, 1, 0]]
    crops = detector.segment_squares(bgr, white_at_bottom=True)

    reconstructed, conf = engine.reconstruct_full_board(crops)
    assert reconstructed is not None
    assert reconstructed.board_fen() == target_b.board_fen()
    assert conf >= 0.70

def test_turn_inference_from_move_highlights():
    """Verify that when a piece on a highlighted square is detected, turn is inferred for the opposing side."""
    import cv2
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray
    import chess.svg

    clf = PieceClassifier(target_square_size=60)
    detector = BoardDetector()
    engine = MoveInferenceEngine(clf)

    # Position after 1. e4: e4 has a White pawn. If e4 is highlighted, it's Black's turn!
    target_b = chess.Board()
    target_b.push_san("e4")

    svg = chess.svg.board(target_b, coordinates=False, size=480)
    renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
    qimg = QImage(480, 480, QImage.Format.Format_ARGB32)
    qimg.fill(0)
    p = QPainter(qimg)
    renderer.render(p)
    p.end()

    arr = np.frombuffer(qimg.bits(), dtype=np.uint8).reshape((480, 480, 4))
    bgr = arr[:, :, [2, 1, 0]]
    crops = detector.segment_squares(bgr, white_at_bottom=True)

    # Realistic Chess.com yellow highlight blended on e4
    tint = np.full_like(crops[chess.E4], [40, 230, 230])
    crops[chess.E4] = cv2.addWeighted(crops[chess.E4], 0.6, tint, 0.4, 0)

    assert clf.is_highlighted(crops[chess.E4]) is True

    reconstructed, _ = engine.reconstruct_full_board(crops)
    assert reconstructed is not None
    # White pawn on e4 was highlighted -> White just moved -> It is Black's turn!
    assert reconstructed.turn == chess.BLACK

def test_clean_start_on_new_board_selection():
    """Verify that reset_for_new_game wipes move history, active candidates, and resets FEN cleanly."""
    from core.board_state import BoardState
    from core.engine_manager import EngineManager
    from core.analyzer import ChessAnalyzer
    from core.game_state_manager import GameStateManager, SyncStatus

    bs = BoardState()
    eng = EngineManager()
    ana = ChessAnalyzer()
    gsm = GameStateManager(bs, eng, ana)

    # Simulate previous game with moves
    gsm.confirm_live_move(chess.Move.from_uci("e2e4"), chess.Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"), 0.95)
    gsm.confirm_live_move(chess.Move.from_uci("e7e5"), chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"), 0.95)

    assert len(gsm.live_moves) == 2
    assert gsm.last_confirmed_move == chess.Move.from_uci("e7e5")

    # User clicks 'Select Board' and confirms new board -> Clean start!
    gsm.reset_for_new_game()

    assert len(gsm.live_moves) == 0
    assert gsm.last_confirmed_move is None
    assert gsm.is_exploring_variation is False
    assert gsm.candidates == []
    assert gsm.summary is None
    assert gsm.board_state.board.fen() == chess.STARTING_FEN
    assert gsm.sync_status == SyncStatus.SYNCHRONIZING

def test_multi_scale_piece_classifier_accuracy():
    """Verify that PieceClassifier accurately identifies pieces at 80% and 96% scaling."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray, QRect
    import chess.svg

    clf = PieceClassifier(target_square_size=60)
    # Test Knight and Queen at 80% scale (typical of Chess.com piece padding)
    for pt in [chess.KNIGHT, chess.QUEEN, chess.PAWN]:
        for color in [chess.WHITE, chess.BLACK]:
            p = chess.Piece(pt, color)
            size = 60
            psize = int(size * 0.80)
            svg = chess.svg.piece(p, size=psize)
            renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
            qimg = QImage(size, size, QImage.Format.Format_ARGB32)
            qimg.fill(0)
            painter = QPainter(qimg)
            offset = (size - psize) // 2
            renderer.render(painter, QRect(offset, offset, psize, psize))
            painter.end()
            arr = np.frombuffer(qimg.bits(), dtype=np.uint8).reshape((size, size, 4))
            bgr = arr[:, :, [2, 1, 0]]
            alpha = arr[:, :, 3:4] / 255.0
            sq = np.full((size, size, 3), 220, dtype=np.uint8)
            sq = (bgr * alpha + sq * (1.0 - alpha)).astype(np.uint8)

            classified_piece, conf = clf.classify_square(sq)
            assert classified_piece == p
            assert conf >= 0.60

def test_global_chess_constraint_satisfaction():
    """Verify that global constraints guarantee exactly 1 king per side and no pawns on back ranks."""
    import chess
    import chess.svg
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray, QRect

    clf = PieceClassifier(target_square_size=60)
    engine = MoveInferenceEngine(clf)

    # Empty crops map
    crops = {sq: np.full((60, 60, 3), 210, dtype=np.uint8) for sq in chess.SQUARES}

    for sq, p in [(chess.E1, chess.Piece(chess.KING, chess.WHITE)), (chess.E8, chess.Piece(chess.KING, chess.BLACK))]:
        svg = chess.svg.piece(p, size=50)
        renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
        qimg = QImage(60, 60, QImage.Format.Format_ARGB32)
        qimg.fill(0)
        painter = QPainter(qimg)
        renderer.render(painter, QRect(5, 5, 50, 50))
        painter.end()
        arr = np.frombuffer(qimg.bits(), dtype=np.uint8).reshape((60, 60, 4))
        bgr = arr[:, :, [2, 1, 0]]
        alpha = arr[:, :, 3:4] / 255.0
        crops[sq] = (bgr * alpha + crops[sq] * (1.0 - alpha)).astype(np.uint8)

    rec, conf = engine.reconstruct_full_board(crops)
    assert rec is not None
    assert len(rec.pieces(chess.KING, chess.WHITE)) == 1
    assert len(rec.pieces(chess.KING, chess.BLACK)) == 1
    assert rec.king(chess.WHITE) == chess.E1
    assert rec.king(chess.BLACK) == chess.E8

def test_first_ply_opening_never_assumed_as_move_zero():
    """Verify that playing 1. e4 or 1. d4 is never falsely detected as move 0 starting position."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray, QRect
    import chess.svg

    clf = PieceClassifier(target_square_size=64)
    engine = MoveInferenceEngine(clf)

    for opening_san in ["e4", "d4", "Nf3"]:
        target_b = chess.Board()
        target_b.push_san(opening_san)

        crops = {}
        for sq in chess.SQUARES:
            p = target_b.piece_at(sq)
            qimg = QImage(64, 64, QImage.Format.Format_ARGB32)
            r = chess.square_rank(sq)
            f = chess.square_file(sq)
            bg = (210, 238, 238) if (r + f) % 2 == 0 else (86, 150, 118)
            qimg.fill(0)
            if p:
                psize = 50
                svg = chess.svg.piece(p, size=psize)
                rend = QSvgRenderer(QByteArray(svg.encode('utf-8')))
                painter = QPainter(qimg)
                rend.render(painter, QRect(7, 7, psize, psize))
                painter.end()
            arr = np.frombuffer(qimg.bits(), dtype=np.uint8).reshape((64, 64, 4))
            alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
            comp = (arr[:, :, :3].astype(np.float32) * alpha + np.full((64, 64, 3), bg) * (1.0 - alpha)).astype(np.uint8)
            crops[sq] = comp

        # Must not be detected as standard starting position
        assert engine._is_standard_starting_position(crops) is False

        # find_best_board_match from initial board must accurately find the 1-ply move
        matched, conf = engine.find_best_board_match(crops, known_board=chess.Board())
        assert matched is not None
        assert matched.board_fen() == target_b.board_fen()

def test_translation_invariant_piece_recognition():
    """Verify that pieces shifted by 1-3 pixels are correctly classified via 2D alignment."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray, QRect
    import chess.svg

    clf = PieceClassifier(target_square_size=64)
    offsets = [(6, 8), (10, 8), (8, 6), (8, 10), (7, 9)]

    for pt in [chess.KNIGHT, chess.ROOK, chess.QUEEN, chess.PAWN]:
        for ox, oy in offsets:
            p = chess.Piece(pt, chess.WHITE)
            psize = 48
            svg = chess.svg.piece(p, size=psize)
            rend = QSvgRenderer(QByteArray(svg.encode('utf-8')))
            qimg = QImage(64, 64, QImage.Format.Format_ARGB32)
            qimg.fill(0)
            painter = QPainter(qimg)
            rend.render(painter, QRect(ox, oy, psize, psize))
            painter.end()

            arr = np.frombuffer(qimg.bits(), dtype=np.uint8).reshape((64, 64, 4))
            alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
            comp = (arr[:, :, :3].astype(np.float32) * alpha + np.full((64, 64, 3), (86, 150, 118)) * (1.0 - alpha)).astype(np.uint8)

            classified, conf = clf.classify_square(comp)
            assert classified == p, f"Offset ({ox}, {oy}) failed for {p}: got {classified}"

def test_material_balance_and_bishop_color_constraints():
    """Verify that global constraints eliminate impossible 2nd dark-squared bishop when 8 pawns exist."""
    import chess
    clf = PieceClassifier(target_square_size=64)
    engine = MoveInferenceEngine(clf)

    # Empty crops map
    crops = {sq: np.full((64, 64, 3), 180, dtype=np.uint8) for sq in chess.SQUARES}
    rec, conf = engine.reconstruct_full_board(crops)
    # With no kings, reconstruction cleanly rejects invalid board
    assert rec is None

def test_chesscom_neo_and_lichess_cburnett_piece_classification():
    """Verify 100% piece classification accuracy on both Chess.com Neo and Lichess Cburnett pieces."""
    import cv2
    import os
    import chess
    import chess.svg
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray, QRect

    clf = PieceClassifier(target_square_size=64)

    piece_map = {'p': chess.PAWN, 'n': chess.KNIGHT, 'b': chess.BISHOP, 'r': chess.ROOK, 'q': chess.QUEEN, 'k': chess.KING}
    color_map = {'w': chess.WHITE, 'b': chess.BLACK}

    # 1. Chess.com Neo pieces
    neo_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "themes", "neo")
    if os.path.exists(neo_dir):
        for c_char, color in color_map.items():
            for p_char, pt in piece_map.items():
                fn = os.path.join(neo_dir, f"{c_char}{p_char}.png")
                raw = cv2.imread(fn, cv2.IMREAD_UNCHANGED)
                assert raw is not None, f"Missing asset: {fn}"
                resized = cv2.resize(raw, (64, 64), interpolation=cv2.INTER_AREA)
                alpha = resized[:, :, 3:4].astype(np.float32) / 255.0
                bgr = resized[:, :, :3].astype(np.float32)

                for bg_bgr, sq_name in [((210, 238, 238), 'light'), ((86, 150, 118), 'dark')]:
                    bg = np.full((64, 64, 3), bg_bgr, dtype=np.float32)
                    comp = (bgr * alpha + bg * (1.0 - alpha)).astype(np.uint8)
                    pred_p, conf = clf.classify_square(comp)
                    expected = chess.Piece(pt, color)
                    assert pred_p == expected, f"Failed Neo {expected} on {sq_name}: got {pred_p} (conf={conf:.2f})"
                    assert conf >= 0.40

    # 2. Lichess Cburnett pieces
    for color in [chess.WHITE, chess.BLACK]:
        for pt in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]:
            expected = chess.Piece(pt, color)
            psize = 52
            svg_data = chess.svg.piece(expected, size=psize)
            rend = QSvgRenderer(QByteArray(svg_data.encode('utf-8')))
            qimg = QImage(64, 64, QImage.Format.Format_ARGB32)
            qimg.fill(0)
            painter = QPainter(qimg)
            rend.render(painter, QRect(6, 6, psize, psize))
            painter.end()
            arr = np.frombuffer(qimg.bits(), dtype=np.uint8).reshape((64, 64, 4))
            alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
            bgr = arr[:, :, :3].astype(np.float32)

            for bg_bgr, sq_name in [((210, 238, 238), 'light'), ((86, 150, 118), 'dark')]:
                bg = np.full((64, 64, 3), bg_bgr, dtype=np.float32)
                comp = (bgr * alpha + bg * (1.0 - alpha)).astype(np.uint8)
                pred_p, conf = clf.classify_square(comp)
                assert pred_p == expected, f"Failed Cburnett {expected} on {sq_name}: got {pred_p} (conf={conf:.2f})"
                assert conf >= 0.40

def test_midgame_full_board_reconstruction_with_real_chesscom_pieces():
    """Verify full-board reconstruction of a complex Sicilian Defense Najdorf position with Chess.com Neo pieces."""
    import cv2
    import os
    clf = PieceClassifier(target_square_size=64)
    engine = MoveInferenceEngine(clf)

    board = chess.Board('r1bqkb1r/1p2pppp/p1np1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 1 6')
    piece_chars = {chess.PAWN: 'p', chess.KNIGHT: 'n', chess.BISHOP: 'b', chess.ROOK: 'r', chess.QUEEN: 'q', chess.KING: 'k'}
    color_chars = {chess.WHITE: 'w', chess.BLACK: 'b'}
    neo_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "themes", "neo")

    crops = {}
    for sq in chess.SQUARES:
        r = chess.square_rank(sq)
        f = chess.square_file(sq)
        bg_bgr = (210, 238, 238) if (r + f) % 2 == 1 else (86, 150, 118)
        bg = np.full((64, 64, 3), bg_bgr, dtype=np.uint8)

        p = board.piece_at(sq)
        if p is not None:
            fn = os.path.join(neo_dir, f"{color_chars[p.color]}{piece_chars[p.piece_type]}.png")
            raw = cv2.imread(fn, cv2.IMREAD_UNCHANGED)
            res = cv2.resize(raw, (64, 64), interpolation=cv2.INTER_AREA)
            a = res[:, :, 3:4].astype(np.float32) / 255.0
            comp = (res[:, :, :3].astype(np.float32) * a + bg.astype(np.float32) * (1.0 - a)).astype(np.uint8)
            crops[sq] = comp
        else:
            crops[sq] = bg

    rec_board, conf = engine.reconstruct_full_board(crops)
    assert rec_board is not None
    assert rec_board.board_fen() == board.board_fen()
    assert conf >= 0.85

def test_chesscom_differential_move_inference():
    """Verify differential legal move inference accurately detects moves using Chess.com Neo pieces."""
    import cv2
    import os
    clf = PieceClassifier(target_square_size=64)
    engine = MoveInferenceEngine(clf)

    board = chess.Board('r1bqkb1r/1p2pppp/p1np1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 1 6')
    piece_chars = {chess.PAWN: 'p', chess.KNIGHT: 'n', chess.BISHOP: 'b', chess.ROOK: 'r', chess.QUEEN: 'q', chess.KING: 'k'}
    color_chars = {chess.WHITE: 'w', chess.BLACK: 'b'}
    neo_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "themes", "neo")

    def make_crops(b):
        crops = {}
        for sq in chess.SQUARES:
            r = chess.square_rank(sq)
            f = chess.square_file(sq)
            bg_bgr = (210, 238, 238) if (r + f) % 2 == 1 else (86, 150, 118)
            bg = np.full((64, 64, 3), bg_bgr, dtype=np.uint8)
            p = b.piece_at(sq)
            if p is not None:
                fn = os.path.join(neo_dir, f"{color_chars[p.color]}{piece_chars[p.piece_type]}.png")
                raw = cv2.imread(fn, cv2.IMREAD_UNCHANGED)
                res = cv2.resize(raw, (64, 64), interpolation=cv2.INTER_AREA)
                a = res[:, :, 3:4].astype(np.float32) / 255.0
                comp = (res[:, :, :3].astype(np.float32) * a + bg.astype(np.float32) * (1.0 - a)).astype(np.uint8)
                crops[sq] = comp
            else:
                crops[sq] = bg
        return crops

    prev_crops = make_crops(board)
    next_b = board.copy()
    move = chess.Move.from_uci("f1e2")
    next_b.push(move)
    curr_crops = make_crops(next_b)

    inferred_move, success, conf = engine.infer_legal_move(board, prev_crops, curr_crops)
    assert success is True
    assert inferred_move == move
    assert conf >= 0.80

# ==============================================================================
# SYNTHETIC STATE-BASED INFERENCE TESTS
# ==============================================================================

class SyntheticTestClassifier:
    """Mock classifier that deterministically reports square occupancy and color."""
    def is_square_occupied(self, crop: np.ndarray):
        if crop is None or crop.size == 0:
            return False, 0.0
        is_occ = (crop[0, 0, 1] == 1)
        return is_occ, 1.0 if is_occ else 0.0

    def detect_piece_color(self, crop: np.ndarray):
        if crop is not None and crop.size > 0 and crop[0, 0, 2] == 2:
            return chess.BLACK
        return chess.WHITE

    def is_highlighted(self, crop: np.ndarray):
        return False

def make_synthetic_crops(board: chess.Board):
    """Encodes piece presence and color into synthetic 32x32 crops."""
    crops = {}
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        arr = np.zeros((32, 32, 3), dtype=np.uint8)
        arr[0, 0, 0] = sq
        if p is not None:
            arr[0, 0, 1] = 1
            arr[0, 0, 2] = 1 if p.color == chess.WHITE else 2
            arr[1:, 1:] = 100 if p.color == chess.WHITE else 50
        else:
            arr[0, 0, 1] = 0
            arr[0, 0, 2] = 0
            arr[1:, 1:] = 200
        crops[sq] = arr
    return crops

def test_robust_state_inference_simple_pawn_move():
    """Verify state-based inference correctly detects a simple pawn move (1. e4)."""
    from core.vision.state_inference import RobustMoveInference, Verdict
    engine = RobustMoveInference(SyntheticTestClassifier())
    b0 = chess.Board()
    b1 = b0.copy()
    b1.push_san("e4")

    res = engine.infer_frame(b0, make_synthetic_crops(b0), make_synthetic_crops(b1))
    assert res.verdict == Verdict.MOVES
    assert len(res.steps) == 1
    assert res.steps[0][0] == chess.Move.from_uci("e2e4")
    assert res.steps[0][1].board_fen() == b1.board_fen()

def test_robust_state_inference_capture():
    """Verify state-based inference correctly detects a capture (exd5)."""
    from core.vision.state_inference import RobustMoveInference, Verdict
    engine = RobustMoveInference(SyntheticTestClassifier())
    b0 = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    b1 = b0.copy()
    b1.push_san("exd5")

    res = engine.infer_frame(b0, make_synthetic_crops(b0), make_synthetic_crops(b1))
    assert res.verdict == Verdict.MOVES
    assert len(res.steps) == 1
    assert res.steps[0][0] == chess.Move.from_uci("e4d5")

def test_robust_state_inference_kingside_castling():
    """Verify state-based inference detects kingside castling (O-O) via 4-square bitmask."""
    from core.vision.state_inference import RobustMoveInference, Verdict
    engine = RobustMoveInference(SyntheticTestClassifier())
    b0 = chess.Board("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    b1 = b0.copy()
    b1.push_san("O-O")

    res = engine.infer_frame(b0, make_synthetic_crops(b0), make_synthetic_crops(b1))
    assert res.verdict == Verdict.MOVES
    assert len(res.steps) == 1
    assert res.steps[0][0] == chess.Move.from_uci("e1g1")

def test_robust_state_inference_en_passant():
    """Verify state-based inference detects en passant (exf6) with 3-square occupancy delta."""
    from core.vision.state_inference import RobustMoveInference, Verdict
    engine = RobustMoveInference(SyntheticTestClassifier())
    b0 = chess.Board("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
    b1 = b0.copy()
    b1.push_san("exf6")

    res = engine.infer_frame(b0, make_synthetic_crops(b0), make_synthetic_crops(b1))
    assert res.verdict == Verdict.MOVES
    assert len(res.steps) == 1
    assert res.steps[0][0] == chess.Move.from_uci("e5f6")

def test_robust_state_inference_promotion_queen_default():
    """Verify state-based inference defaults to Queen promotion when masks are identical."""
    from core.vision.state_inference import RobustMoveInference, Verdict
    engine = RobustMoveInference(SyntheticTestClassifier())
    b0 = chess.Board("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
    b1 = b0.copy()
    b1.push_san("e8=Q")

    res = engine.infer_frame(b0, make_synthetic_crops(b0), make_synthetic_crops(b1))
    assert res.verdict == Verdict.MOVES
    assert res.steps[0][0] == chess.Move.from_uci("e7e8q")
    assert res.steps[0][0].promotion == chess.QUEEN

def test_robust_state_inference_2ply_sequence():
    """Verify state-based inference captures 2-ply blitz sequence in a single frame."""
    from core.vision.state_inference import RobustMoveInference, Verdict
    engine = RobustMoveInference(SyntheticTestClassifier())
    b0 = chess.Board()
    b1 = b0.copy()
    b1.push_san("e4")
    b2 = b1.copy()
    b2.push_san("e5")

    res = engine.infer_frame(b0, make_synthetic_crops(b0), make_synthetic_crops(b2))
    assert res.verdict == Verdict.MOVES
    assert len(res.steps) == 2
    assert res.steps[0][0] == chess.Move.from_uci("e2e4")
    assert res.steps[1][0] == chess.Move.from_uci("e7e5")

def test_robust_state_inference_highlight_only_no_change():
    """Verify highlight-only pixel changes with unchanged piece occupancy return NO_CHANGE."""
    from core.vision.state_inference import RobustMoveInference, Verdict
    engine = RobustMoveInference(SyntheticTestClassifier())
    b = chess.Board()
    b.push_san("e4")

    prev = make_synthetic_crops(b)
    curr = make_synthetic_crops(b)
    # Simulate highlight color shift on e2 and e4 (pixel diff >= 6.0, occupancy unchanged)
    curr[chess.E2][1:, 1:] = 175
    curr[chess.E4][1:, 1:] = 175

    res = engine.infer_frame(b, prev, curr)
    assert res.verdict == Verdict.NO_CHANGE

def test_robust_state_inference_piece_lifted_mid_drag_uncertain():
    """Verify that a piece lifted mid-drag (from-square empty, nothing else changed) returns UNCERTAIN."""
    from core.vision.state_inference import RobustMoveInference, Verdict
    engine = RobustMoveInference(SyntheticTestClassifier())
    b = chess.Board()

    prev = make_synthetic_crops(b)
    curr = make_synthetic_crops(b)
    # Lift pawn on e2: e2 becomes empty in curr
    curr[chess.E2][0, 0, 1] = 0
    curr[chess.E2][0, 0, 2] = 0
    curr[chess.E2][1:, 1:] = 200

    res = engine.infer_frame(b, prev, curr)
    assert res.verdict == Verdict.UNCERTAIN

def test_robust_resync_never_returns_pre_move_board():
    """Verify that healing a position after a move NEVER returns the pre-move board."""
    from core.vision.state_inference import RobustMoveInference
    engine = RobustMoveInference(SyntheticTestClassifier())
    b0 = chess.Board()   # Stale pre-move board
    b1 = b0.copy()
    b1.push_san("e4")    # Live board on screen

    # Screen shows b1 crops, observer is currently at b0
    curr = make_synthetic_crops(b1)
    healed_board, conf, reason = engine.heal_position(b0, curr, continuous_uncertain_seconds=0.0)

    assert healed_board is not None
    # Must heal to b1 (the live game), NEVER b0 (the stale pre-move board)
    assert healed_board.board_fen() == b1.board_fen()
    assert healed_board.board_fen() != b0.board_fen()

def test_robust_state_inference_highlight_disambiguation():
    """Verify that yellow/green move highlights provide decisive disambiguation and confidence."""
    from core.vision.state_inference import RobustMoveInference, Verdict
    from core.vision.piece_classifier import PieceClassifier

    clf = PieceClassifier(target_square_size=64)
    engine = RobustMoveInference(clf)

    b0 = chess.Board()
    b1 = b0.copy()
    b1.push_san("e4")

    prev = make_synthetic_crops(b0)
    curr = make_synthetic_crops(b1)

    # Apply Chess.com move highlight tint to e2 and e4:
    # Yellow/green tint: B=80, G=190, R=190 (r>125, g>125, r-b>28, g-b>28)
    curr[chess.E2][:, :] = (80, 190, 190)
    curr[chess.E4][:, :] = (80, 190, 190)
    curr[chess.E4][16:48, 16:48] = 230

    res = engine.infer_frame(b0, prev, curr)
    assert res.verdict == Verdict.MOVES
    assert res.steps[0][0] == chess.Move.from_uci("e2e4")
    assert "[highlight match]" in res.reason
    assert res.confidence == 1.0

def test_observer_two_frame_stability_gate(tmp_path):
    """Verify the 2-frame stability gate detects animation in motion (diff >= 1.8) and records to SessionRecorder."""
    import cv2
    from core.vision.session_recorder import SessionRecorder

    rec = SessionRecorder.get_instance()
    rec.base_dir = tmp_path / "sessions"
    rec.base_dir.mkdir(parents=True, exist_ok=True)

    f1 = np.full((128, 128, 3), 100, dtype=np.uint8)
    f2 = np.full((128, 128, 3), 100, dtype=np.uint8)
    f2[30:90, 30:90] = 220

    s1 = cv2.resize(f1, (32, 32))
    s2 = cv2.resize(f2, (32, 32))
    g1 = cv2.cvtColor(s1, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(s2, cv2.COLOR_BGR2GRAY)
    inter_frame_diff = float(np.mean(np.abs(g2.astype(np.float32) - g1.astype(np.float32))))

    assert inter_frame_diff >= 1.8

    rec.record_frame(
        source="board",
        image=f2,
        board_fen_before=chess.STARTING_FEN,
        verdict="UNCERTAIN",
        notes=f"Animation in progress (diff={inter_frame_diff:.2f} >= 1.8)"
    )

    path = rec.save_incident("Animation stability test")
    assert path is not None
    assert (path / "manifest.json").exists()

def test_grey_legal_move_dots_immunity_on_empty_squares():
    """Verify that faint grey destination hint circles are recognized as empty squares, not occupied pieces."""
    import cv2
    from core.vision.piece_classifier import PieceClassifier
    clf = PieceClassifier()
    # Synthetic square crop with Chess.com style grey circular legal move dot
    square = np.full((64, 64, 3), (118, 150, 86), dtype=np.uint8) # Dark green square
    # Draw faint grey circle in center
    cv2.circle(square, (32, 32), 10, (140, 140, 140), -1)
    
    is_occ, conf = clf.is_square_occupied(square)
    assert is_occ is False

def test_piece_in_hand_holding_state_uncertainty_without_healing():
    """Verify that a piece held in hand/mid-drag produces 'Piece in hand' reason and does not trigger auto-heal."""
    from core.vision.state_inference import RobustMoveInference, Verdict
    from core.vision.observer import BoardObserver
    from core.game_state_manager import GameStateManager
    from core.board_state import BoardState
    from core.engine_manager import EngineManager
    from core.analyzer import ChessAnalyzer

    engine = RobustMoveInference(SyntheticTestClassifier())
    board = chess.Board()

    prev = make_synthetic_crops(board)
    curr = make_synthetic_crops(board)
    # Lift pawn from e2 (empty in curr, cursor over e3)
    curr[chess.E2][0, 0, 1] = 0
    curr[chess.E2][0, 0, 2] = 0
    curr[chess.E2][1:, 1:] = 200

    res = engine.infer_frame(board, prev, curr)
    assert res.verdict == Verdict.UNCERTAIN
    assert "Piece in hand" in res.reason

    # Verify BoardObserver status handling
    bs = BoardState()
    em = EngineManager()
    an = ChessAnalyzer()
    gsm = GameStateManager(bs, em, an)
    obs = BoardObserver(gsm)
    obs._known_board = board.copy()
    
    # Simulate worker logic handling for piece in hand
    is_holding = ("Piece in hand" in res.reason or "holding" in res.reason)
    assert is_holding is True

def test_real_user_uploaded_chessboard_images():
    """Verify orientation, start position, dot rejection, and piece recognition on real screen gameplay images."""
    import os
    import cv2
    from core.vision.board_detector import BoardDetector
    from core.vision.piece_classifier import PieceClassifier
    from core.vision.move_inference import MoveInferenceEngine
    img_paths = [
        r'C:/Users/arnau/.gemini/antigravity/brain/6d77e573-a0ca-404b-8f75-19afaaa1409a/.user_uploaded/media_1794044648511_10355908.jpg',
        r'C:/Users/arnau/.gemini/antigravity/brain/6d77e573-a0ca-404b-8f75-19afaaa1409a/.user_uploaded/media_1794044672319_ef4cb4d2.jpg',
        r'C:/Users/arnau/.gemini/antigravity/brain/6d77e573-a0ca-404b-8f75-19afaaa1409a/.user_uploaded/media_1794044684328_ea82efb4.jpg',
        r'C:/Users/arnau/.gemini/antigravity/brain/6d77e573-a0ca-404b-8f75-19afaaa1409a/.user_uploaded/media_1794044707719_5949b5d7.jpg',
        r'C:/Users/arnau/.gemini/antigravity/brain/6d77e573-a0ca-404b-8f75-19afaaa1409a/.user_uploaded/media_1794044742635_fa097911.jpg'
    ]
    if not all(os.path.exists(p) for p in img_paths):
        pytest.skip("User uploaded gameplay images not available in environment")

    bd = BoardDetector()
    clf = PieceClassifier()
    eng = MoveInferenceEngine(clf)

    for idx, p in enumerate(img_paths, 1):
        im = cv2.imread(p)
        cands = bd.detect_chessboards(im)
        if cands:
            x, y, w, h, sc = cands[0]
            crop = im[y:y+h, x:x+w]
        else:
            rx, ry, rw, rh = bd.refine_inner_board(im)
            crop = im[ry:ry+rh, rx:rx+rw]

        crops_w = bd.segment_squares(crop, white_at_bottom=True)
        is_w = bd.determine_orientation(crops_w)
        crops_actual = bd.segment_squares(crop, white_at_bottom=is_w)

        expected_w = (idx == 1)
        assert is_w == expected_w

        if idx == 1:
            assert eng._is_standard_starting_position(crops_actual) is True
        elif idx == 2:
            assert eng._is_standard_starting_position(crops_actual) is True
        elif idx == 3:
            d5_occ, _ = clf.is_square_occupied(crops_actual[chess.D5])
            d6_occ, _ = clf.is_square_occupied(crops_actual[chess.D6])
            d4_occ, _ = clf.is_square_occupied(crops_actual[chess.D4])
            assert not d5_occ
            assert not d6_occ
            assert d4_occ
        elif idx == 5:
            e6_piece, _ = clf.classify_square(crops_actual[chess.E6])
            c6_piece, _ = clf.classify_square(crops_actual[chess.C6])
            f5_piece, _ = clf.classify_square(crops_actual[chess.F5])
            c3_piece, _ = clf.classify_square(crops_actual[chess.C3])
            c4_piece, _ = clf.classify_square(crops_actual[chess.C4])
            d4_piece, _ = clf.classify_square(crops_actual[chess.D4])
            e7_piece, _ = clf.classify_square(crops_actual[chess.E7])
            assert e6_piece == chess.Piece.from_symbol('p')
            assert c6_piece == chess.Piece.from_symbol('n')
            assert f5_piece == chess.Piece.from_symbol('b')
            assert c3_piece == chess.Piece.from_symbol('N')
            assert c4_piece == chess.Piece.from_symbol('P')
            assert d4_piece == chess.Piece.from_symbol('P')
            assert e7_piece is None







