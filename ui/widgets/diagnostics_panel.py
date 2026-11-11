"""
Developer diagnostics and telemetry panel.
Provides real-time inspection of captured screen crop, latencies, FEN, and rejection logs.
"""
from __future__ import annotations
from typing import Optional
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QScrollArea
)
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt, Slot, QMetaObject, Q_ARG
from core.types import DiagnosticsData, SyncStatus

class DiagnosticsPanel(QFrame):
    """
    Developer diagnostics drawer displaying live capture telemetry and rejection reasons.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("DiagnosticsPanel")
        self.setStyleSheet("""
            QFrame#DiagnosticsPanel {
                background-color: rgba(10, 14, 24, 0.88);
                border-top: 1px solid rgba(255, 255, 255, 0.12);
                padding: 10px;
            }
            QLabel {
                font-family: 'JetBrains Mono', 'Consolas', monospace;
                font-size: 11px;
                color: #94A3B8;
            }
            QLabel.Value {
                color: #F8FAFC;
                font-weight: 700;
            }
            QLabel.Header {
                font-family: 'Segoe UI Variable Display', 'Inter', sans-serif;
                font-size: 11px;
                font-weight: 800;
                color: #00F0FF;
                letter-spacing: 0.8px;
            }
        """)
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(14, 10, 14, 10)
        main_layout.setSpacing(18)

        # 1. Left: Captured Crop Preview
        crop_box = QVBoxLayout()
        lbl_crop_title = QLabel("CAPTURED LIVE CROP")
        lbl_crop_title.setProperty("class", "Header")
        crop_box.addWidget(lbl_crop_title)

        self.preview_lbl = QLabel("No frame")
        self.preview_lbl.setFixedSize(120, 120)
        self.preview_lbl.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 10px;
            color: #64748B;
        """)
        self.preview_lbl.setAlignment(Qt.AlignCenter)
        crop_box.addWidget(self.preview_lbl)
        main_layout.addLayout(crop_box)

        # 2. Middle: Latency & Telemetry Grid
        telemetry_box = QVBoxLayout()
        lbl_tel_title = QLabel("LATENCY & SYSTEM TELEMETRY")
        lbl_tel_title.setProperty("class", "Header")
        telemetry_box.addWidget(lbl_tel_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(5)

        grid.addWidget(QLabel("Capture Latency:"), 0, 0)
        self.lbl_cap_ms = QLabel("0.0 ms")
        self.lbl_cap_ms.setProperty("class", "Value")
        grid.addWidget(self.lbl_cap_ms, 0, 1)

        grid.addWidget(QLabel("Recognition Latency:"), 1, 0)
        self.lbl_rec_ms = QLabel("0.0 ms")
        self.lbl_rec_ms.setProperty("class", "Value")
        grid.addWidget(self.lbl_rec_ms, 1, 1)

        grid.addWidget(QLabel("Total Pipeline:"), 2, 0)
        self.lbl_tot_ms = QLabel("0.0 ms")
        self.lbl_tot_ms.setProperty("class", "Value")
        grid.addWidget(self.lbl_tot_ms, 2, 1)

        grid.addWidget(QLabel("Observation FPS:"), 3, 0)
        self.lbl_fps = QLabel("0.0")
        self.lbl_fps.setProperty("class", "Value")
        grid.addWidget(self.lbl_fps, 3, 1)

        telemetry_box.addLayout(grid)
        main_layout.addLayout(telemetry_box)

        # 3. Right: FEN & Validation Log
        state_box = QVBoxLayout()
        lbl_state_title = QLabel("STATE VERIFICATION & REJECTION LOG")
        lbl_state_title.setProperty("class", "Header")
        state_box.addWidget(lbl_state_title)

        self.lbl_sync_stat = QLabel("Status: BOARD_UNAVAILABLE")
        self.lbl_sync_stat.setProperty("class", "Value")
        self.lbl_sync_stat.setStyleSheet("color: #FF2A85; font-weight: 700;")
        state_box.addWidget(self.lbl_sync_stat)

        self.lbl_last_move = QLabel("Last Move: None")
        self.lbl_last_move.setStyleSheet("color: #F8FAFC;")
        state_box.addWidget(self.lbl_last_move)

        self.lbl_fen = QLabel("FEN: None")
        self.lbl_fen.setWordWrap(True)
        self.lbl_fen.setStyleSheet("color: #00F0FF; font-size: 10px;")
        state_box.addWidget(self.lbl_fen)

        self.lbl_rejection = QLabel("Rejection Reason: None")
        self.lbl_rejection.setStyleSheet("color: #FFB800; font-size: 10px;")
        state_box.addWidget(self.lbl_rejection)

        main_layout.addLayout(state_box, stretch=1)

    def update_diagnostics(self, diag: DiagnosticsData) -> None:
        if not self.isVisible():
            return

        self.lbl_cap_ms.setText(f"{diag.capture_ms:.1f} ms")
        self.lbl_rec_ms.setText(f"{diag.recognition_ms:.1f} ms")
        self.lbl_tot_ms.setText(f"{diag.total_latency_ms:.1f} ms")
        self.lbl_fps.setText(f"{diag.fps:.1f} Hz")

        status_str = diag.sync_status.value
        conf_str = f"{diag.confidence*100:.0f}%"
        self.lbl_sync_stat.setText(f"Status: {status_str} (conf: {conf_str})")
        if "SYNCED" in status_str or "READY" in status_str:
            self.lbl_sync_stat.setStyleSheet("color: #00FF9D; font-weight: 700;")
        elif "SCANNING" in status_str or "WAITING" in status_str or "OBSCURED" in status_str:
            self.lbl_sync_stat.setStyleSheet("color: #FFB800; font-weight: 700;")
        else:
            self.lbl_sync_stat.setStyleSheet("color: #FF2A85; font-weight: 700;")

        self.lbl_last_move.setText(f"Last Move: {diag.last_move_san or 'None'}")
        self.lbl_fen.setText(f"Live FEN: {diag.detected_fen}")
        self.lbl_rejection.setText(f"Notice: {diag.rejection_reason or 'None (normal sync)'}")

        # Update preview image safely
        try:
            if diag.cropped_image is not None and diag.cropped_image.size > 0:
                rgb = cv2.cvtColor(diag.cropped_image, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
                pix = QPixmap.fromImage(qimg)
                self.preview_lbl.setPixmap(pix.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            pass
