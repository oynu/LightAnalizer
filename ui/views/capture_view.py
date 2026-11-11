"""
Screen capture, board calibration, and piece recognition validation view.
Provides manual calibration controls, auto-detection, and live preview.
"""
from __future__ import annotations
from typing import Optional
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QSpinBox, QCheckBox, QMessageBox, QGroupBox
)
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt
from core.types import BoardCalibration
from core.vision.capture import ScreenCapture
from core.vision.board_detector import BoardDetector
from core.vision.piece_classifier import PieceClassifier
from core.vision.observer import BoardObserver
from core.board_state import BoardState

class CaptureView(QWidget):
    """
    Renders interactive screen capture calibration, orientation toggles, and recognition tests.
    """
    def __init__(self, observer: BoardObserver, board_state: BoardState, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.observer = observer
        self.board_state = board_state
        self.capture = ScreenCapture()
        self.detector = BoardDetector()
        self.classifier = PieceClassifier()

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # ---------------- LEFT PANEL: CALIBRATION CONTROLS ----------------
        ctrl_panel = QFrame()
        ctrl_panel.setFixedWidth(340)
        ctrl_layout = QVBoxLayout(ctrl_panel)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(12)

        lbl_title = QLabel("Screen Capture & Calibration")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF;")
        ctrl_layout.addWidget(lbl_title)

        privacy_note = QLabel("🔒 Privacy Notice: All screen processing occurs 100% locally on your PC. No screenshots are transmitted.")
        privacy_note.setWordWrap(True)
        privacy_note.setStyleSheet("background-color: #161B26; color: #93C5FD; border-radius: 5px; padding: 8px; font-size: 11px;")
        ctrl_layout.addWidget(privacy_note)

        # Coordinates Group
        coord_group = QGroupBox("Chessboard Boundaries (Pixels)")
        coord_layout = QVBoxLayout(coord_group)
        coord_layout.setSpacing(8)

        # X & Y
        row_xy = QHBoxLayout()
        row_xy.addWidget(QLabel("X:"))
        self.spin_x = QSpinBox()
        self.spin_x.setRange(0, 7680)
        self.spin_x.setValue(self.observer.calibration.x)
        row_xy.addWidget(self.spin_x)

        row_xy.addWidget(QLabel("Y:"))
        self.spin_y = QSpinBox()
        self.spin_y.setRange(0, 4320)
        self.spin_y.setValue(self.observer.calibration.y)
        row_xy.addWidget(self.spin_y)
        coord_layout.addLayout(row_xy)

        # Width & Height
        row_wh = QHBoxLayout()
        row_wh.addWidget(QLabel("Width:"))
        self.spin_w = QSpinBox()
        self.spin_w.setRange(100, 4000)
        self.spin_w.setValue(self.observer.calibration.width)
        row_wh.addWidget(self.spin_w)

        row_wh.addWidget(QLabel("Height:"))
        self.spin_h = QSpinBox()
        self.spin_h.setRange(100, 4000)
        self.spin_h.setValue(self.observer.calibration.height)
        row_wh.addWidget(self.spin_h)
        coord_layout.addLayout(row_wh)

        ctrl_layout.addWidget(coord_group)

        # Orientation Checkbox
        self.chk_white_bottom = QCheckBox("Orientation: White at Bottom")
        self.chk_white_bottom.setChecked(self.observer.calibration.orientation_white_bottom)
        ctrl_layout.addWidget(self.chk_white_bottom)

        # Actions Row
        self.btn_auto_detect = QPushButton("🔍 Auto-Detect Board from Screen")
        self.btn_auto_detect.setStyleSheet("""
            QPushButton {
                background-color: #1F2127;
                color: #EDEDED;
                border: 1px solid #2B2D35;
                border-radius: 5px;
                padding: 8px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2D303B;
            }
        """)
        self.btn_auto_detect.clicked.connect(self._auto_detect_board)
        ctrl_layout.addWidget(self.btn_auto_detect)

        self.btn_test_snap = QPushButton("📸 Test Capture Snapshot")
        self.btn_test_snap.setStyleSheet("background-color: #1F2127; color: #EDEDED; border: 1px solid #2B2D35; border-radius: 5px; padding: 8px;")
        self.btn_test_snap.clicked.connect(self._test_capture)
        ctrl_layout.addWidget(self.btn_test_snap)

        self.btn_test_recog = QPushButton("♟ Test Piece Recognition")
        self.btn_test_recog.setStyleSheet("background-color: #1F2127; color: #EDEDED; border: 1px solid #2B2D35; border-radius: 5px; padding: 8px;")
        self.btn_test_recog.clicked.connect(self._test_recognition)
        ctrl_layout.addWidget(self.btn_test_recog)

        # Observation Toggle
        self.btn_toggle_obs = QPushButton("Start Screen Observation")
        self.btn_toggle_obs.setStyleSheet("""
            QPushButton {
                background-color: #065F46;
                color: #6EE7B7;
                border: 1px solid #059669;
                border-radius: 6px;
                padding: 10px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.btn_toggle_obs.clicked.connect(self._toggle_observation)
        ctrl_layout.addWidget(self.btn_toggle_obs)

        ctrl_layout.addStretch()
        main_layout.addWidget(ctrl_panel)

        # ---------------- RIGHT PANEL: CAPTURE PREVIEW ----------------
        preview_panel = QFrame()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)

        lbl_prev_title = QLabel("Captured Region Preview")
        lbl_prev_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #FFFFFF;")
        preview_layout.addWidget(lbl_prev_title)

        self.preview_label = QLabel("Click 'Test Capture Snapshot' or 'Auto-Detect Board' to view calibrated screen area.")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("""
            background-color: #141518;
            border: 1px dashed #2B2D35;
            border-radius: 8px;
            color: #6B7280;
        """)
        preview_layout.addWidget(self.preview_label, stretch=1)

        self.recog_status_lbl = QLabel("")
        self.recog_status_lbl.setStyleSheet("color: #34D399; font-size: 12px; font-weight: 600;")
        preview_layout.addWidget(self.recog_status_lbl)

        main_layout.addWidget(preview_panel)

        # Sync spinboxes
        self.spin_x.valueChanged.connect(self._apply_calibration)
        self.spin_y.valueChanged.connect(self._apply_calibration)
        self.spin_w.valueChanged.connect(self._apply_calibration)
        self.spin_h.valueChanged.connect(self._apply_calibration)
        self.chk_white_bottom.toggled.connect(self._apply_calibration)

    def _apply_calibration(self) -> None:
        cal = BoardCalibration(
            x=self.spin_x.value(),
            y=self.spin_y.value(),
            width=self.spin_w.value(),
            height=self.spin_h.value(),
            orientation_white_bottom=self.chk_white_bottom.isChecked()
        )
        self.observer.update_calibration(cal)

    def _auto_detect_board(self) -> None:
        full_img = self.capture.capture_full_screen()
        if full_img is None:
            QMessageBox.warning(self, "Capture Error", "Could not capture desktop screen.")
            return

        rect = self.detector.detect_board_region(full_img)
        if rect:
            rx, ry, rw, rh = rect
            self.spin_x.setValue(rx)
            self.spin_y.setValue(ry)
            self.spin_w.setValue(rw)
            self.spin_h.setValue(rh)
            self._apply_calibration()
            self._test_capture()
            QMessageBox.information(self, "Board Detected", f"Detected board at X:{rx}, Y:{ry}, Size:{rw}x{rh}.")
        else:
            QMessageBox.warning(self, "Not Found", "Could not find a chessboard automatically. Please adjust coordinates manually.")

    def _test_capture(self) -> None:
        cal = self.observer.calibration
        img = self.capture.capture_region(cal.x, cal.y, cal.width, cal.height)
        if img is None:
            QMessageBox.warning(self, "Capture Error", "Could not capture designated region.")
            return

        # Convert BGR to QPixmap for preview
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg)

        scaled_pix = pix.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled_pix)

    def _test_recognition(self) -> None:
        cal = self.observer.calibration
        img = self.capture.capture_region(cal.x, cal.y, cal.width, cal.height)
        if img is None:
            QMessageBox.warning(self, "Capture Error", "No image to classify.")
            return

        crops = self.detector.segment_squares(img, cal.orientation_white_bottom)
        board, conf = self.observer.inference.reconstruct_full_board(crops)

        if board:
            fen = board.fen()
            self.recog_status_lbl.setText(f"✓ Recognized Position (Confidence {conf*100:.0f}%): {fen}")
            reply = QMessageBox.question(
                self, "Apply Position?",
                f"Recognized position with {conf*100:.0f}% confidence.\n\nFEN: {fen}\n\nLoad this position onto the active board?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.board_state.load_fen(fen)
        else:
            self.recog_status_lbl.setText("⚠ Position recognition low confidence or invalid board.")
            QMessageBox.warning(self, "Uncertain Recognition", "Could not reliably reconstruct a legal chess position. Please check board calibration.")

    def _toggle_observation(self) -> None:
        if self.observer.is_active():
            self.observer.stop()
            self.btn_toggle_obs.setText("Start Screen Observation")
            self.btn_toggle_obs.setStyleSheet("background-color: #065F46; color: #6EE7B7; border: 1px solid #059669; border-radius: 6px; padding: 10px; font-weight: 700;")
        else:
            self.observer.start()
            self.btn_toggle_obs.setText("⏹ Stop Screen Observation")
            self.btn_toggle_obs.setStyleSheet("background-color: #7F1D1D; color: #FCA5A5; border: 1px solid #DC2626; border-radius: 6px; padding: 10px; font-weight: 700;")
