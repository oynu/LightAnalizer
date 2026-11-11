"""
Mouse Controller for On-Screen Live Chess Clients.
Translates chess board moves into precise physical screen clicks on the calibrated chessboard.
Supports manual 1-click execution (Space / UI button) and optional auto-play mode with
natural humanized delays and safety failsafes.
"""
from __future__ import annotations
import time
import math
import threading
from typing import Optional, Tuple, Callable
import ctypes
from ctypes import wintypes
import chess
from core.types import BoardCalibration

# Win32 Constants
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_MOVE = 0x0001

class MouseMoveController:
    """
    Translates chess moves into on-screen clicks using calibrated chessboard coordinates.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._is_executing = False
        self._auto_click_enabled = False
        self._click_delay_ms = 85  # Human-like delay between piece click and destination
        self._humanize_glide = True  # Smooth cursor glide instead of instant jump
        self._last_played_ply = -1

    @property
    def auto_click_enabled(self) -> bool:
        return self._auto_click_enabled

    @auto_click_enabled.setter
    def auto_click_enabled(self, enabled: bool) -> None:
        self._auto_click_enabled = enabled

    @property
    def is_executing(self) -> bool:
        return self._is_executing

    def get_square_coords(self, cal: BoardCalibration, square: chess.Square) -> Tuple[int, int]:
        """Calculates the physical screen (x, y) center point of a chess square."""
        file_idx = chess.square_file(square)
        rank_idx = chess.square_rank(square)

        if cal.orientation_white_bottom:
            col = file_idx
            row = 7 - rank_idx
        else:
            col = 7 - file_idx
            row = rank_idx

        sq_w = cal.width / 8.0
        sq_h = cal.height / 8.0

        center_x = int(cal.x + (col * sq_w) + (sq_w / 2.0))
        center_y = int(cal.y + (row * sq_h) + (sq_h / 2.0))
        return center_x, center_y

    def execute_move_async(
        self,
        cal: BoardCalibration,
        move: chess.Move,
        on_complete: Optional[Callable[[bool], None]] = None
    ) -> bool:
        """Asynchronously executes a move on screen in a background thread."""
        if not cal or not cal.is_calibrated:
            return False

        with self._lock:
            if self._is_executing:
                return False
            self._is_executing = True

        thread = threading.Thread(
            target=self._worker_execute,
            args=(cal, move, on_complete),
            daemon=True
        )
        thread.start()
        return True

    def _worker_execute(
        self,
        cal: BoardCalibration,
        move: chess.Move,
        on_complete: Optional[Callable[[bool], None]]
    ) -> None:
        success = False
        try:
            x1, y1 = self.get_square_coords(cal, move.from_square)
            x2, y2 = self.get_square_coords(cal, move.to_square)

            # 1. Move to source piece & click
            self._move_cursor_to(x1, y1)
            time.sleep(0.02)
            self._send_click(x1, y1)

            # 2. Dwell delay (simulates natural human reaction)
            time.sleep(max(0.04, self._click_delay_ms / 1000.0))

            # 3. Move to destination square & click
            self._move_cursor_to(x2, y2)
            time.sleep(0.02)
            self._send_click(x2, y2)

            # 4. Handle promotion if applicable (default promote to Queen)
            if move.promotion:
                time.sleep(0.08)
                # On most web clients, Queen is either automatic or pops up on the arrival square
                self._send_click(x2, y2)

            success = True
        except Exception as e:
            print(f"[MouseMoveController] Execution error: {e}")
        finally:
            with self._lock:
                self._is_executing = False
            if on_complete:
                try:
                    on_complete(success)
                except Exception:
                    pass

    def _move_cursor_to(self, target_x: int, target_y: int) -> None:
        """Moves cursor to target point, optionally with natural micro-glide."""
        if not self._humanize_glide:
            ctypes.windll.user32.SetCursorPos(target_x, target_y)
            return

        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        start_x, start_y = pt.x, pt.y

        dist = math.hypot(target_x - start_x, target_y - start_y)
        steps = min(12, max(3, int(dist / 50.0)))

        for i in range(1, steps + 1):
            t = i / float(steps)
            # Smooth cubic ease-in-out curve
            ease_t = t * t * (3.0 - 2.0 * t)
            curr_x = int(start_x + (target_x - start_x) * ease_t)
            curr_y = int(start_y + (target_y - start_y) * ease_t)
            ctypes.windll.user32.SetCursorPos(curr_x, curr_y)
            time.sleep(0.005)

        ctypes.windll.user32.SetCursorPos(target_x, target_y)

    def _send_click(self, x: int, y: int) -> None:
        """Sends a physical left mouse click at the current coordinates."""
        ctypes.windll.user32.SetCursorPos(x, y)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.025)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
