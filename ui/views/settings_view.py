"""
Engine and application settings configuration view.
"""
from __future__ import annotations
import os
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QDoubleSpinBox, QFileDialog, QMessageBox,
    QGroupBox, QCheckBox
)
from core.engine_manager import EngineManager, EngineConfig
from core.opponent.repository import OpponentRepository

class SettingsView(QWidget):
    """
    Renders engine configuration, resource limits, and data privacy tools.
    """
    def __init__(self, engine_mgr: EngineManager, repo: OpponentRepository, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine_mgr = engine_mgr
        self.repo = repo
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        title = QLabel("Engine & Application Settings")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(title)

        # Engine Configuration Group
        engine_group = QGroupBox("Stockfish UCI Engine")
        engine_layout = QVBoxLayout(engine_group)
        engine_layout.setSpacing(10)

        # Path row
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Executable Path:"))
        self.path_input = QLineEdit(self.engine_mgr.config.engine_path)
        path_row.addWidget(self.path_input, stretch=1)
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_engine)
        path_row.addWidget(btn_browse)
        engine_layout.addLayout(path_row)

        # Resource limits: Threads & Hash
        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("Threads:"))
        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 64)
        self.spin_threads.setValue(self.engine_mgr.config.threads)
        res_row.addWidget(self.spin_threads)

        res_row.addWidget(QLabel("Hash Memory (MB):"))
        self.spin_hash = QSpinBox()
        self.spin_hash.setRange(16, 16384)
        self.spin_hash.setValue(self.engine_mgr.config.hash_mb)
        res_row.addWidget(self.spin_hash)

        res_row.addWidget(QLabel("Analysis Depth:"))
        self.spin_depth = QSpinBox()
        self.spin_depth.setRange(5, 50)
        self.spin_depth.setValue(self.engine_mgr.config.depth)
        res_row.addWidget(self.spin_depth)

        res_row.addWidget(QLabel("Time Limit (s):"))
        self.spin_time = QDoubleSpinBox()
        self.spin_time.setRange(0.2, 30.0)
        self.spin_time.setSingleStep(0.5)
        self.spin_time.setValue(self.engine_mgr.config.time_limit_sec)
        res_row.addWidget(self.spin_time)

        engine_layout.addLayout(res_row)

        # Engine Actions
        actions_row = QHBoxLayout()
        btn_test = QPushButton("Test UCI Engine Connection")
        btn_test.setStyleSheet("background-color: #1F2127; color: #60A5FA; border: 1px solid #2B2D35; padding: 6px 12px; border-radius: 5px;")
        btn_test.clicked.connect(self._test_engine)
        actions_row.addWidget(btn_test)

        btn_save = QPushButton("Save & Restart Engine")
        btn_save.setStyleSheet("background-color: #2563EB; color: #FFFFFF; font-weight: 600; padding: 6px 14px; border-radius: 5px;")
        btn_save.clicked.connect(self._save_engine_settings)
        actions_row.addWidget(btn_save)
        actions_row.addStretch()

        engine_layout.addLayout(actions_row)
        layout.addWidget(engine_group)

        # Data Privacy & Storage Group
        privacy_group = QGroupBox("Local Data Privacy & Storage")
        privacy_layout = QVBoxLayout(privacy_group)
        privacy_layout.setSpacing(8)

        lbl_priv = QLabel("LightAnalizer operates entirely locally. All game logs, positions, and opponent profiles are stored in a private SQLite database on this machine.")
        lbl_priv.setWordWrap(True)
        lbl_priv.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        privacy_layout.addWidget(lbl_priv)

        db_path_lbl = QLabel(f"Database Location: {self.repo.db_path}")
        db_path_lbl.setStyleSheet("color: #6B7280; font-size: 11px;")
        privacy_layout.addWidget(db_path_lbl)

        btn_clear_db = QPushButton("Delete All Personal Profiles & History")
        btn_clear_db.setStyleSheet("background-color: #311313; color: #EF4444; border: 1px solid #7F1D1D; padding: 6px 12px; border-radius: 5px; max-width: 260px;")
        btn_clear_db.clicked.connect(self._clear_database)
        privacy_layout.addWidget(btn_clear_db)

        layout.addWidget(privacy_group)
        layout.addStretch()

    def _browse_engine(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Stockfish Binary", "", "Executables (*.exe);;All Files (*)")
        if file_path:
            self.path_input.setText(file_path)

    def _save_engine_settings(self) -> None:
        path = self.path_input.text().strip()
        threads = self.spin_threads.value()
        hash_mb = self.spin_hash.value()
        depth = self.spin_depth.value()
        time_lim = self.spin_time.value()

        self.engine_mgr.config.engine_path = path
        self.engine_mgr.config.threads = threads
        self.engine_mgr.config.hash_mb = hash_mb
        self.engine_mgr.config.depth = depth
        self.engine_mgr.config.time_limit_sec = time_lim

        # Restart engine
        self.engine_mgr.stop_engine()
        success = self.engine_mgr.start_engine()
        if success:
            QMessageBox.information(self, "Engine Saved", "Engine settings saved and engine restarted successfully.")
        else:
            QMessageBox.warning(self, "Restart Failed", f"Could not start engine at '{path}'. Please check file path.")

    def _test_engine(self) -> None:
        self.engine_mgr.stop_engine()
        success = self.engine_mgr.start_engine()
        if success and self.engine_mgr._engine:
            eng_id = self.engine_mgr._engine.id.get('name', 'Stockfish')
            QMessageBox.information(self, "Engine Connected", f"Successfully connected to engine:\n\n{eng_id}")
        else:
            QMessageBox.warning(self, "Engine Error", f"Failed to connect to engine at '{self.engine_mgr.config.engine_path}'.")

    def _clear_database(self) -> None:
        reply = QMessageBox.question(
            self, "Clear Database",
            "This will delete all stored games and opponent profiles. Are you sure?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            opps = self.repo.list_opponents()
            for o in opps:
                self.repo.delete_opponent(o.id)
            QMessageBox.information(self, "Cleared", "All local games and opponent profiles have been cleared.")
