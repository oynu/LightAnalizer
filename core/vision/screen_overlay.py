"""
Full-screen interactive board selection overlay.
Provides intuitive Snipping-Tool style click-and-drag selection,
auto-detection with candidate cards, real-time 8x8 grid preview, and DPI scaling.
"""
from __future__ import annotations
from typing import Optional, Callable, List, Tuple
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QFrame, QApplication
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPixmap, QImage,
    QCursor, QKeyEvent, QMouseEvent
)
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from core.types import BoardCalibration
from core.vision.capture import ScreenCapture
from core.vision.board_detector import BoardDetector

class BoardSelectionOverlay(QWidget):
    """
    Snipping-tool style full-screen overlay for manual rectangle drawing
    or 1-click automatic chessboard detection.
    Supports both 'moves_tab' and 'board' selection modes.
    """
    calibration_confirmed = Signal(object)  # Emits BoardCalibration
    cancelled = Signal()

    def __init__(
        self,
        detector: Optional[BoardDetector] = None,
        parent: Optional[QWidget] = None,
        mode: str = "moves_tab"
    ):
        super().__init__(parent)
        self.mode = mode
        self.detector = detector or BoardDetector()
        self.capture = ScreenCapture()

        # Window flags: frameless, stays on top, tool window
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CrossCursor))

        self._desktop_pixmap: Optional[QPixmap] = None
        self._desktop_bgr: Optional[np.ndarray] = None
        self._dpr = 1.0

        # Dragging state (in logical screen coordinates)
        self._is_dragging = False
        self._drag_start = QPoint()
        self._drag_current = QPoint()
        self._selected_rect: Optional[QRect] = None
        self._cursor_pos: QPoint = QPoint(-100, -100)
        self._active_handle: Optional[str] = None
        self._handle_radius = 6

        # Auto-detected candidates [(x, y, w, h, score)]
        self._candidates: List[Tuple[int, int, int, int, float]] = []
        self._hovered_candidate_idx = -1

        self._setup_desktop_snapshot()
        self._setup_top_banner()

    def _setup_desktop_snapshot(self) -> None:
        """Captures frozen desktop snapshot once on launch."""
        screen = QApplication.primaryScreen()
        if not screen:
            return

        self._dpr = screen.devicePixelRatio()
        geom = screen.geometry()
        self.setGeometry(geom)

        pix = screen.grabWindow(0)
        self._desktop_pixmap = pix

        # Convert to BGR for OpenCV detector
        qimg = pix.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = qimg.width(), qimg.height()
        ptr = qimg.bits()
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4))
        self._desktop_bgr = np.ascontiguousarray(arr[:, :, [2, 1, 0]])

    def _get_handles(self, r: QRect) -> Dict[str, QPoint]:
        cx = r.x() + (r.width() // 2)
        cy = r.y() + (r.height() // 2)
        return {
            'tl': r.topLeft(),
            'tr': r.topRight(),
            'bl': r.bottomLeft(),
            'br': r.bottomRight(),
            'tc': QPoint(cx, r.top()),
            'bc': QPoint(cx, r.bottom()),
            'ml': QPoint(r.left(), cy),
            'mr': QPoint(r.right(), cy),
        }

    def _hit_test_handle(self, pos: QPoint) -> Optional[str]:
        if not self._selected_rect:
            return None
        handles = self._get_handles(self._selected_rect)
        for h_id, pt in handles.items():
            if (pos - pt).manhattanLength() <= 10:
                return h_id
        return None

    def _setup_top_banner(self) -> None:
        """Top instructional toolbar."""
        self.banner = QFrame(self)
        self.banner.setStyleSheet("""
            QFrame {
                background-color: #16181D;
                border: 1px solid #2B2D35;
                border-radius: 8px;
            }
            QLabel {
                color: #EDEDED;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton {
                background-color: #1F2127;
                color: #EDEDED;
                border: 1px solid #2B2D35;
                border-radius: 5px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2D303B;
            }
            QPushButton#ConfirmBtn {
                background-color: #2563EB;
                border: 1px solid #3B82F6;
                color: #FFFFFF;
            }
            QPushButton#ConfirmBtn:hover {
                background-color: #1D4ED8;
            }
            QPushButton#AutoBtn {
                background-color: #065F46;
                border: 1px solid #059669;
                color: #6EE7B7;
            }
            QPushButton#AutoBtn:hover {
                background-color: #047857;
            }
        """)

        layout = QHBoxLayout(self.banner)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        if self.mode == "moves_tab":
            icon_lbl = QLabel("📝 <b>Select Moves Tab</b> — Drag a rectangle over the chess moves / notation panel, then confirm:")
        else:
            icon_lbl = QLabel("🎯 <b>Select Chessboard</b> — Click and drag a rectangle over the board, or auto-detect:")
        layout.addWidget(icon_lbl)

        layout.addStretch()

        self.btn_auto = QPushButton("🔍 Auto-Detect Board")
        self.btn_auto.setObjectName("AutoBtn")
        self.btn_auto.clicked.connect(self._run_auto_detect)
        if self.mode != "moves_tab":
            layout.addWidget(self.btn_auto)

        self.btn_confirm = QPushButton("✓ Confirm Selection")
        self.btn_confirm.setObjectName("ConfirmBtn")
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.clicked.connect(self._confirm_selection)
        layout.addWidget(self.btn_confirm)

        self.btn_cancel = QPushButton("✕ Cancel (Esc)")
        self.btn_cancel.clicked.connect(self.close)
        layout.addWidget(self.btn_cancel)

        # Center banner horizontally at top of screen
        self.banner.adjustSize()
        bx = (self.width() - self.banner.width()) // 2
        self.banner.move(bx, 24)

    def _run_auto_detect(self) -> None:
        """Runs automatic chessboard detector and highlights found candidates."""
        if self._desktop_bgr is None:
            return

        candidates = self.detector.detect_chessboards(self._desktop_bgr)
        self._candidates = candidates

        if candidates:
            # Select highest scoring candidate automatically
            bx, by, bw, bh, _ = candidates[0]
            # Convert physical device pixels to logical coordinates
            lx = int(bx / self._dpr)
            ly = int(by / self._dpr)
            lw = int(bw / self._dpr)
            lh = int(bh / self._dpr)
            self._selected_rect = QRect(lx, ly, lw, lh)
            self.btn_confirm.setEnabled(True)
            self.update()
        else:
            self._selected_rect = None
            self.btn_confirm.setEnabled(False)
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            self._cursor_pos = pos

            # Check handle hits on existing selection
            h_id = self._hit_test_handle(pos)
            if h_id:
                self._active_handle = h_id
                self._drag_start = pos
                return

            # Check if clicked inside a detected candidate
            for idx, (cx, cy, cw, ch, _) in enumerate(self._candidates):
                lcx, lcy, lcw, lch = int(cx / self._dpr), int(cy / self._dpr), int(cw / self._dpr), int(ch / self._dpr)
                candidate_rect = QRect(lcx, lcy, lcw, lch)
                if candidate_rect.contains(pos):
                    self._selected_rect = candidate_rect
                    self.btn_confirm.setEnabled(True)
                    self.update()
                    return

            # Start dragging new selection rectangle
            self._is_dragging = True
            self._active_handle = None
            self._drag_start = pos
            self._drag_current = pos
            self._selected_rect = None
            self.btn_confirm.setEnabled(False)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._cursor_pos = event.pos()

        if self._active_handle and self._selected_rect:
            # Resizing via handle
            r = self._selected_rect
            dx = event.pos().x() - self._drag_start.x()
            dy = event.pos().y() - self._drag_start.y()
            self._drag_start = event.pos()

            x, y, w, h = r.x(), r.y(), r.width(), r.height()
            h_id = self._active_handle

            if 'l' in h_id:
                x += dx
                w -= dx
            if 'r' in h_id:
                w += dx
            if 't' in h_id:
                y += dy
                h -= dy
            if 'b' in h_id:
                h += dy

            if w >= 50 and h >= 50:
                self._selected_rect = QRect(x, y, w, h)
            self.update()
            return

        if self._is_dragging:
            self._drag_current = event.pos()
            x1 = min(self._drag_start.x(), self._drag_current.x())
            y1 = min(self._drag_start.y(), self._drag_current.y())
            w = abs(self._drag_current.x() - self._drag_start.x())
            h = abs(self._drag_current.y() - self._drag_start.y())
            self._selected_rect = QRect(x1, y1, w, h)
            self.btn_confirm.setEnabled(w >= 60 and h >= 60)
            self.update()
            return

        # Update cursor when hovering over handles
        h_id = self._hit_test_handle(event.pos())
        if h_id in ['tl', 'br']:
            self.setCursor(QCursor(Qt.SizeFDiagCursor))
        elif h_id in ['tr', 'bl']:
            self.setCursor(QCursor(Qt.SizeBDiagCursor))
        elif h_id in ['tc', 'bc']:
            self.setCursor(QCursor(Qt.SizeVerCursor))
        elif h_id in ['ml', 'mr']:
            self.setCursor(QCursor(Qt.SizeHorCursor))
        else:
            self.setCursor(QCursor(Qt.CrossCursor))

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            if self._active_handle:
                self._active_handle = None
                self._refine_selection()
                self.update()
                return

            if self._is_dragging:
                self._is_dragging = False
                if self._selected_rect and self._selected_rect.width() >= 60 and self._selected_rect.height() >= 60:
                    self._refine_selection()
                    self.btn_confirm.setEnabled(True)
                else:
                    self._selected_rect = None
                    self.btn_confirm.setEnabled(False)
                self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._selected_rect:
                self._confirm_selection()
        elif self._selected_rect:
            step = 5 if (event.modifiers() & Qt.ShiftModifier) else 1
            r = self._selected_rect
            if event.key() == Qt.Key_Left:
                self._selected_rect = QRect(r.x() - step, r.y(), r.width(), r.height())
            elif event.key() == Qt.Key_Right:
                self._selected_rect = QRect(r.x() + step, r.y(), r.width(), r.height())
            elif event.key() == Qt.Key_Up:
                self._selected_rect = QRect(r.x(), r.y() - step, r.width(), r.height())
            elif event.key() == Qt.Key_Down:
                self._selected_rect = QRect(r.x(), r.y() + step, r.width(), r.height())
            self.update()

    def _refine_selection(self) -> None:
        """Refines the dragged selection to snap to square and auto-align inner board."""
        if not self._selected_rect or self._desktop_bgr is None:
            return

        if self.mode == "moves_tab":
            return

        r = self._selected_rect
        px = int(r.x() * self._dpr)
        py = int(r.y() * self._dpr)
        pw = int(r.width() * self._dpr)
        ph = int(r.height() * self._dpr)

        # Bounds check
        dh, dw = self._desktop_bgr.shape[:2]
        px = max(0, min(dw - 10, px))
        py = max(0, min(dh - 10, py))
        pw = max(10, min(dw - px, pw))
        ph = max(10, min(dh - py, ph))

        crop = self._desktop_bgr[py:py + ph, px:px + pw]
        rx, ry, rw, rh = self.detector.refine_inner_board(crop)

        if rw > 60 and rh > 60:
            final_px = px + rx
            final_py = py + ry
            final_pw = rw
            final_ph = rh
            lx = int(final_px / self._dpr)
            ly = int(final_py / self._dpr)
            lw = int(final_pw / self._dpr)
            lh = int(final_ph / self._dpr)
            self._selected_rect = QRect(lx, ly, lw, lh)

    def _confirm_selection(self) -> None:
        if not self._selected_rect:
            return

        r = self._selected_rect
        cal = BoardCalibration(
            x=r.x(),
            y=r.y(),
            width=r.width(),
            height=r.height(),
            device_pixel_ratio=self._dpr,
            is_calibrated=True
        )

        if self.mode == "moves_tab":
            self.calibration_confirmed.emit(cal)
            self.close()
            return

        # Determine orientation from crop for chessboard mode
        if self._desktop_bgr is not None:
            px = int(r.x() * self._dpr)
            py = int(r.y() * self._dpr)
            pw = int(r.width() * self._dpr)
            ph = int(r.height() * self._dpr)
            crop = self._desktop_bgr[py:py + ph, px:px + pw]
            crops = self.detector.segment_squares(crop, white_at_bottom=True)
            cal.orientation_white_bottom = self.detector.determine_orientation(crops)

        self.calibration_confirmed.emit(cal)
        self.close()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. Draw Desktop Snapshot
        if self._desktop_pixmap:
            painter.drawPixmap(0, 0, self._desktop_pixmap)

        # 2. Draw Dimming Mask (Semi-transparent black overlay)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

        # 3. Draw Detected Auto-Candidates (Chessboard mode only)
        if self.mode != "moves_tab":
            for cx, cy, cw, ch, score in self._candidates:
                lcx = int(cx / self._dpr)
                lcy = int(cy / self._dpr)
                lcw = int(cw / self._dpr)
                lch = int(ch / self._dpr)
                cand_rect = QRect(lcx, lcy, lcw, lch)

                # Draw green outline
                pen = QPen(QColor("#10B981"), 2, Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(cand_rect)

                # Draw score tag
                tag_rect = QRect(lcx, max(0, lcy - 22), 120, 20)
                painter.fillRect(tag_rect, QColor("#064E3B"))
                painter.setPen(QColor("#34D399"))
                painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
                painter.drawText(tag_rect, Qt.AlignCenter, f"Chessboard ({score:.0f})")

        # 4. Draw Selected Rectangle Cutout
        if self._selected_rect:
            r = self._selected_rect

            # Clear cutout in the dimming mask so the selected board is bright and visible
            if self._desktop_pixmap:
                src_rect = QRect(int(r.x() * self._dpr), int(r.y() * self._dpr), int(r.width() * self._dpr), int(r.height() * self._dpr))
                sub_pix = self._desktop_pixmap.copy(src_rect)
                painter.drawPixmap(r, sub_pix)

            # Draw bounding box border
            border_pen = QPen(QColor("#3B82F6"), 2, Qt.SolidLine)
            painter.setPen(border_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(r)

            if self.mode == "moves_tab":
                # Subtle glowing tint over the selected notation tab
                painter.fillRect(r, QColor(59, 130, 246, 25))
            else:
                # Draw 8x8 internal grid preview lines for chessboard
                grid_pen = QPen(QColor(59, 130, 246, 120), 1, Qt.DashLine)
                painter.setPen(grid_pen)
                cell_w = r.width() / 8.0
                cell_h = r.height() / 8.0

                for i in range(1, 8):
                    gx = int(r.x() + (i * cell_w))
                    painter.drawLine(gx, r.y(), gx, r.y() + r.height())
                    gy = int(r.y() + (i * cell_h))
                    painter.drawLine(r.x(), gy, r.x() + r.width(), gy)

            # Draw resize handles at 8 control points
            handles = self._get_handles(r)
            for pt in handles.values():
                painter.setPen(QPen(QColor("#FFFFFF"), 1.5))
                painter.setBrush(QBrush(QColor("#3B82F6")))
                painter.drawEllipse(pt, self._handle_radius, self._handle_radius)

            # Dimension tag underneath
            label_text = f"Moves Tab: {r.width()} × {r.height()} px" if self.mode == "moves_tab" else f"{r.width()} × {r.height()} px"
            tag_width = 160 if self.mode == "moves_tab" else 140
            dim_rect = QRect(r.x(), r.y() + r.height() + 8, tag_width, 22)
            painter.fillRect(dim_rect, QColor("#1E2025"))
            painter.setPen(QColor("#93C5FD"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(dim_rect, Qt.AlignCenter, label_text)

        # 5. Draw 2.5x Magnifier Loupe near cursor while dragging or hovering
        if (self._is_dragging or self._active_handle or self._selected_rect is None) and self._desktop_pixmap:
            pos = self._cursor_pos
            if pos.x() >= 0 and pos.y() >= 0:
                lx = pos.x() + 25
                ly = pos.y() + 25
                if lx + 130 > self.width():
                    lx = pos.x() - 145
                if ly + 130 > self.height():
                    ly = pos.y() - 145

                loupe_rect = QRectF(lx, ly, 110, 110)
                phys_cx = int(pos.x() * self._dpr)
                phys_cy = int(pos.y() * self._dpr)
                sub_sz = int(44 * self._dpr)
                src_x = max(0, phys_cx - (sub_sz // 2))
                src_y = max(0, phys_cy - (sub_sz // 2))

                sub_pix = self._desktop_pixmap.copy(QRect(src_x, src_y, sub_sz, sub_sz))
                scaled_pix = sub_pix.scaled(110, 110, Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)

                painter.save()
                path = QPainterPath()
                path.addEllipse(loupe_rect)
                painter.setClipPath(path)
                painter.drawPixmap(loupe_rect.toRect(), scaled_pix)

                # Magnifier crosshair
                painter.setPen(QPen(QColor(255, 255, 255, 220), 1))
                ccx = lx + 55
                ccy = ly + 55
                painter.drawLine(int(ccx - 12), int(ccy), int(ccx + 12), int(ccy))
                painter.drawLine(int(ccx), int(ccy - 12), int(ccx), int(ccy + 12))
                painter.restore()

                # Loupe glass ring
                painter.setPen(QPen(QColor("#3B82F6"), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(loupe_rect)

                # Coordinate pill
                tag = QRect(int(lx + 8), int(ly + 88), 94, 16)
                painter.fillRect(tag, QColor(15, 17, 23, 230))
                painter.setPen(QColor("#93C5FD"))
                painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                painter.drawText(tag, Qt.AlignCenter, f"{pos.x()}, {pos.y()}")

        painter.end()

    def closeEvent(self, event) -> None:
        self.cancelled.emit()
        super().closeEvent(event)
