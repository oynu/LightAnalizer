"""
Mouse Controller for On-Screen Live Chess Clients.
Translates chess moves into physical hardware screen clicks on the calibrated chessboard.
Supports 1-button auto-move mode with DPR scaling, SendInput injection, and smooth gliding.
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

# Optional PyAutoGUI integration for seamless cross-process input synthesis
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.02
except Exception:
    pyautogui = None

# Win32 Constants
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

# Win32 Structures for 64-bit Windows SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p)
    ]

class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _INPUT_UNION)
    ]

try:
    _user32 = ctypes.windll.user32
    _user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    _user32.SendInput.restype = wintypes.UINT
except Exception:
    _user32 = None


class MouseMoveController:
    """
    Translates chess moves into physical on-screen mouse clicks using calibrated
    chessboard coordinates. Uses multi-layer input injection (SendInput, mouse_event,
    and PyAutoGUI) to guarantee the cursor moves visibly and clicks register across
    all browsers and chess clients (Chess.com, Lichess, etc.).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._is_executing = False
        self._auto_move_enabled = False
        self._click_delay_ms = 110  # Natural human dwell between piece click and square click
        self._humanize_glide = True  # Visibly glide cursor across screen

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
        properly scaled by the device pixel ratio (DPR) to match Screen HUD arrows exactly.
        """
        file_idx = chess.square_file(square)
        rank_idx = chess.square_rank(square)

        if cal.orientation_white_bottom:
            col = file_idx
            row = 7 - rank_idx
        else:
            col = 7 - file_idx
            row = rank_idx

        b_size = min(cal.width, cal.height)
        sq_size = b_size / 8.0
        bx = cal.x + (cal.width - b_size) / 2.0
        by = cal.y + (cal.height - b_size) / 2.0

        # Center of square in logical units
        log_x = bx + (col * sq_size) + (sq_size / 2.0)
        log_y = by + (row * sq_size) + (sq_size / 2.0)

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
        """Asynchronously executes a move on screen in a dedicated background worker thread."""
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
            print(f"[MouseMoveController] Executing {move.uci()}: ({x1}, {y1}) -> ({x2}, {y2})")

            # 1. Visibly glide cursor to source piece and click it
            self._move_cursor(x1, y1, smooth=True)
            time.sleep(0.04)
            self._click_at(x1, y1)

            # 2. Natural human dwell delay between selecting piece and choosing destination
            dwell = max(0.12, self._click_delay_ms / 1000.0)
            time.sleep(dwell)

            # 3. Visibly glide cursor to destination square and click it
            self._move_cursor(x2, y2, smooth=True)
            time.sleep(0.04)
            self._click_at(x2, y2)

            # 4. Handle pawn promotion if applicable (default promote to Queen)
            if move.promotion:
                time.sleep(0.10)
                self._click_at(x2, y2)

            success = True
            print(f"[MouseMoveController] Move {move.uci()} successfully clicked on screen.")
        except Exception as e:
            print(f"[MouseMoveController] Execution error: {e}")
        finally:
            with self._lock:
                self._is_executing = False
            if on_complete:
                try:
                    on_complete(success)
                except Exception as ex:
                    print(f"[MouseMoveController] on_complete callback error: {ex}")

    def _to_normalized_coords(self, x: int, y: int) -> Tuple[int, int]:
        """Maps physical pixel coordinates to normalized 0..65535 Windows desktop space."""
        try:
            u32 = ctypes.windll.user32
            vx = u32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
            vy = u32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
            vw = u32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            vh = u32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
            if vw <= 0:
                vw = u32.GetSystemMetrics(0) or 1920
            if vh <= 0:
                vh = u32.GetSystemMetrics(1) or 1080

            norm_x = int(round((x - vx) * 65535.0 / max(1, vw - 1)))
            norm_y = int(round((y - vy) * 65535.0 / max(1, vh - 1)))
            return max(0, min(65535, norm_x)), max(0, min(65535, norm_y))
        except Exception:
            return 0, 0

    def _set_cursor_position(self, x: int, y: int) -> None:
        """Sets cursor position via SetCursorPos, SendInput, and mouse_event."""
        try:
            ctypes.windll.user32.SetCursorPos(int(x), int(y))
        except Exception:
            pass

        norm_x, norm_y = self._to_normalized_coords(x, y)
        flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK

        # SendInput driver-level injection
        if _user32:
            try:
                inp = INPUT()
                inp.type = INPUT_MOUSE
                inp.mi.dx = norm_x
                inp.mi.dy = norm_y
                inp.mi.dwFlags = flags
                inp.mi.mouseData = 0
                inp.mi.time = 0
                inp.mi.dwExtraInfo = None
                _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            except Exception:
                pass

        # mouse_event OS queue injection
        try:
            ctypes.windll.user32.mouse_event(flags, norm_x, norm_y, 0, 0)
        except Exception:
            pass

    def _move_cursor(self, target_x: int, target_y: int, smooth: bool = True) -> None:
        """Moves cursor to target coordinates, optionally with a smooth visible glide."""
        if smooth and self._humanize_glide:
            # Try PyAutoGUI smooth glide first
            if pyautogui:
                try:
                    pyautogui.moveTo(target_x, target_y, duration=0.14, tween=pyautogui.easeInOutQuad)
                    self._set_cursor_position(target_x, target_y)
                    return
                except Exception:
                    pass

            # Fallback smooth interpolation
            try:
                pt = wintypes.POINT()
                if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                    start_x, start_y = pt.x, pt.y
                else:
                    start_x, start_y = target_x, target_y

                dist = math.hypot(target_x - start_x, target_y - start_y)
                steps = min(15, max(4, int(dist / 35.0)))
                for i in range(1, steps + 1):
                    t = i / float(steps)
                    ease_t = t * t * (3.0 - 2.0 * t)
                    curr_x = int(start_x + (target_x - start_x) * ease_t)
                    curr_y = int(start_y + (target_y - start_y) * ease_t)
                    self._set_cursor_position(curr_x, curr_y)
                    time.sleep(0.008)
            except Exception:
                pass

        self._set_cursor_position(target_x, target_y)

    def _send_mouse_button(self, down: bool, x: int, y: int) -> None:
        """Sends physical mouse down or mouse up event through all Win32 layers."""
        norm_x, norm_y = self._to_normalized_coords(x, y)
        btn_flag = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
        flags = btn_flag | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK

        # 1. SendInput
        if _user32:
            try:
                inp = INPUT()
                inp.type = INPUT_MOUSE
                inp.mi.dx = norm_x
                inp.mi.dy = norm_y
                inp.mi.dwFlags = flags
                inp.mi.mouseData = 0
                inp.mi.time = 0
                inp.mi.dwExtraInfo = None
                _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            except Exception:
                pass

        # 2. mouse_event
        try:
            ctypes.windll.user32.mouse_event(flags, norm_x, norm_y, 0, 0)
        except Exception:
            pass

        # 3. PyAutoGUI
        if pyautogui:
            try:
                if down:
                    pyautogui.mouseDown(x=x, y=y, button="left")
                else:
                    pyautogui.mouseUp(x=x, y=y, button="left")
            except Exception:
                pass

    def _click_at(self, x: int, y: int) -> None:
        """Performs a physical click at (x, y) with proper press down, dwell, and release."""
        self._set_cursor_position(x, y)
        time.sleep(0.04)
        self._send_mouse_button(down=True, x=x, y=y)
        time.sleep(0.055)  # 55ms realistic press dwell
        self._send_mouse_button(down=False, x=x, y=y)
        time.sleep(0.04)
