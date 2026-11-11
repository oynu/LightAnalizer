"""
Mouse Controller for On-Screen Live Chess Clients.
Translates chess moves into physical hardware-level screen clicks on the calibrated chessboard.

Each move is played exactly like a human would: glide to the piece, click it, short pause,
glide to the target square, click it. Every mouse button event is injected exactly ONCE through
Win32 `SendInput` (falling back to `mouse_event` only if SendInput is rejected), so a click can
never be doubled/toggled.
"""
from __future__ import annotations
import time
import math
import random
import threading
from typing import Optional, Tuple, Callable
import ctypes
from ctypes import wintypes
import chess
from core.types import BoardCalibration

# Win32 Constants
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000


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
    chessboard coordinates (HUD-accurate, DPI aware, multi-monitor aware).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._is_executing = False
        self._auto_move_enabled = False
        self._rng = random.Random()
        self._humanize_glide = True
        self._click_jitter = 0.16      # click anywhere within the central ~32% of a square
        self.last_error: str = ""

    @property
    def auto_move_enabled(self) -> bool:
        return self._auto_move_enabled

    @auto_move_enabled.setter
    def auto_move_enabled(self, enabled: bool) -> None:
        self._auto_move_enabled = enabled

    @property
    def is_executing(self) -> bool:
        return self._is_executing

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def get_square_coords(
        self,
        cal: BoardCalibration,
        square: chess.Square,
        jitter: float = 0.0
    ) -> Tuple[int, int]:
        """
        Physical screen (x, y) of a square center, matching the Screen HUD arrow geometry exactly.
        `jitter` (fraction of a square) randomly offsets the point inside the square like a human click.
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

        log_x = bx + (col * sq_size) + (sq_size / 2.0)
        log_y = by + (row * sq_size) + (sq_size / 2.0)

        if jitter > 0:
            log_x += self._rng.uniform(-jitter, jitter) * sq_size
            log_y += self._rng.uniform(-jitter, jitter) * sq_size

        dpr = getattr(cal, "device_pixel_ratio", 1.0)
        if not dpr or dpr <= 0:
            dpr = 1.0

        return int(round(log_x * dpr)), int(round(log_y * dpr))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
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
        self.last_error = ""
        try:
            x1, y1 = self.get_square_coords(cal, move.from_square, jitter=self._click_jitter)
            x2, y2 = self.get_square_coords(cal, move.to_square, jitter=self._click_jitter)
            print(f"[MouseMoveController] Executing {move.uci()}: ({x1}, {y1}) -> ({x2}, {y2})")

            # 1. Glide to the piece and click it
            self._glide_to(x1, y1, self._rng.uniform(0.16, 0.38))
            time.sleep(self._rng.uniform(0.05, 0.12))
            self._click()

            # 2. Human pause between selecting the piece and choosing the destination
            time.sleep(self._rng.uniform(0.12, 0.34))

            # 3. Glide to destination and click it
            self._glide_to(x2, y2, self._rng.uniform(0.16, 0.40))
            time.sleep(self._rng.uniform(0.05, 0.12))
            self._click()

            # 4. Pawn promotion: auto-queen popup normally sits on the destination square
            if move.promotion:
                time.sleep(self._rng.uniform(0.25, 0.45))
                self._click()

            success = True
            print(f"[MouseMoveController] Move {move.uci()} clicked on screen.")
        except Exception as e:
            self.last_error = str(e)
            print(f"[MouseMoveController] Execution error: {e}")
        finally:
            with self._lock:
                self._is_executing = False
            if on_complete:
                try:
                    on_complete(success)
                except Exception as ex:
                    print(f"[MouseMoveController] on_complete callback error: {ex}")

    # ------------------------------------------------------------------
    # Win32 injection primitives
    # ------------------------------------------------------------------
    def _to_normalized_coords(self, x: int, y: int) -> Tuple[int, int]:
        """Maps physical pixel coordinates to normalized 0..65535 virtual-desktop space."""
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

    def _inject(self, flags: int, dx: int = 0, dy: int = 0) -> bool:
        """Injects ONE mouse event. SendInput first, legacy mouse_event only if SendInput was rejected."""
        if _user32 is not None:
            try:
                inp = INPUT()
                inp.type = INPUT_MOUSE
                inp.mi.dx = dx
                inp.mi.dy = dy
                inp.mi.mouseData = 0
                inp.mi.dwFlags = flags
                inp.mi.time = 0
                inp.mi.dwExtraInfo = None
                if _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1:
                    return True
            except Exception:
                pass
        try:
            ctypes.windll.user32.mouse_event(flags, dx, dy, 0, 0)
            return True
        except Exception:
            return False

    def _set_cursor_position(self, x: int, y: int) -> None:
        """Teleports the cursor: SetCursorPos plus an absolute SendInput move so apps receive WM_MOUSEMOVE."""
        x, y = int(x), int(y)
        try:
            ctypes.windll.user32.SetCursorPos(x, y)
        except Exception:
            pass
        nx, ny = self._to_normalized_coords(x, y)
        self._inject(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny)

    def _get_cursor_position(self) -> Optional[Tuple[int, int]]:
        try:
            pt = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return pt.x, pt.y
        except Exception:
            pass
        return None

    def _glide_to(self, tx: int, ty: int, duration: float) -> None:
        """Moves the cursor along a slightly curved, eased path so the motion is visible and natural."""
        start = self._get_cursor_position()
        if not self._humanize_glide or start is None:
            self._set_cursor_position(tx, ty)
            return

        sx, sy = start
        dist = math.hypot(tx - sx, ty - sy)
        if dist < 3:
            self._set_cursor_position(tx, ty)
            return

        steps = max(10, min(60, int(duration / 0.008)))
        # Quadratic Bezier control point offset perpendicular to the path
        nx, ny = -(ty - sy) / dist, (tx - sx) / dist
        bend = self._rng.uniform(-0.10, 0.10) * dist
        cx = (sx + tx) / 2.0 + nx * bend
        cy = (sy + ty) / 2.0 + ny * bend

        for i in range(1, steps + 1):
            t = i / float(steps)
            e = t * t * (3.0 - 2.0 * t)
            px = (1 - e) ** 2 * sx + 2 * (1 - e) * e * cx + e ** 2 * tx
            py = (1 - e) ** 2 * sy + 2 * (1 - e) * e * cy + e ** 2 * ty
            self._set_cursor_position(int(round(px)), int(round(py)))
            time.sleep(duration / steps)

        self._set_cursor_position(tx, ty)
        pos = self._get_cursor_position()
        if pos is not None and (abs(pos[0] - tx) > 3 or abs(pos[1] - ty) > 3):
            try:
                ctypes.windll.user32.SetCursorPos(int(tx), int(ty))
            except Exception:
                pass

    def _click(self) -> None:
        """One physical left click at the current cursor position (single down + single up)."""
        self._inject(MOUSEEVENTF_LEFTDOWN)
        time.sleep(self._rng.uniform(0.045, 0.095))
        self._inject(MOUSEEVENTF_LEFTUP)
        time.sleep(0.03)
