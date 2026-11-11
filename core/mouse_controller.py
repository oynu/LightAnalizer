"""
Mouse Controller for On-Screen Live Chess Clients.
Translates chess board moves into precise physical screen clicks on the calibrated chessboard.
Supports 1-button auto-move mode with DPR scaling, window activation, and natural dwell timing.
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
        self._auto_move_enabled = False
        self._click_delay_ms = 95  # Natural dwell between piece click and square click
        self._humanize_glide = True  # Smooth cursor glide instead of instant jump
        self._last_played_ply = -1

    @property
    def auto_move_enabled(self) -> bool:
        return self._auto_move_enabled

    @auto_move_enabled.setter
    def auto_move_enabled(self, enabled: bool) -> None:
        self._auto_move_enabled = enabled

    @property
    def is_executing(self) -> bool:
        return self._is_executing

    def get_square_coords(self, cal: BoardCalibration, square: chess.Square) -> Tuple[int, int]:
        """
        Calculates physical screen (x, y) coordinates for the center of a chess square,
        properly scaled by the device pixel ratio (DPR) so clicks land dead-center on screen.
        """
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

        # Logical center in Qt coordinates
        log_x = cal.x + (col * sq_w) + (sq_w / 2.0)
        log_y = cal.y + (row * sq_h) + (sq_h / 2.0)

        # Scale to physical screen coordinates for Windows SetCursorPos & mouse_event
        dpr = getattr(cal, "device_pixel_ratio", 1.0)
        if not dpr or dpr <= 0:
            dpr = 1.0

        phys_x = int(round(log_x * dpr))
        phys_y = int(round(log_y * dpr))
        return phys_x, phys_y

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

            # Bring target client/browser window into foreground focus if needed
            pt = wintypes.POINT(x1, y1)
            target_hwnd = ctypes.windll.user32.WindowFromPoint(pt)
            root_hwnd = ctypes.windll.user32.GetAncestor(target_hwnd, 2)  # GA_ROOT
            if root_hwnd:
                ctypes.windll.user32.SetForegroundWindow(root_hwnd)
                time.sleep(0.04)

            # 1. Click the piece you want to move
            self._move_cursor_to(x1, y1)
            self._send_click(x1, y1)

            # 2. Realistic pause between selecting piece and choosing destination square
            time.sleep(max(0.08, self._click_delay_ms / 1000.0))

            # 3. Click the square you want to move it to
            self._move_cursor_to(x2, y2)
            self._send_click(x2, y2)

            # 4. Handle pawn promotion if applicable (default promote to Queen)
            if move.promotion:
                time.sleep(0.08)
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
        """Moves cursor to target physical point, optionally with natural micro-glide."""
        if not self._humanize_glide:
            ctypes.windll.user32.SetCursorPos(target_x, target_y)
            return

        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        start_x, start_y = pt.x, pt.y

        dist = math.hypot(target_x - start_x, target_y - start_y)
        steps = min(12, max(4, int(dist / 45.0)))

        for i in range(1, steps + 1):
            t = i / float(steps)
            ease_t = t * t * (3.0 - 2.0 * t)
            curr_x = int(start_x + (target_x - start_x) * ease_t)
            curr_y = int(start_y + (target_y - start_y) * ease_t)
            ctypes.windll.user32.SetCursorPos(curr_x, curr_y)
            time.sleep(0.005)

        ctypes.windll.user32.SetCursorPos(target_x, target_y)

    def _send_click(self, x: int, y: int) -> None:
        """Positions cursor and performs a clean physical click with proper dwell time."""
        ctypes.windll.user32.SetCursorPos(x, y)
        time.sleep(0.03)  # Let target window register WM_MOUSEMOVE
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.035)  # Natural press duration
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.03)
