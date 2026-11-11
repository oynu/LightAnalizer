"""
High-performance adaptive screen observation worker.
Minimizes latency with lightweight difference hashing, animation settling,
and diagnostic instrumentation.
"""
from __future__ import annotations
import threading
import time
from typing import Optional, Dict
import cv2
import numpy as np
import chess
from core.types import BoardCalibration, SyncStatus, DiagnosticsData
from core.vision.capture import ScreenCapture
from core.vision.board_detector import BoardDetector
from core.vision.piece_classifier import PieceClassifier
from core.vision.move_inference import MoveInferenceEngine
from core.vision.state_inference import RobustMoveInference, Verdict, FrameResult
from core.vision.session_recorder import SessionRecorder
from core.game_state_manager import GameStateManager

class BoardObserver:
    """
    Background worker monitoring the screen region with adaptive sleeping,
    sub-millisecond static checks, and reliable move validation.
    """
    def __init__(
        self,
        game_state_mgr: Optional[GameStateManager] = None,
        calibration: Optional[BoardCalibration] = None
    ):
        self.game_state_mgr = game_state_mgr
        self.calibration = calibration or BoardCalibration()
        self.capture = ScreenCapture()
        self.detector = BoardDetector()
        self.classifier = PieceClassifier()
        self.inference = RobustMoveInference(self.classifier)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Cache of previous frame
        self._prev_crops: Optional[Dict[chess.Square, np.ndarray]] = None
        self._prev_thumb: Optional[np.ndarray] = None
        self._known_board = chess.Board()
        self._last_san: str = ""
        self._uncertain_start_time: Optional[float] = None

    def set_game_state_manager(self, mgr: GameStateManager) -> None:
        with self._lock:
            self.game_state_mgr = mgr

    def set_known_board(self, board: Optional[chess.Board]) -> None:
        with self._lock:
            self._known_board = board.copy() if board else None
            self._prev_crops = None
            self._prev_thumb = None
            self._last_san = ""
            self._uncertain_start_time = None

    def reset_state(self) -> None:
        """Completely clears all cached observation history and previous frames."""
        with self._lock:
            self._prev_crops = None
            self._prev_thumb = None
            self._known_board = None
            self._last_san = ""
            self._uncertain_start_time = None

    def update_calibration(self, cal: BoardCalibration) -> None:
        with self._lock:
            self.calibration = cal
            self._prev_crops = None
            self._prev_thumb = None
            self._known_board = None
            self._last_san = ""
            self._uncertain_start_time = None
            if self.game_state_mgr:
                self.game_state_mgr.update_sync_status(
                    SyncStatus.SYNCHRONIZING,
                    "Calibrated. Scanning chessboard..."
                )

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.8)
        self._thread = None
        if self.game_state_mgr:
            self.game_state_mgr.update_sync_status(
                SyncStatus.BOARD_UNAVAILABLE,
                "Observation stopped."
            )

    def is_active(self) -> bool:
        with self._lock:
            return self._running

    def _worker_loop(self) -> None:
        fps_counter = 0
        fps_time = time.time()
        curr_fps = 0.0
        consecutive_uncertain = 0

        while True:
            with self._lock:
                if not self._running:
                    break
                cal = self.calibration
                prev_thumb = self._prev_thumb
                prev_crops = self._prev_crops
                mgr = self.game_state_mgr

            if not cal.is_calibrated or cal.width <= 0 or cal.height <= 0:
                time.sleep(0.5)
                continue

            # Update FPS measurement
            fps_counter += 1
            if time.time() - fps_time >= 1.0:
                curr_fps = float(fps_counter) / (time.time() - fps_time)
                fps_counter = 0
                fps_time = time.time()

            t_start = time.perf_counter()
            rejection_reason = ""

            try:
                # 1. Fast Screen Capture
                t0_cap = time.perf_counter()
                raw_img = self.capture.capture_region(cal.x, cal.y, cal.width, cal.height)
                t_cap = (time.perf_counter() - t0_cap) * 1000.0

                if raw_img is None or raw_img.size == 0:
                    if mgr:
                        mgr.update_sync_status(SyncStatus.BOARD_UNAVAILABLE, "Screen capture unavailable")
                    time.sleep(0.5)
                    continue

                # 2. Fast 8x8 block difference check on 32x32 thumbnail (<0.1 ms)
                thumb = cv2.resize(raw_img, (32, 32))
                gray_thumb = cv2.cvtColor(thumb, cv2.COLOR_BGR2GRAY)

                if prev_thumb is not None:
                    diff_matrix = np.abs(gray_thumb.astype(np.float32) - prev_thumb.astype(np.float32)).reshape(8, 4, 8, 4).mean(axis=(1, 3))
                    max_sq_diff = float(diff_matrix.max())
                    top2_sq_sum = float(np.sort(diff_matrix.ravel())[-2:].sum())

                    if max_sq_diff < 2.8 and top2_sq_sum < 4.8:
                        # Static board: sleep until next 350ms tick
                        elapsed = time.perf_counter() - t_start
                        time.sleep(max(0.040, 0.350 - elapsed))
                        continue

                # 3. Change Detected: 2-Frame Stability Gate (detect animation in flight)
                time.sleep(0.060)
                settled_img = self.capture.capture_region(cal.x, cal.y, cal.width, cal.height)
                if settled_img is not None and settled_img.size > 0:
                    s_thumb = cv2.resize(settled_img, (32, 32))
                    gray_s_thumb = cv2.cvtColor(s_thumb, cv2.COLOR_BGR2GRAY)
                    inter_frame_diff = float(np.mean(np.abs(gray_s_thumb.astype(np.float32) - gray_thumb.astype(np.float32))))

                    if inter_frame_diff >= 1.8:
                        # Animation or piece motion actively in flight across screen
                        SessionRecorder.get_instance().record_frame(
                            source="board",
                            image=settled_img,
                            board_fen_before=self._known_board.fen() if self._known_board else "",
                            verdict="UNCERTAIN",
                            notes=f"Animation in progress (diff={inter_frame_diff:.2f} >= 1.8)"
                        )
                        if mgr:
                            mgr.update_sync_status(SyncStatus.SYNCHRONIZING, "Piece in motion... settling")
                        time.sleep(0.040)
                        continue

                    raw_img = settled_img
                    gray_thumb = gray_s_thumb

                t0_recog = time.perf_counter()
                curr_crops = self.detector.segment_squares(raw_img, cal.orientation_white_bottom)

                # If first frame after calibration: baseline full-board sync
                if prev_crops is None:
                    board, b_conf, _ = self.inference.heal_position(
                        self._known_board or chess.Board(),
                        curr_crops,
                        continuous_uncertain_seconds=4.0
                    )
                    if board:
                        with self._lock:
                            self._known_board = board.copy()
                            self._prev_crops = curr_crops
                            self._prev_thumb = gray_thumb
                            self._last_san = ""
                            self._uncertain_start_time = None
                        if mgr:
                            mgr.resynchronize_live_board(board, b_conf)
                    else:
                        if mgr:
                            mgr.update_sync_status(
                                SyncStatus.POSITION_UNCERTAIN,
                                "Scanning board position... Please keep chessboard visible"
                            )
                        time.sleep(0.08)
                    continue

                # 4. State-based Move Inference from previous known board
                current_board = self._known_board.copy()
                frame_res = self.inference.infer_frame(current_board, prev_crops, curr_crops)
                t_recog = (time.perf_counter() - t0_recog) * 1000.0
                conf = frame_res.confidence

                if frame_res.verdict == Verdict.NO_CHANGE:
                    consecutive_uncertain = 0
                    self._uncertain_start_time = None
                    with self._lock:
                        self._prev_crops = curr_crops
                        self._prev_thumb = gray_thumb
                    rejection_reason = "No change"

                elif frame_res.verdict == Verdict.MOVES:
                    consecutive_uncertain = 0
                    self._uncertain_start_time = None
                    board_cursor = self._known_board.copy()
                    for move, board_after in frame_res.steps:
                        try:
                            self._last_san = board_cursor.san(move)
                        except Exception:
                            self._last_san = move.uci()
                        board_cursor = board_after.copy()
                        with self._lock:
                            self._known_board = board_cursor.copy()
                        if mgr:
                            mgr.confirm_live_move(move, board_cursor, conf)

                    with self._lock:
                        self._prev_crops = curr_crops
                        self._prev_thumb = gray_thumb
                    rejection_reason = ""

                elif frame_res.verdict == Verdict.UNCERTAIN:
                    # If piece is held/lifted, do NOT increment healing counter or desync
                    is_holding_piece = ("Piece in hand" in (frame_res.reason or "") or "holding" in (frame_res.reason or ""))
                    rejection_reason = frame_res.reason or "Position uncertain"
                    conf = 0.0

                    if is_holding_piece:
                        if mgr:
                            mgr.update_sync_status(
                                SyncStatus.SYNCHRONIZING,
                                "Piece in hand... awaiting drop",
                                rejection_reason=rejection_reason
                            )
                        # Sleep briefly to await piece drop
                        time.sleep(0.040)
                    else:
                        consecutive_uncertain += 1
                        if self._uncertain_start_time is None:
                            self._uncertain_start_time = time.time()

                        if consecutive_uncertain >= 3:
                            uncertain_duration = time.time() - self._uncertain_start_time
                            matched_board, match_conf, heal_reason = self.inference.heal_position(
                                current_board,
                                curr_crops,
                                continuous_uncertain_seconds=uncertain_duration
                            )
                            if matched_board and match_conf >= 0.70:
                                consecutive_uncertain = 0
                                self._uncertain_start_time = None
                                with self._lock:
                                    self._known_board = matched_board.copy()
                                    self._prev_crops = curr_crops
                                    self._prev_thumb = gray_thumb
                                    self._last_san = ""
                                if mgr:
                                    mgr.resynchronize_live_board(matched_board, match_conf)
                            else:
                                if mgr:
                                    mgr.update_sync_status(
                                        SyncStatus.POSITION_UNCERTAIN,
                                        "Position uncertain... Synchronizing move",
                                        rejection_reason=rejection_reason
                                    )
                        else:
                            if mgr:
                                mgr.update_sync_status(
                                    SyncStatus.SYNCHRONIZING,
                                    "Synchronizing move...",
                                    rejection_reason=rejection_reason
                                )

                # Record frame in session recorder rolling buffer
                SessionRecorder.get_instance().record_frame(
                    source="board",
                    image=raw_img,
                    board_fen_before=current_board.fen(),
                    board_fen_after=self._known_board.fen() if self._known_board else "",
                    detected_moves=[m.uci() for m, _ in frame_res.steps] if frame_res.steps else [],
                    verdict=frame_res.verdict.value,
                    notes=frame_res.reason or rejection_reason
                )

                t_total = (time.perf_counter() - t_start) * 1000.0

                # 5. Emit Diagnostics
                if mgr:
                    diag = DiagnosticsData(
                        capture_ms=round(t_cap, 1),
                        recognition_ms=round(t_recog, 1),
                        total_latency_ms=round(t_total, 1),
                        fps=round(curr_fps, 1),
                        sync_status=mgr.sync_status,
                        detected_fen=self._known_board.fen(),
                        authoritative_fen=mgr.live_board.fen(),
                        last_move_san=self._last_san,
                        rejection_reason=rejection_reason,
                        confidence=conf,
                        cropped_image=raw_img,
                        device_pixel_ratio=cal.device_pixel_ratio
                    )
                    mgr.emit_diagnostics(diag)

            except Exception as e:
                print(f"[BoardObserver] Observation loop error: {e}")

            elapsed = time.perf_counter() - t_start
            time.sleep(max(0.020, 0.350 - elapsed))

    def _try_reanchor_drift(self, cal: BoardCalibration) -> bool:
        """
        Detects and recovers from slight window scrolling or position drift (±30px).
        Only adjusts if a genuine chessboard with confirmed checkerboard score is found.
        """
        try:
            pad = 30
            x_pad = max(0, cal.x - pad)
            y_pad = max(0, cal.y - pad)
            w_pad = cal.width + (pad * 2)
            h_pad = cal.height + (pad * 2)

            pad_img = self.capture.capture_region(x_pad, y_pad, w_pad, h_pad)
            if pad_img is None or pad_img.size == 0:
                return False

            rx, ry, rw, rh = self.detector.refine_inner_board(pad_img)
            if rw <= 60 or rh <= 60:
                return False

            dpr = cal.device_pixel_ratio if cal.device_pixel_ratio > 0 else 1.0
            rx_log = int(round(rx / dpr))
            ry_log = int(round(ry / dpr))
            rw_log = int(round(rw / dpr))
            rh_log = int(round(rh / dpr))

            # Must closely match original board dimensions (within 6%)
            if abs(rw_log - cal.width) > max(15, int(cal.width * 0.06)):
                return False
            if abs(rh_log - cal.height) > max(15, int(cal.height * 0.06)):
                return False

            new_x = x_pad + rx_log
            new_y = y_pad + ry_log

            # Drift must be modest (within ±25px)
            if abs(new_x - cal.x) > 25 or abs(new_y - cal.y) > 25:
                return False

            # Verify that the candidate region has a strong checkerboard score
            test_crop = pad_img[ry:ry + rh, rx:rx + rw]
            score = self.detector.compute_checkerboard_score(test_crop)
            if score < 14.0:
                return False

            if abs(new_x - cal.x) >= 2 or abs(new_y - cal.y) >= 2:
                with self._lock:
                    self.calibration.x = new_x
                    self.calibration.y = new_y
                    self.calibration.width = rw_log
                    self.calibration.height = rh_log
                return True
        except Exception:
            pass
        return False

