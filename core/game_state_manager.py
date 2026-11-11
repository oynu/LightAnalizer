"""
Single authoritative game-state manager.
Coordinates board position, engine analysis version tracking,
synchronization status, and user exploration mode.
"""
from __future__ import annotations
import time
from typing import List, Optional, Callable, Dict, Any
import chess
from PySide6.QtCore import QObject, Signal
from core.types import (
    SyncStatus, CandidateMove, PositionSummary,
    DiagnosticsData, BoardCalibration
)
from core.board_state import BoardState
from core.engine_manager import EngineManager
from core.analyzer import ChessAnalyzer
from core.brilliant_farmer import BrilliantFarmer

class GameStateManager(QObject):
    """
    Authoritative coordinator for the chess position, engine synchronization,
    and live observation lifecycle.
    Thread-safe inter-thread communication via Qt Signals.
    """
    state_changed = Signal()
    orientation_changed = Signal(bool)
    diagnostics_emitted = Signal(object)

    def __init__(
        self,
        board_state: BoardState,
        engine_mgr: EngineManager,
        analyzer: ChessAnalyzer
    ):
        super().__init__()
        self.board_state = board_state
        self.engine_mgr = engine_mgr
        self.analyzer = analyzer

        # Authoritative Live Game State
        self._live_board = chess.Board()
        self._live_fen = chess.STARTING_FEN
        self._live_moves: List[chess.Move] = []
        self._last_confirmed_move: Optional[chess.Move] = None
        self._orientation_white_bottom = True

        # Synchronization & Diagnostics State
        self._sync_status = SyncStatus.BOARD_UNAVAILABLE
        self._status_message = "No board selected. Click 'Select Board' to begin."
        self._confidence = 0.0
        self._last_sync_timestamp = 0.0
        self._rejection_reason = ""

        # Position Version Counter for Strict Engine Synchronization
        self._position_version = 0
        self._latest_candidates: List[CandidateMove] = []
        self._latest_summary: Optional[PositionSummary] = None

        # Brilliant Farmer Mode
        self.brilliant_farmer = BrilliantFarmer()
        self._brilliant_mode = False
        self._brilliant_count = 0
        self._brilliant_history: List[Tuple[int, str]] = []

        # Mode: Live Tracking vs User Exploring Variation
        self._is_exploring_variation = False

        # Callbacks
        self._listeners: List[Callable[[], None]] = []
        self._diagnostics_listeners: List[Callable[[DiagnosticsData], None]] = []

        # Observer reference
        self.observer: Optional[Any] = None

        # Wire engine callback with strict version check
        self.engine_mgr.add_result_callback(self._on_engine_analysis_result)

    def set_observer(self, observer: Any) -> None:
        self.observer = observer

    @property
    def orientation_white_bottom(self) -> bool:
        return self._orientation_white_bottom

    @property
    def player_color(self) -> chess.Color:
        return chess.WHITE if self._orientation_white_bottom else chess.BLACK

    def set_orientation(self, white_bottom: bool) -> None:
        if self._orientation_white_bottom != white_bottom:
            self._orientation_white_bottom = white_bottom
            if self.observer and hasattr(self.observer, "calibration"):
                self.observer.calibration.orientation_white_bottom = white_bottom
                if hasattr(self.observer, "set_known_board") and self.board_state.board:
                    self.observer.set_known_board(self.board_state.board)
            self.orientation_changed.emit(white_bottom)
            self._notify()

    def toggle_orientation(self) -> bool:
        new_val = not self._orientation_white_bottom
        self.set_orientation(new_val)
        return new_val

    @property
    def brilliant_mode(self) -> bool:
        return self._brilliant_mode

    @property
    def brilliant_count(self) -> int:
        return self._brilliant_count

    def set_brilliant_mode(self, enabled: bool) -> None:
        self._brilliant_mode = enabled
        # Boost MultiPV search depth to 6 when farming brilliance to unearth tactical sacrifices
        if hasattr(self.engine_mgr, "config"):
            self.engine_mgr.config.multipv = 6 if enabled else 3

        # Re-request active position analysis with 6 lines
        self._position_version += 1
        curr_ver = self._position_version
        active_b = self.board_state.board
        self._request_analysis_for_position(active_b, curr_ver)

        if self._latest_candidates:
            if enabled:
                self._latest_candidates = self.brilliant_farmer.process_candidates(
                    self.board_state.board, list(self._latest_candidates)
                )
            else:
                self._latest_candidates.sort(key=lambda c: c.rank)
            self._notify()

    def toggle_brilliant_mode(self) -> bool:
        new_val = not self._brilliant_mode
        self.set_brilliant_mode(new_val)
        return new_val

    @property
    def current_board(self) -> chess.Board:
        """Returns the board currently displayed to the user."""
        return self.board_state.board

    @property
    def live_board(self) -> chess.Board:
        """Returns the authoritative live board observed on screen."""
        return self._live_board

    @property
    def fen(self) -> str:
        return self.board_state.board.fen()

    @property
    def sync_status(self) -> SyncStatus:
        return self._sync_status

    @property
    def status_message(self) -> str:
        return self._status_message

    @property
    def is_exploring_variation(self) -> bool:
        return self._is_exploring_variation

    @property
    def candidates(self) -> List[CandidateMove]:
        return self._latest_candidates

    @property
    def summary(self) -> Optional[PositionSummary]:
        return self._latest_summary

    @property
    def last_sync_time(self) -> float:
        return self._last_sync_timestamp

    @property
    def live_moves(self) -> List[chess.Move]:
        return list(self._live_moves)

    @property
    def last_confirmed_move(self) -> Optional[chess.Move]:
        return self._last_confirmed_move

    def add_listener(self, cb: Callable[[], None]) -> None:
        self.state_changed.connect(cb)
        if cb not in self._listeners:
            self._listeners.append(cb)

    def add_diagnostics_listener(self, cb: Callable[[DiagnosticsData], None]) -> None:
        self.diagnostics_emitted.connect(cb)
        if cb not in self._diagnostics_listeners:
            self._diagnostics_listeners.append(cb)

    def _notify(self) -> None:
        self.state_changed.emit()

    def update_sync_status(self, status: SyncStatus, message: str = "", rejection_reason: str = "") -> None:
        changed = (self._sync_status != status or self._status_message != message)
        self._sync_status = status
        self._status_message = message or status.value
        if rejection_reason:
            self._rejection_reason = rejection_reason
        if changed:
            self._notify()

    def confirm_live_move(self, move: chess.Move, new_board: chess.Board, confidence: float) -> None:
        """
        Called when a legal move is confirmed from screen observation.
        """
        try:
            move_san = self.board_state.board.san(move)
        except Exception:
            move_san = move.uci()

        # Check if the confirmed move was a brilliant move
        was_brilliant = False
        for c in self._latest_candidates:
            if getattr(c, "is_brilliant", False) and c.move == move:
                was_brilliant = True
                break
        if not was_brilliant:
            is_sound, _ = self.brilliant_farmer.is_move_sound_sacrifice(self.board_state.board, move)
            if is_sound:
                was_brilliant = True

        if was_brilliant:
            self._brilliant_count += 1
            self._brilliant_history.append((len(self._live_moves) + 1, move_san))

        self._live_board = new_board.copy()
        self._live_fen = self._live_board.fen()
        self._live_moves.append(move)
        self._last_confirmed_move = move
        self._confidence = confidence
        self._last_sync_timestamp = time.time()
        self._sync_status = SyncStatus.SYNCHRONIZED
        self._status_message = f"Synchronized (move {move_san})"
        self._rejection_reason = ""

        # If not actively exploring a custom branch, update the active analysis board
        if not self._is_exploring_variation:
            self._position_version += 1
            curr_ver = self._position_version
            success = self.board_state.push_move(move)
            if not success:
                self.board_state.reset(self._live_fen)
            self._request_analysis_for_position(self._live_board, curr_ver)

        self._notify()

    def reset_for_new_game(self) -> None:
        """
        Completely resets all game history, engine searches, and caches for a clean match start.
        """
        self.engine_mgr.cancel_analysis()
        self._live_moves.clear()
        self._last_confirmed_move = None
        self._is_exploring_variation = False
        self._latest_candidates.clear()
        self._latest_summary = None
        self._confidence = 0.0
        self._position_version += 1
        self._brilliant_count = 0
        self._brilliant_history.clear()
        self.board_state.reset()
        self._live_board = chess.Board()
        self._live_fen = self._live_board.fen()
        self.update_sync_status(SyncStatus.SYNCHRONIZING, "Scanning board position...")

    def set_starting_position(self, fen: str = chess.STARTING_FEN, orientation_white_bottom: bool = True) -> bool:
        """
        Sets a new starting position from FEN and configures board orientation.
        Resets move history, stops obsolete engine searches, and triggers
        immediate engine analysis for the side to move.
        """
        try:
            new_board = chess.Board(fen)
        except Exception:
            return False

        self.engine_mgr.cancel_analysis()
        self._live_moves.clear()
        self._last_confirmed_move = None
        self._is_exploring_variation = False
        self._latest_candidates.clear()
        self._latest_summary = None
        self._confidence = 1.0

        self._orientation_white_bottom = orientation_white_bottom
        self._live_board = new_board.copy()
        self._live_fen = self._live_board.fen()

        self._position_version += 1
        curr_ver = self._position_version
        self.board_state.reset(self._live_fen)

        if self.observer:
            if hasattr(self.observer, "calibration"):
                self.observer.calibration.orientation_white_bottom = orientation_white_bottom
            if hasattr(self.observer, "set_known_board"):
                self.observer.set_known_board(new_board)

        turn_str = "White" if new_board.turn == chess.WHITE else "Black"
        self.update_sync_status(
            SyncStatus.SYNCHRONIZED,
            f"Position set: {turn_str} to move"
        )
        self._request_analysis_for_position(self._live_board, curr_ver)
        self.orientation_changed.emit(orientation_white_bottom)
        self._notify()
        return True

    def undo_last_ply(self) -> bool:
        """
        Reverts the last confirmed ply. Useful as a safety net if a move was misdetected
        or user wants to step back. Triggers immediate re-analysis for the reverted position.
        """
        if not self._live_moves:
            return False

        self.engine_mgr.cancel_analysis()
        if self._brilliant_history and self._brilliant_history[-1][0] == len(self._live_moves):
            self._brilliant_history.pop()
            self._brilliant_count = max(0, self._brilliant_count - 1)
        self._live_moves.pop()

        root_board = self.board_state.game.board()
        new_board = root_board.copy()
        for m in self._live_moves:
            new_board.push(m)

        self._live_board = new_board.copy()
        self._live_fen = self._live_board.fen()
        self._last_confirmed_move = self._live_moves[-1] if self._live_moves else None
        self._position_version += 1
        curr_ver = self._position_version

        self.board_state.reset(root_board.fen())
        for m in self._live_moves:
            self.board_state.push_move(m)

        if self.observer and hasattr(self.observer, "set_known_board"):
            self.observer.set_known_board(self._live_board)

        self.update_sync_status(
            SyncStatus.SYNCHRONIZED,
            f"Undid move. Active ply: {len(self._live_moves)}"
        )
        self._request_analysis_for_position(self._live_board, curr_ver)
        self._notify()
        return True

    def sync_move_sequence(self, moves: List[chess.Move], new_board: chess.Board, confidence: float = 0.99) -> None:
        """
        Atomically synchronizes a complete sequence of moves (initial scan or multi-ply replay).
        Populates board_state move history and triggers engine analysis for the final position.
        """
        self.engine_mgr.cancel_analysis()
        self.board_state.reset()
        for m in moves:
            self.board_state.push_move(m)
        self._live_moves = list(moves)
        self._live_board = new_board.copy()
        self._live_fen = self._live_board.fen()
        self._last_confirmed_move = moves[-1] if moves else None
        self._confidence = confidence
        self._last_sync_timestamp = time.time()
        self._sync_status = SyncStatus.SYNCHRONIZED

        try:
            last_san = self.board_state.board.san(moves[-1]) if moves else ""
        except Exception:
            last_san = moves[-1].uci() if moves else ""

        self._status_message = f"Synchronized ({len(moves)} moves, last: {last_san})" if moves else "Synchronized"
        self._rejection_reason = ""

        if not self._is_exploring_variation:
            self._position_version += 1
            curr_ver = self._position_version
            self._request_analysis_for_position(self._live_board, curr_ver)

        self._notify()

    def resynchronize_live_board(self, new_board: chess.Board, confidence: float) -> None:
        """
        Called when full board is resynchronized (initial position or mid-game join).
        """
        self._live_moves.clear()
        self._live_board = new_board.copy()
        self._live_fen = self._live_board.fen()
        self._last_confirmed_move = None
        self._confidence = confidence
        self._last_sync_timestamp = time.time()
        self._sync_status = SyncStatus.SYNCHRONIZED
        self._status_message = "Synchronized with screen position"
        self._rejection_reason = ""

        if not self._is_exploring_variation:
            self._position_version += 1
            curr_ver = self._position_version
            self.board_state.reset(self._live_fen)
            self._request_analysis_for_position(self._live_board, curr_ver)

        self._notify()

    def user_played_analysis_move(self, move: chess.Move) -> bool:
        """User played an interactive move on the analysis board."""
        was_brill = any(getattr(c, "is_brilliant", False) and c.move == move for c in self._latest_candidates)
        if not was_brill:
            is_sound, _ = self.brilliant_farmer.is_move_sound_sacrifice(self.board_state.board, move)
            if is_sound:
                was_brill = True

        success = self.board_state.push_move(move)
        if success:
            if was_brill:
                self._brilliant_count += 1
                try:
                    m_san = self.board_state.board.san(move)
                except Exception:
                    m_san = move.uci()
                self._brilliant_history.append((len(self.board_state.moves), m_san))

            self._is_exploring_variation = True
            self._position_version += 1
            curr_ver = self._position_version
            self._request_analysis_for_position(self.board_state.board, curr_ver)
            self._notify()
        return success

    def return_to_live_game(self) -> None:
        """Exits variation exploration and snaps back to the authoritative live game position."""
        self._is_exploring_variation = False
        self._position_version += 1
        curr_ver = self._position_version
        self.board_state.reset(self._live_fen)
        for m in self._live_moves:
            self.board_state.push_move(m)
        self._request_analysis_for_position(self._live_board, curr_ver)
        self._notify()

    def _request_analysis_for_position(self, board: chess.Board, version: int) -> None:
        # Cancel any obsolete engine searches
        self.engine_mgr.cancel_analysis()
        self.engine_mgr.request_analysis(board)

    def _on_engine_analysis_result(self, fen: str, candidates: List[CandidateMove]) -> None:
        # Strict version and FEN verification: discard stale results
        if fen != self.board_state.board.fen():
            return  # Discard obsolete engine analysis

        if self._brilliant_mode:
            candidates = self.brilliant_farmer.process_candidates(self.board_state.board, candidates)

        self._latest_candidates = candidates
        self._latest_summary = self.analyzer.analyze_position(self.board_state.board, candidates)
        self._notify()

    def emit_diagnostics(self, diag: DiagnosticsData) -> None:
        self.diagnostics_emitted.emit(diag)
