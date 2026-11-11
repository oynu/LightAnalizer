"""
LightAnalizer — Premium AI Chess Analysis and Opponent Profiling Desktop Application.
Application entry point.
"""
from __future__ import annotations
import sys
import os
import chess
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from core.board_state import BoardState
from core.engine_manager import EngineManager
from core.analyzer import ChessAnalyzer
from core.modes import ModeManager
from core.game_state_manager import GameStateManager
from core.opponent.repository import OpponentRepository
from core.vision.observer import BoardObserver
from ui.main_window import MainWindow

def main():
    # In PySide6 / Qt6, high-DPI scaling and DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    # are enabled natively and automatically by QApplication.
    app = QApplication(sys.argv)
    app.setApplicationName("LightAnalizer")
    app.setOrganizationName("DeepMind")

    # Initialize core modules
    repo = OpponentRepository()
    board_state = BoardState()
    engine_mgr = EngineManager()
    analyzer = ChessAnalyzer()
    mode_mgr = ModeManager()

    # Authoritative Game State Coordinator
    game_state_mgr = GameStateManager(board_state, engine_mgr, analyzer)
    observer = BoardObserver(game_state_mgr=game_state_mgr)
    game_state_mgr.set_observer(observer)
    observer.set_known_board(board_state.board)

    # Pre-launch Stockfish in background
    engine_mgr.start_engine()

    window = MainWindow(
        game_state_mgr=game_state_mgr,
        observer=observer,
        mode_mgr=mode_mgr,
        repo=repo
    )
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
