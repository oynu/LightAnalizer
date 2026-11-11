"""
Automated tests for UI lifecycle stability, repeated board selector activations,
and multi-threaded live game synchronization without crashes.
"""
import sys
import time
import threading
import pytest
import chess
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QMetaObject

from core.board_state import BoardState
from core.engine_manager import EngineManager
from core.analyzer import ChessAnalyzer
from core.modes import ModeManager
from core.game_state_manager import GameStateManager
from core.opponent.repository import OpponentRepository
from core.vision.observer import BoardObserver
from core.types import BoardCalibration, SyncStatus
from ui.main_window import MainWindow

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_select_board_repeated_open_and_close(qapp):
    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)
    mode_mgr = ModeManager()
    repo = OpponentRepository(":memory:")
    observer = BoardObserver(gsm)

    win = MainWindow(gsm, observer, mode_mgr, repo)
    win.show()
    qapp.processEvents()

    # 1st open and confirm
    win.open_board_selector()
    qapp.processEvents()
    assert win._active_overlay is not None
    cal = BoardCalibration(x=50, y=50, width=400, height=400, is_calibrated=True)
    win._on_calibration_confirmed(cal)
    qapp.processEvents()
    assert win._active_overlay is None

    # 2nd open and close
    win.open_board_selector()
    qapp.processEvents()
    assert win._active_overlay is not None
    win._active_overlay.close()
    qapp.processEvents()

    # 3rd open and confirm
    win.open_board_selector()
    qapp.processEvents()
    assert win._active_overlay is not None
    win._on_calibration_confirmed(cal)
    qapp.processEvents()
    assert win._active_overlay is None

    win.close()
    qapp.processEvents()
    observer.stop()
    engine_mgr.stop_engine()

def test_select_moves_tab_repeated_open_and_confirm(qapp):
    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)
    mode_mgr = ModeManager()
    repo = OpponentRepository(":memory:")
    observer = BoardObserver(gsm)

    win = MainWindow(gsm, observer, mode_mgr, repo)
    win.show()
    qapp.processEvents()

    # 1. Open moves tab selector
    win.open_moves_tab_selector()
    qapp.processEvents()
    assert win._active_overlay is not None
    assert win._active_overlay.mode == "moves_tab"

    # Confirm selection
    cal = BoardCalibration(x=200, y=150, width=280, height=450, is_calibrated=True)
    win._on_moves_tab_confirmed(cal)
    qapp.processEvents()
    assert win._active_overlay is None
    assert win.moves_tab_observer.calibration.width == 280

    # 2. Re-open and cancel (Esc)
    win.open_moves_tab_selector()
    qapp.processEvents()
    assert win._active_overlay is not None
    win._active_overlay.close()
    qapp.processEvents()
    assert win._active_overlay is None

    # 3. Clean start on new selection verified
    win.open_moves_tab_selector()
    qapp.processEvents()
    cal2 = BoardCalibration(x=100, y=100, width=320, height=480, is_calibrated=True)
    win._on_moves_tab_confirmed(cal2)
    qapp.processEvents()
    assert win.moves_tab_observer.calibration.width == 320
    assert win.game_state_mgr.sync_status == SyncStatus.SYNCHRONIZING

    win.close()
    qapp.processEvents()
    win.moves_tab_observer.stop()
    observer.stop()
    engine_mgr.stop_engine()

def test_compact_hud_mode_and_always_on_top(qapp):
    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)
    mode_mgr = ModeManager()
    repo = OpponentRepository(":memory:")
    observer = BoardObserver(gsm)

    win = MainWindow(gsm, observer, mode_mgr, repo)
    win.show()
    qapp.processEvents()

    # Starts in compact HUD mode, pinned by default so it stays on top without Alt-Tab
    assert win._is_compact_mode is True
    assert win.width() <= 400
    assert win._always_on_top is True
    assert win.windowFlags() & Qt.WindowStaysOnTopHint

    # By default in compact mode, visual mini-board is enabled and visible
    assert win.view_analysis.board_container.isVisible()
    assert win.view_analysis.analysis_container.isVisible()

    # Toggle mini-board off
    win.toggle_mini_board()
    qapp.processEvents()
    assert win._show_mini_board is False
    assert not win.view_analysis.board_container.isVisible()

    # Toggle mini-board back on
    win.toggle_mini_board()
    qapp.processEvents()
    assert win._show_mini_board is True
    assert win.view_analysis.board_container.isVisible()

    # Expand to full desktop mode
    win.toggle_compact_mode()
    qapp.processEvents()
    assert win._is_compact_mode is False
    assert win.width() >= 800
    assert win.view_analysis.board_container.isVisible()

    # Return to compact HUD
    win.toggle_compact_mode()
    qapp.processEvents()
    assert win._is_compact_mode is True
    assert win.width() <= 400
    assert win.view_analysis.board_container.isVisible()

    # Unpin always-on-top
    win.toggle_always_on_top()
    qapp.processEvents()
    assert win._always_on_top is False
    assert not (win.windowFlags() & Qt.WindowStaysOnTopHint)

    # Re-pin always-on-top
    win.toggle_always_on_top()
    qapp.processEvents()
    assert win._always_on_top is True
    assert win.windowFlags() & Qt.WindowStaysOnTopHint

    win.close()
    qapp.processEvents()
    win.moves_tab_observer.stop()
    observer.stop()
    engine_mgr.stop_engine()

def test_thread_safe_live_move_and_engine_streaming(qapp):
    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)
    mode_mgr = ModeManager()
    repo = OpponentRepository(":memory:")
    observer = BoardObserver(gsm)
    engine_mgr.start_engine()

    win = MainWindow(gsm, observer, mode_mgr, repo)
    win.show()
    qapp.processEvents()

    moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
    curr_b = chess.Board()

    for uci in moves:
        m = chess.Move.from_uci(uci)
        curr_b.push(m)
        def do_move(move=m, b=curr_b.copy()):
            gsm.confirm_live_move(move, b, 0.95)

        t = threading.Thread(target=do_move)
        t.start()
        t.join(timeout=0.5)

        for _ in range(5):
            qapp.processEvents()
            time.sleep(0.02)

    assert win.game_state_mgr.last_confirmed_move == chess.Move.from_uci("b8c6")
    assert win.view_analysis.board_widget._board.fen() == curr_b.fen()

    win.close()
    qapp.processEvents()
    observer.stop()
    engine_mgr.stop_engine()

def test_player_side_toggle_and_turn_indicators(qapp):
    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)
    mode_mgr = ModeManager()
    repo = OpponentRepository(":memory:")
    observer = BoardObserver(gsm)

    win = MainWindow(gsm, observer, mode_mgr, repo)
    win.show()
    qapp.processEvents()

    # Initial state: White at bottom (Player is White)
    assert gsm.orientation_white_bottom is True
    assert gsm.player_color == chess.WHITE
    assert "White" in win.btn_side_toggle.text()
    assert win.view_analysis.board_widget.is_white_at_bottom() is True
    assert "YOUR TURN [WHITE TO MOVE]" in win.view_analysis.lbl_coach.text()

    # Toggle to Black
    win.btn_side_toggle.click()
    qapp.processEvents()
    assert gsm.orientation_white_bottom is False
    assert gsm.player_color == chess.BLACK
    assert "Black" in win.btn_side_toggle.text()
    assert win.view_analysis.board_widget.is_white_at_bottom() is False
    assert observer.calibration.orientation_white_bottom is False
    assert win.moves_tab_observer.calibration.orientation_white_bottom is False
    assert "OPPONENT'S TURN [WHITE TO MOVE]" in win.view_analysis.lbl_coach.text()

    # Play e4 (White's move)
    b_after_e4 = chess.Board()
    m_e4 = chess.Move.from_uci("e2e4")
    b_after_e4.push(m_e4)
    gsm.confirm_live_move(m_e4, b_after_e4, 0.99)
    qapp.processEvents()

    # Now turn is BLACK and player is BLACK:
    assert "YOUR TURN [BLACK TO MOVE]" in win.view_analysis.lbl_coach.text()

    # Toggle back to White
    win.btn_side_toggle.click()
    qapp.processEvents()
    assert gsm.orientation_white_bottom is True
    assert gsm.player_color == chess.WHITE
    assert "White" in win.btn_side_toggle.text()
    assert win.view_analysis.board_widget.is_white_at_bottom() is True
    assert "OPPONENT'S TURN [BLACK TO MOVE]" in win.view_analysis.lbl_coach.text()

    win.close()
    qapp.processEvents()
    observer.stop()
    engine_mgr.stop_engine()

def test_position_setup_dialog_and_custom_fen(qapp):
    from ui.widgets.position_dialog import PositionSetupDialog

    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)
    mode_mgr = ModeManager()
    repo = OpponentRepository(":memory:")
    observer = BoardObserver(gsm)

    win = MainWindow(gsm, observer, mode_mgr, repo)
    win.show()
    qapp.processEvents()

    dlg = PositionSetupDialog(gsm, win)
    dlg.show()
    qapp.processEvents()

    # 1. Preset Black
    dlg.btn_preset_black.click()
    dlg.btn_apply.click()
    qapp.processEvents()
    assert gsm.orientation_white_bottom is False
    assert gsm.player_color == chess.BLACK
    assert "Black" in win.btn_side_toggle.text()

    # 2. Preset 1. e4
    dlg2 = PositionSetupDialog(gsm, win)
    dlg2.btn_preset_1e4.click()
    dlg2.btn_apply.click()
    qapp.processEvents()
    assert gsm.orientation_white_bottom is False
    assert gsm.current_board.turn == chess.BLACK
    assert gsm.current_board.piece_at(chess.E4) is not None

    # 3. Custom FEN (Sicilian Defense)
    sicilian_fen = "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2"
    dlg3 = PositionSetupDialog(gsm, win)
    dlg3.txt_fen.setText(sicilian_fen)
    dlg3.radio_white.setChecked(True)
    dlg3.btn_apply.click()
    qapp.processEvents()
    assert gsm.orientation_white_bottom is True
    assert gsm.player_color == chess.WHITE
    assert gsm.current_board.turn == chess.WHITE
    assert "White" in win.btn_side_toggle.text()

    win.close()
    qapp.processEvents()
    observer.stop()
    engine_mgr.stop_engine()

def test_flag_wrong_move_f9_and_session_recording(qapp, tmp_path):
    from core.vision.session_recorder import SessionRecorder
    import numpy as np

    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)
    mode_mgr = ModeManager()
    repo = OpponentRepository(":memory:")
    observer = BoardObserver(gsm)

    rec = SessionRecorder.get_instance()
    rec.base_dir = tmp_path / "sessions"
    rec.base_dir.mkdir(parents=True, exist_ok=True)

    dummy_frame = np.full((100, 100, 3), 128, dtype=np.uint8)
    rec.record_frame(
        source="board",
        image=dummy_frame,
        board_fen_before=chess.STARTING_FEN,
        board_fen_after=chess.STARTING_FEN,
        detected_moves=["e2e4"],
        verdict="MOVES"
    )

    win = MainWindow(gsm, observer, mode_mgr, repo)
    win.show()
    qapp.processEvents()

    win._on_flag_wrong_move()
    qapp.processEvents()

    assert "Incident saved" in win.sync_pill.text()
    incidents = list(rec.base_dir.glob("incident_*"))
    assert len(incidents) >= 1
    manifest_file = incidents[0] / "manifest.json"
    assert manifest_file.exists()

    win.close()
    qapp.processEvents()
    observer.stop()
    engine_mgr.stop_engine()

def test_undo_last_ply_safety_net(qapp):
    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)
    mode_mgr = ModeManager()
    repo = OpponentRepository(":memory:")
    observer = BoardObserver(gsm)

    win = MainWindow(gsm, observer, mode_mgr, repo)
    win.show()
    qapp.processEvents()

    # Confirm e2e4
    b1 = chess.Board()
    m1 = chess.Move.from_uci("e2e4")
    b1.push(m1)
    gsm.confirm_live_move(m1, b1, confidence=0.99)
    qapp.processEvents()
    assert len(gsm.live_moves) == 1
    assert gsm.current_board.piece_at(chess.E4) is not None

    # Confirm e7e5
    b2 = b1.copy()
    m2 = chess.Move.from_uci("e7e5")
    b2.push(m2)
    gsm.confirm_live_move(m2, b2, confidence=0.99)
    qapp.processEvents()
    assert len(gsm.live_moves) == 2

    # Trigger Undo (Backspace)
    win._on_undo_last_ply()
    qapp.processEvents()

    assert len(gsm.live_moves) == 1
    assert gsm.live_moves[0] == m1
    assert gsm.current_board.turn == chess.BLACK
    assert "Undid last move" in win.sync_pill.text()

    # Undo again back to starting position
    win._on_undo_last_ply()
    qapp.processEvents()
    assert len(gsm.live_moves) == 0
    assert gsm.current_board.turn == chess.WHITE
    assert gsm.current_board.piece_at(chess.E4) is None

    win.close()
    qapp.processEvents()
    observer.stop()
    engine_mgr.stop_engine()

def test_screen_overlay_lifecycle_and_rendering(qapp):
    from core.types import CandidateMove

    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    gsm = GameStateManager(board_state, engine_mgr, analyzer)
    mode_mgr = ModeManager()
    repo = OpponentRepository(":memory:")
    observer = BoardObserver(gsm)

    win = MainWindow(gsm, observer, mode_mgr, repo)
    win.show()
    qapp.processEvents()

    # Calibrate board
    cal = BoardCalibration(x=120, y=120, width=480, height=480, is_calibrated=True)
    win._on_calibration_confirmed(cal)
    qapp.processEvents()

    # Toggle overlay ON via MainWindow
    win.toggle_screen_overlay()
    qapp.processEvents()
    assert win.screen_overlay.isVisible()
    assert win.view_analysis._screen_hud_active
    assert win.screen_overlay.geometry().x() == 120
    assert win.screen_overlay.geometry().width() == 480

    # Feed candidate moves and verify sync
    c1 = CandidateMove(move=chess.Move.from_uci("e2e4"), san="e4", score_cp=35, eval_str="+0.35", rank=1)
    c2 = CandidateMove(move=chess.Move.from_uci("d2d4"), san="d4", score_cp=28, eval_str="+0.28", rank=2)
    c3 = CandidateMove(move=chess.Move.from_uci("g1f3"), san="Nf3", score_cp=20, eval_str="+0.20", rank=3)
    gsm._latest_candidates = [c1, c2, c3]
    win._sync_screen_overlay()
    qapp.processEvents()
    assert len(win.screen_overlay._candidate_moves) == 3

    # Verify paintEvent executes cleanly without exceptions
    win.screen_overlay.paintEvent(None)

    # Toggle overlay OFF
    win.toggle_screen_overlay()
    qapp.processEvents()
    assert not win.screen_overlay.isVisible()
    assert not win.view_analysis._screen_hud_active

    win.close()
    qapp.processEvents()
    observer.stop()
    engine_mgr.stop_engine()
