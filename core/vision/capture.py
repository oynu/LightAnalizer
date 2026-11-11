"""
High-performance screen and region capture module using native Qt screen grabbing.
Handles Windows high-DPI scaling, multiple monitors, and zero-copy RGBA alignment.
"""
from __future__ import annotations
import numpy as np
from typing import Optional, Tuple
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from core.types import BoardCalibration

class ScreenCapture:
    """
    Captures screen regions with high-DPI awareness, multi-monitor coordinate translation,
    and fast buffer conversions.
    """
    def __init__(self):
        pass

    def get_screen_info(self, x: Optional[int] = None, y: Optional[int] = None) -> Tuple[float, int, int]:
        """Returns (devicePixelRatio, screen_width, screen_height) in logical units."""
        app = QGuiApplication.instance()
        if not app:
            return 1.0, 1920, 1080
        screen = None
        if x is not None and y is not None:
            screen = QGuiApplication.screenAt(QPoint(x, y))
        if not screen:
            screen = app.primaryScreen()
        if not screen:
            return 1.0, 1920, 1080
        geom = screen.geometry()
        return screen.devicePixelRatio(), geom.width(), geom.height()

    def capture_region(self, x: int, y: int, width: int, height: int) -> Optional[np.ndarray]:
        """
        Captures a specific screen region (in logical screen coordinates).
        Identifies the screen containing the selected region and translates coordinates
        relative to that screen so multiple monitors work correctly.
        Returns an unpadded BGR numpy array (OpenCV compatible).
        """
        app = QGuiApplication.instance()
        if not app:
            return None

        # Clamp region to positive dimensions
        width = max(10, width)
        height = max(10, height)

        center_pt = QPoint(x + width // 2, y + height // 2)
        topleft_pt = QPoint(x, y)

        target_screen = QGuiApplication.screenAt(center_pt) or QGuiApplication.screenAt(topleft_pt)
        if target_screen is None:
            for scr in app.screens():
                geom = scr.geometry()
                if geom.contains(center_pt) or geom.contains(topleft_pt) or geom.intersects(QRect(x, y, width, height)):
                    target_screen = scr
                    break

        if target_screen is None:
            target_screen = app.primaryScreen()

        if not target_screen:
            return None

        geom = target_screen.geometry()
        # Translate coordinates relative to the target screen
        local_x = x - geom.x()
        local_y = y - geom.y()

        pix = target_screen.grabWindow(0, local_x, local_y, width, height)
        if pix.isNull():
            return None

        return self._pixmap_to_bgr(pix)

    def capture_full_screen(self) -> Optional[np.ndarray]:
        """Captures primary desktop in full resolution."""
        app = QGuiApplication.instance()
        if not app:
            return None
        screen = app.primaryScreen()
        if not screen:
            return None
        pix = screen.grabWindow(0)
        if pix.isNull():
            return None
        return self._pixmap_to_bgr(pix)

    def capture_calibrated_board(self, cal: BoardCalibration) -> Optional[np.ndarray]:
        """Captures using BoardCalibration settings."""
        if cal.width <= 0 or cal.height <= 0:
            return None
        return self.capture_region(cal.x, cal.y, cal.width, cal.height)

    def _pixmap_to_bgr(self, pix: QPixmap) -> np.ndarray:
        """
        Converts QPixmap to contiguous BGR numpy array using 4-byte aligned RGBA.
        Guarantees zero stride distortion across display scalings (100%, 125%, 150%, 200%).
        """
        qimg = pix.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = qimg.width(), qimg.height()
        ptr = qimg.bits()
        # Shape is (h, w, 4)
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4))
        # Drop alpha and convert RGBA -> BGR
        bgr = np.ascontiguousarray(arr[:, :, [2, 1, 0]])
        return bgr
