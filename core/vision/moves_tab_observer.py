"""
High-performance screen observer for the moves/notation tab.
Continuously captures the selected moves panel, runs OCR,
transcribes moves in real-time, and feeds confirmed moves to GameStateManager.
"""
from __future__ import annotations
import threading
import time
import logging
from typing import Optional, List, Dict, Any
import cv2
import numpy as np
import chess

from core.types import BoardCalibration, SyncStatus, DiagnosticsData
from core.vision.capture import ScreenCapture
from core.vision.text_ocr import TextOCR
from core.vision.notation_parser import parse_ocr_to_game, group_boxes_into_rows, resolve_move_from_token, is_ignorable_token
from core.vision.piece_icon_bank import PieceIconBank
from core.vision.session_recorder import SessionRecorder
from core.game_state_manager import GameStateManager

logger = logging.getLogger(__name__)

class MovesTabObserver:
    """
    Background worker monitoring the moves/notation tab region on screen.
    Uses diff-based change detection, debounced OCR recognition,
    2-frame confirmation to prevent flicker errors, and grid-anchored move tracking.
    """
    def __init__(
        self,
        game_state_mgr: Optional[GameStateManager] = None,
        calibration: Optional[BoardCalibration] = None
    ):
        self.game_state_mgr = game_state_mgr
        self.calibration = calibration or BoardCalibration()
        self.capture = ScreenCapture()
        self.ocr = TextOCR()
        self.icon_bank = PieceIconBank()

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Cache of previous frame & state
        self._prev_thumb: Optional[np.ndarray] = None
        self._known_moves: List[chess.Move] = []
        self._known_board: chess.Board = chess.Board()
        self._last_san: str = ""

        # Multi-frame confirmation & divergence protection
        self._pending_move: Optional[chess.Move] = None
        self._pending_count: int = 0
        self._divergence_count: int = 0

    def set_game_state_manager(self, mgr: GameStateManager) -> None:
        with self._lock:
            self.game_state_mgr = mgr

    def set_known_board(self, board: Optional[chess.Board]) -> None:
        with self._lock:
            self._known_board = board.copy() if board else chess.Board()
            self._known_moves.clear()
            self._prev_thumb = None
            self._last_san = ""

    def reset_state(self) -> None:
        """Clears all cached move history and frame baselines for a clean match start."""
        with self._lock:
            self._prev_thumb = None
            self._known_moves.clear()
            self._known_board = chess.Board()
            self._last_san = ""
            self._pending_move = None
            self._pending_count = 0
            self._divergence_count = 0

    def on_undo(self, live_moves: List[chess.Move], board: chess.Board) -> None:
        """Resets observer cache to previous confirmed state when a ply is undone."""
        with self._lock:
            self._known_moves = list(live_moves)
            self._known_board = board.copy()
            self._prev_thumb = None
            self._pending_move = None
            self._pending_count = 0
            self._divergence_count = 0

    def update_calibration(self, cal: BoardCalibration) -> None:
        with self._lock:
            self.calibration = cal
            self._prev_thumb = None
            self._known_moves.clear()
            self._known_board = chess.Board()
            self._last_san = ""
            self._pending_move = None
            self._pending_count = 0
            self._divergence_count = 0
            if self.game_state_mgr:
                self.game_state_mgr.update_sync_status(
                    SyncStatus.SYNCHRONIZING,
                    "Moves tab selected. Scanning notation..."
                )

    def start(self) -> None:
        with self._lock:
            if self._running and self._thread and self._thread.is_alive():
                return
            self._running = True
            self._thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        if self.game_state_mgr:
            self.game_state_mgr.update_sync_status(
                SyncStatus.BOARD_UNAVAILABLE,
                "Observation stopped."
            )

    def is_active(self) -> bool:
        with self._lock:
            return bool(self._running and self._thread and self._thread.is_alive())

    def _worker_loop(self) -> None:
        fps_counter = 0
        fps_time = time.time()
        curr_fps = 0.0

        while True:
            with self._lock:
                if not self._running:
                    break
                cal = self.calibration
                prev_thumb = self._prev_thumb
                mgr = self.game_state_mgr

            if not cal.is_calibrated or cal.width <= 0 or cal.height <= 0:
                time.sleep(0.3)
                continue

            fps_counter += 1
            if time.time() - fps_time >= 1.0:
                curr_fps = float(fps_counter) / (time.time() - fps_time)
                fps_counter = 0
                fps_time = time.time()

            t_start = time.perf_counter()

            try:
                # 1. Screen Capture of selected moves tab
                t0_cap = time.perf_counter()
                raw_img = self.capture.capture_region(cal.x, cal.y, cal.width, cal.height)
                t_cap = (time.perf_counter() - t0_cap) * 1000.0

                if raw_img is None or raw_img.size == 0:
                    if mgr:
                        mgr.update_sync_status(SyncStatus.BOARD_UNAVAILABLE, "Screen capture unavailable")
                    time.sleep(0.3)
                    continue

                # 2. Fast Difference Check on 64x64 thumbnail
                thumb = cv2.resize(raw_img, (64, 64))
                gray_thumb = cv2.cvtColor(thumb, cv2.COLOR_BGR2GRAY)

                with self._lock:
                    has_known = len(self._known_moves) > 0

                # Only skip OCR if we already have transcribed moves and screen has zero changes
                if prev_thumb is not None and has_known:
                    diff = float(np.mean(np.abs(gray_thumb.astype(np.float32) - prev_thumb.astype(np.float32))))
                    max_diff = float(np.max(np.abs(gray_thumb.astype(np.float32) - prev_thumb.astype(np.float32))))
                    if diff < 0.20 and max_diff < 12.0:
                        elapsed = time.perf_counter() - t_start
                        time.sleep(max(0.040, 0.350 - elapsed))
                        continue

                # 3. Fast OCR Recognition & Move Transcription
                t0_ocr = time.perf_counter()
                ocr_items = self.ocr.recognize(raw_img)
                t_ocr = (time.perf_counter() - t0_ocr) * 1000.0

                parsed_moves, final_board = parse_ocr_to_game(
                    ocr_items,
                    image=raw_img,
                    icon_bank=self.icon_bank
                )

                verdict_str = "HOLD"
                with self._lock:
                    known_moves = list(self._known_moves)
                    known_len = len(known_moves)
                    parsed_len = len(parsed_moves)

                    if parsed_len > known_len:
                        if parsed_moves[:known_len] == known_moves and (parsed_len - known_len) == 1:
                            # Standard incremental single-ply live move
                            m = parsed_moves[-1]
                            if self._pending_move == m:
                                self._pending_count += 1
                                if self._pending_count >= 2:
                                    # Confirmed across 2 consecutive frames!
                                    self._known_moves.append(m)
                                    self._known_board.push(m)
                                    try:
                                        san = self._known_board.san(m)
                                    except Exception:
                                        san = m.uci()
                                    self._last_san = san
                                    self._pending_move = None
                                    self._pending_count = 0
                                    self._divergence_count = 0
                                    verdict_str = f"CONFIRMED_1PLY ({san})"
                                    if mgr:
                                        mgr.confirm_live_move(m, self._known_board.copy(), confidence=0.99)
                                else:
                                    verdict_str = f"PENDING_1PLY ({m.uci()}) (frame 1/2)"
                            else:
                                self._pending_move = m
                                self._pending_count = 1
                                verdict_str = f"NEW_CANDIDATE ({m.uci()})"
                        elif known_len == 0:
                            # Initial match load or starting position
                            self._known_moves = list(parsed_moves)
                            self._known_board = final_board.copy()
                            try:
                                self._last_san = self._known_board.san(parsed_moves[-1]) if parsed_moves else ""
                            except Exception:
                                self._last_san = parsed_moves[-1].uci() if parsed_moves else ""
                            self._pending_move = None
                            self._pending_count = 0
                            self._divergence_count = 0
                            verdict_str = f"INITIAL_SYNC ({len(parsed_moves)} moves)"
                            if mgr:
                                mgr.sync_move_sequence(parsed_moves, self._known_board.copy(), confidence=0.99)
                        else:
                            # Multi-move jump or divergence during play
                            self._divergence_count += 1
                            if self._divergence_count >= 3:
                                self._known_moves = list(parsed_moves)
                                self._known_board = final_board.copy()
                                try:
                                    self._last_san = self._known_board.san(parsed_moves[-1]) if parsed_moves else ""
                                except Exception:
                                    self._last_san = parsed_moves[-1].uci() if parsed_moves else ""
                                self._pending_move = None
                                self._pending_count = 0
                                self._divergence_count = 0
                                verdict_str = f"RESYNC_AFTER_DIVERGENCE ({len(parsed_moves)} moves)"
                                if mgr:
                                    mgr.sync_move_sequence(parsed_moves, self._known_board.copy(), confidence=0.99)
                            else:
                                verdict_str = f"DIVERGENCE_HELD (frame {self._divergence_count}/3)"

                    elif parsed_len == 0 and known_len == 0:
                        if mgr:
                            mgr.update_sync_status(
                                SyncStatus.SYNCHRONIZING,
                                "Moves tab active (waiting for move 1)..."
                            )
                        verdict_str = "WAITING_MOVE_1"

                    elif known_len > 0 and (parsed_len == 0 or parsed_len <= known_len):
                        # Table might have scrolled down!
                        # Look for row matching expected_move_num on self._known_board
                        current_ply = known_len
                        expected_move_num = (current_ply // 2) + 1
                        expected_turn = chess.WHITE if (current_ply % 2 == 0) else chess.BLACK

                        rows = group_boxes_into_rows(ocr_items)
                        candidate_move = None

                        import re
                        for r in rows:
                            r_texts = [str(itm[1]).strip() for itm in r]
                            has_num = False
                            for txt in r_texts:
                                m_num = re.match(r'^([0-9]{1,3})\.?', txt)
                                if m_num and int(m_num.group(1)) == expected_move_num:
                                    has_num = True
                                    break

                            if has_num:
                                non_num_items = [itm for itm in r if not is_ignorable_token(str(itm[1]))]
                                target_item = None
                                if expected_turn == chess.WHITE and len(non_num_items) >= 1:
                                    target_item = non_num_items[0]
                                elif expected_turn == chess.BLACK and len(non_num_items) >= 2:
                                    target_item = non_num_items[1]
                                elif expected_turn == chess.BLACK and len(non_num_items) == 1:
                                    box = non_num_items[0][0]
                                    cx = sum(p[0] for p in box) / 4.0
                                    row_min_x = min(min(p[0] for p in itm[0]) for itm in r)
                                    row_max_x = max(max(p[0] for p in itm[0]) for itm in r)
                                    if cx > (row_min_x + (row_max_x - row_min_x) * 0.45):
                                        target_item = non_num_items[0]

                                if target_item:
                                    tok = str(target_item[1]).strip()
                                    has_icon, icon_crop = self.icon_bank.has_icon(raw_img, target_item[0])
                                    icon_sym = self.icon_bank.classify_icon(icon_crop) if (has_icon and icon_crop is not None) else None
                                    cand = resolve_move_from_token(
                                        self._known_board,
                                        tok,
                                        has_piece_icon=has_icon,
                                        piece_icon_symbol=icon_sym
                                    )
                                    if cand and cand in self._known_board.legal_moves:
                                        candidate_move = cand
                                        break

                        if candidate_move:
                            if self._pending_move == candidate_move:
                                self._pending_count += 1
                                if self._pending_count >= 2:
                                    self._known_moves.append(candidate_move)
                                    self._known_board.push(candidate_move)
                                    try:
                                        san = self._known_board.san(candidate_move)
                                    except Exception:
                                        san = candidate_move.uci()
                                    self._last_san = san
                                    self._pending_move = None
                                    self._pending_count = 0
                                    verdict_str = f"CONFIRMED_SCROLLED ({san})"
                                    if mgr:
                                        mgr.confirm_live_move(candidate_move, self._known_board.copy(), confidence=0.99)
                                else:
                                    verdict_str = f"PENDING_SCROLLED ({candidate_move.uci()}) (frame 1/2)"
                            else:
                                self._pending_move = candidate_move
                                self._pending_count = 1
                                verdict_str = f"NEW_SCROLLED ({candidate_move.uci()})"
                        else:
                            verdict_str = "NO_NEW_MOVE_IN_SCROLL"

                    self._prev_thumb = gray_thumb

                # Record frame in session recorder
                SessionRecorder.get_instance().record_frame(
                    source="moves_tab",
                    image=raw_img,
                    ocr_items=ocr_items,
                    board_fen_before=known_moves and self._known_board.fen() or "",
                    board_fen_after=self._known_board.fen(),
                    detected_moves=[m.uci() for m in self._known_moves[-3:]],
                    verdict=verdict_str
                )

                # 4. Diagnostic reporting
                t_total = (time.perf_counter() - t_start) * 1000.0
                diag = DiagnosticsData(
                    fps=curr_fps,
                    capture_ms=t_cap,
                    recognition_ms=t_ocr,
                    total_latency_ms=t_total,
                    confidence=0.99 if parsed_len > 0 else 0.0,
                    sync_status=mgr.sync_status if mgr else SyncStatus.SYNCHRONIZED,
                    last_move_san=self._last_san,
                    detected_fen=self._known_board.fen(),
                    authoritative_fen=self._known_board.fen()
                )
                if mgr:
                    mgr.diagnostics_emitted.emit(diag)

                # Loop interval: 350ms cadence (every 300-400ms as requested)
                elapsed = time.perf_counter() - t_start
                time.sleep(max(0.020, 0.350 - elapsed))

            except Exception as e:
                logger.error(f"Error in MovesTabObserver worker loop: {e}", exc_info=True)
                time.sleep(0.15)
