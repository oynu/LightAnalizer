"""
Main application window for LightAnalizer.
Minimalist, uncluttered shell with prominent 'Select Board' action,
live synchronization status pill, and collapsible developer diagnostics.
"""
from __future__ import annotations
import sys
import time
from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QFrame, QPushButton, QLabel, QComboBox, QMenu,
    QStackedWidget, QDialog
)
from PySide6.QtGui import QKeySequence, QShortcut, QAction
from PySide6.QtCore import Qt, Slot, QTimer
from core.types import OperatingMode, SyncStatus, BoardCalibration, DiagnosticsData
from core.game_state_manager import GameStateManager
from core.modes import ModeManager
from core.opponent.repository import OpponentRepository
from core.vision.observer import BoardObserver
from core.vision.moves_tab_observer import MovesTabObserver
from core.vision.screen_overlay import BoardSelectionOverlay
from core.review import GameReviewer

from ui.styles import DARK_THEME_QSS
from ui.views.analysis_view import AnalysisView
from ui.views.review_view import ReviewView
from ui.views.opponent_view import OpponentView
from ui.views.games_view import GamesView
from ui.views.settings_view import SettingsView
from ui.widgets.diagnostics_panel import DiagnosticsPanel
from ui.widgets.screen_hud import ScreenBoardOverlay

class MainWindow(QMainWindow):
    """
    Focused desktop shell designed around live board synchronization and candidate moves.
    """
    def __init__(
        self,
        game_state_mgr: GameStateManager,
        observer: BoardObserver,
        mode_mgr: ModeManager,
        repo: OpponentRepository,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.game_state_mgr = game_state_mgr
        self.observer = observer
        self.game_state_mgr.set_observer(self.observer)
        self.moves_tab_observer = MovesTabObserver(self.game_state_mgr)
        self.mode_mgr = mode_mgr
        self.repo = repo
        self.reviewer = GameReviewer(game_state_mgr.engine_mgr, game_state_mgr.analyzer)

        self.setWindowTitle("LightAnalizer - Premium AI Chess Analysis")
        self._is_compact_mode = False
        self._always_on_top = False
        self._show_mini_board = True
        self._saved_full_size = (900, 640)
        self.resize(380, 680)
        self.setMinimumSize(280, 360)

        self._active_overlay: Optional[BoardSelectionOverlay] = None
        self._diagnostics_visible = False
        self.screen_overlay = ScreenBoardOverlay()
        self._activate_overlay_after_calibration = False

        self._setup_ui()
        self._setup_shortcuts()
        self._connect_signals()

        # Start in sleek Compact HUD mode with visual mini-board and Always-on-Top Pinned by default
        self.toggle_compact_mode(True)
        self.toggle_always_on_top(True)

        # Timer to refresh sync elapsed time (e.g. "Last sync: 2s ago")
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._refresh_sync_pill_time)
        self._sync_timer.start(1000)

        # On Windows, exclude application from screen capture so it never occludes observed boards
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
            except Exception:
                pass

    def _setup_ui(self) -> None:
        self.setStyleSheet(DARK_THEME_QSS)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---------------- TOP NAVIGATION BAR ----------------
        top_bar = QFrame()
        top_bar.setStyleSheet("""
            QFrame {
                background-color: rgba(10, 14, 24, 0.82);
                border-bottom: 1px solid rgba(255, 255, 255, 0.12);
                padding: 4px 12px;
            }
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 6, 12, 6)
        top_layout.setSpacing(12)

        # Brand Logo
        self.lbl_brand = QLabel("LIGHTANALIZER")
        self.lbl_brand.setStyleSheet("font-family: 'Segoe UI Variable Display', 'Inter', sans-serif; font-size: 13px; font-weight: 800; letter-spacing: 1.5px; color: #F8FAFC;")
        top_layout.addWidget(self.lbl_brand)

        top_layout.addSpacing(8)

        # Primary Action: SELECT MOVES TAB
        self.btn_select_moves = QPushButton("📝 Select Moves Tab")
        self.btn_select_moves.setStyleSheet("""
            QPushButton {
                background-color: #00F0FF;
                color: #080B12;
                border: 1px solid rgba(0, 240, 255, 0.60);
                border-radius: 8px;
                padding: 6px 16px;
                font-weight: 800;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #38BDF8;
                border-color: #38BDF8;
            }
        """)
        self.btn_select_moves.clicked.connect(self.open_moves_tab_selector)
        top_layout.addWidget(self.btn_select_moves)

        # Secondary Action: SELECT BOARD (VISION)
        self.btn_select_board = QPushButton("♟ Select Board (Vision)")
        self.btn_select_board.setToolTip("Auto-detect or drag-select screen chessboard (B)")
        self.btn_select_board.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 0.14);
                border-color: rgba(0, 240, 255, 0.35);
                color: #00F0FF;
            }
        """)
        self.btn_select_board.clicked.connect(self.open_board_selector)
        top_layout.addWidget(self.btn_select_board)

        # Action: SET POSITION / STARTING SIDE
        self.btn_set_pos = QPushButton("⚡ Position...")
        self.btn_set_pos.setToolTip("Set starting position (White/Black, FEN, or common openings) (Ctrl+P)")
        self.btn_set_pos.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 0.14);
                border-color: rgba(0, 240, 255, 0.35);
                color: #00F0FF;
            }
        """)
        self.btn_set_pos.clicked.connect(self.open_position_dialog)
        top_layout.addWidget(self.btn_set_pos)

        # Synchronization Status Pill
        self.sync_pill = QLabel("Moves tab unavailable")
        self.sync_pill.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.04);
            color: #94A3B8;
            border-left: 3px solid #64748B;
            border-radius: 8px;
            padding: 5px 12px;
            font-size: 11px;
            font-weight: 600;
        """)
        top_layout.addWidget(self.sync_pill)

        top_layout.addStretch()

        # Playing Side (Color) Toggle
        self.btn_side_toggle = QPushButton("♔ White")
        self.btn_side_toggle.setToolTip("Playing as White (White at bottom). Click or press F to switch to Black")
        self.btn_side_toggle.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.20);
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.14);
            }
        """)
        self.btn_side_toggle.clicked.connect(self.game_state_mgr.toggle_orientation)
        top_layout.addWidget(self.btn_side_toggle)

        # Small Board Toggle for Compact HUD Mode
        self.btn_board_toggle = QPushButton("♟ Board: ON")
        self.btn_board_toggle.setToolTip("Toggle small visual chessboard in compact view (M)")
        self.btn_board_toggle.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 255, 157, 0.14);
                color: #00FF9D;
                border: 1px solid rgba(0, 255, 157, 0.35);
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: rgba(0, 255, 157, 0.24);
                color: #FFFFFF;
            }
        """)
        self.btn_board_toggle.clicked.connect(self.toggle_mini_board)
        top_layout.addWidget(self.btn_board_toggle)

        # Always-On-Top Floating Pin Toggle
        self.btn_pin = QPushButton("📌 Pin")
        self.btn_pin.setToolTip("Keep window floating on top of screen (P)")
        self.btn_pin.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                color: #00F0FF;
                background-color: rgba(0, 240, 255, 0.14);
                border-color: rgba(0, 240, 255, 0.35);
            }
        """)
        self.btn_pin.clicked.connect(self.toggle_always_on_top)
        top_layout.addWidget(self.btn_pin)

        # Compact HUD / Expand View Toggle
        self.btn_compact_toggle = QPushButton("🗗 Compact HUD")
        self.btn_compact_toggle.setToolTip("Toggle between sleek compact HUD and full board view (C)")
        self.btn_compact_toggle.setStyleSheet("""
            QPushButton {
                background-color: rgba(168, 85, 247, 0.14);
                color: #C084FC;
                border: 1px solid rgba(168, 85, 247, 0.35);
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: rgba(168, 85, 247, 0.24);
                color: #FFFFFF;
            }
        """)
        self.btn_compact_toggle.clicked.connect(self.toggle_compact_mode)
        top_layout.addWidget(self.btn_compact_toggle)

        # Operating Mode Selector
        self.mode_widget = QWidget()
        mode_box = QHBoxLayout(self.mode_widget)
        mode_box.setContentsMargins(0, 0, 0, 0)
        mode_box.setSpacing(6)
        lbl_m = QLabel("Mode:")
        lbl_m.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        mode_box.addWidget(lbl_m)

        self.mode_combo = QComboBox()
        self.mode_combo.setFixedWidth(140)
        for m in OperatingMode:
            self.mode_combo.addItem(m.value)
        self.mode_combo.setCurrentText(self.mode_mgr.current_mode.value)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        mode_box.addWidget(self.mode_combo)
        top_layout.addWidget(self.mode_widget)

        # Workspaces Dropdown Menu
        self.btn_menu = QPushButton("Workspaces...")
        self.btn_menu.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 0.14);
                border-color: rgba(0, 240, 255, 0.35);
                color: #00F0FF;
            }
        """)
        self._setup_workspaces_menu()
        top_layout.addWidget(self.btn_menu)

        # Diagnostics Drawer Toggle Button
        self.btn_diag = QPushButton("Diagnostics")
        self.btn_diag.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #00F0FF;
                border-color: rgba(0, 240, 255, 0.35);
            }
        """)
        self.btn_diag.clicked.connect(self._toggle_diagnostics)
        top_layout.addWidget(self.btn_diag)

        main_layout.addWidget(top_bar)

        # ---------------- CENTRAL VIEW CONTAINER ----------------
        self.stacked_views = QStackedWidget()

        self.view_analysis = AnalysisView(self.game_state_mgr, self.mode_mgr)
        self.view_review = ReviewView(self.game_state_mgr.board_state, self.reviewer)
        self.view_opponent = OpponentView(self.repo, self.game_state_mgr.board_state)
        self.view_games = GamesView(self.repo, self.game_state_mgr.board_state, on_game_loaded=lambda: self.switch_view(0))
        self.view_settings = SettingsView(self.game_state_mgr.engine_mgr, self.repo)

        self.stacked_views.addWidget(self.view_analysis)   # 0: Live Analysis
        self.stacked_views.addWidget(self.view_review)     # 1: Review
        self.stacked_views.addWidget(self.view_opponent)   # 2: Opponent
        self.stacked_views.addWidget(self.view_games)      # 3: Games
        self.stacked_views.addWidget(self.view_settings)   # 4: Settings

        main_layout.addWidget(self.stacked_views, stretch=1)

        # ---------------- COLLAPSIBLE DIAGNOSTICS PANEL ----------------
        self.diagnostics_panel = DiagnosticsPanel()
        self.diagnostics_panel.setVisible(False)
        main_layout.addWidget(self.diagnostics_panel)

    def _setup_workspaces_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #080B12;
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 10px;
                padding: 6px;
            }
            QMenu::item {
                padding: 7px 18px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background-color: rgba(0, 240, 255, 0.20);
                color: #00F0FF;
            }
        """)

        act_analysis = menu.addAction("♞  Live Analysis & Board")
        act_analysis.triggered.connect(lambda: self.switch_view(0))

        act_review = menu.addAction("📊  Post-Game Review")
        act_review.triggered.connect(lambda: self.switch_view(1))

        act_opp = menu.addAction("👤  Opponent Intelligence")
        act_opp.triggered.connect(lambda: self.switch_view(2))

        act_pgn = menu.addAction("📁  Game & PGN Library")
        act_pgn.triggered.connect(lambda: self.switch_view(3))

        menu.addSeparator()

        act_set = menu.addAction("⚙  Engine & Settings")
        act_set.triggered.connect(lambda: self.switch_view(4))

        self.btn_menu.setMenu(menu)

    def switch_view(self, index: int) -> None:
        self.stacked_views.setCurrentIndex(index)

    def open_moves_tab_selector(self) -> None:
        """Launches the full-screen overlay to select the chess moves/notation panel."""
        if self._active_overlay is not None:
            try:
                self._active_overlay.close()
            except Exception:
                pass
            self._active_overlay = None

        self._active_overlay = BoardSelectionOverlay(mode="moves_tab")
        self._active_overlay.calibration_confirmed.connect(self._on_moves_tab_confirmed)
        self._active_overlay.cancelled.connect(self._on_overlay_cancelled)
        self._active_overlay.show()

    def _on_overlay_cancelled(self) -> None:
        self._active_overlay = None
        self.show()
        self.raise_()
        self.activateWindow()
        if self._always_on_top:
            self._apply_win32_topmost(True)

    def _on_moves_tab_confirmed(self, cal: BoardCalibration) -> None:
        self._active_overlay = None
        # Clean start on every selection: wipe previous match state and caches
        self.game_state_mgr.reset_for_new_game()
        if self.observer and self.observer.is_active():
            self.observer.stop()
        self.moves_tab_observer.reset_state()
        self.moves_tab_observer.update_calibration(cal)
        if not self.moves_tab_observer.is_active():
            self.moves_tab_observer.start()
        self._update_mode_button_styles()
        # Switch to main live analysis view immediately
        self.switch_view(0)
        self.show()
        self.raise_()
        self.activateWindow()
        if self._always_on_top:
            self._apply_win32_topmost(True)

    def open_board_selector(self) -> None:
        """Launches the full-screen Snipping-Tool board selector overlay (vision mode)."""
        if self._active_overlay is not None:
            try:
                self._active_overlay.close()
            except Exception:
                pass
            self._active_overlay = None

        detector = getattr(self.observer, "detector", None)
        self._active_overlay = BoardSelectionOverlay(detector=detector, mode="board")
        self._active_overlay.calibration_confirmed.connect(self._on_calibration_confirmed)
        self._active_overlay.cancelled.connect(self._on_overlay_cancelled)
        self._active_overlay.show()

    def _on_calibration_confirmed(self, cal: BoardCalibration) -> None:
        self._active_overlay = None
        # Clean start on every board selection: wipe previous match state and caches
        self.game_state_mgr.reset_for_new_game()
        if self.moves_tab_observer and self.moves_tab_observer.is_active():
            self.moves_tab_observer.stop()
        self.observer.reset_state()
        self.observer.update_calibration(cal)
        # Synchronize board and eval bar orientation to match the screen's observed orientation
        self.game_state_mgr.set_orientation(cal.orientation_white_bottom)
        if not self.observer.is_active():
            self.observer.start()
        self._update_mode_button_styles()

        # Synchronize live on-screen HUD overlay if active or requested
        if getattr(self, "_activate_overlay_after_calibration", False) or (hasattr(self, "screen_overlay") and self.screen_overlay and self.screen_overlay.isVisible()):
            self.screen_overlay.update_calibration(cal)
            self.screen_overlay.set_white_at_bottom(cal.orientation_white_bottom)
            self.screen_overlay.set_candidate_moves(self.game_state_mgr.candidates)
            self.screen_overlay.show()
            self.view_analysis.set_screen_hud_active(True)
            self._activate_overlay_after_calibration = False

        # Switch to main analysis view immediately
        self.switch_view(0)
        self.show()
        self.raise_()
        self.activateWindow()
        if self._always_on_top:
            self._apply_win32_topmost(True)

    def _update_mode_button_styles(self) -> None:
        """Visually indicates the active recognition mode (Board Vision vs Moves Tab)."""
        board_active = self.observer and self.observer.is_active()
        moves_active = self.moves_tab_observer and self.moves_tab_observer.is_active()

        if board_active:
            self.btn_select_board.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 255, 157, 0.18);
                    color: #00FF9D;
                    border: 1px solid rgba(0, 255, 157, 0.55);
                    border-radius: 8px;
                    padding: 5px 12px;
                    font-weight: 700;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: rgba(0, 255, 157, 0.28); }
            """)
        else:
            self.btn_select_board.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.05);
                    color: #94A3B8;
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 8px;
                    padding: 5px 12px;
                    font-weight: 600;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: rgba(0, 240, 255, 0.12); color: #00F0FF; }
            """)

        if moves_active:
            self.btn_select_moves.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 240, 255, 0.20);
                    color: #00F0FF;
                    border: 1px solid rgba(0, 240, 255, 0.60);
                    border-radius: 8px;
                    padding: 5px 12px;
                    font-weight: 700;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: rgba(0, 240, 255, 0.30); }
            """)
        else:
            self.btn_select_moves.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.05);
                    color: #94A3B8;
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 8px;
                    padding: 5px 12px;
                    font-weight: 600;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: rgba(0, 240, 255, 0.12); color: #00F0FF; }
            """)

    def _apply_win32_topmost(self, pinned: bool) -> None:
        """Enforces true OS-level topmost z-order via Windows API so clicks in browser never hide the app."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                hwnd = int(self.winId())
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_SHOWWINDOW = 0x0040
                SWP_NOACTIVATE = 0x0010

                user32 = ctypes.windll.user32
                user32.SetWindowPos.argtypes = [
                    wintypes.HWND, wintypes.HWND,
                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    wintypes.UINT
                ]
                user32.SetWindowPos.restype = wintypes.BOOL

                HWND_TOPMOST = wintypes.HWND(-1)
                HWND_NOTOPMOST = wintypes.HWND(-2)
                target = HWND_TOPMOST if pinned else HWND_NOTOPMOST
                user32.SetWindowPos(hwnd, target, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE)
            except Exception:
                pass

    def toggle_always_on_top(self, force_pin: Optional[bool] = None) -> None:
        """Toggles floating always-on-top window mode."""
        self._always_on_top = (not self._always_on_top) if force_pin is None else force_pin
        if self._always_on_top:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            self.btn_pin.setText("📌 Pinned")
            self.btn_pin.setToolTip("Window is permanently floating on top of screen. Click to unpin (P)")
            self.btn_pin.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 240, 255, 0.18);
                    color: #00F0FF;
                    border: 1px solid rgba(0, 240, 255, 0.50);
                    border-radius: 8px;
                    padding: 5px 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: rgba(0, 240, 255, 0.28);
                }
            """)
        else:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
            self.btn_pin.setText("📌 Pin")
            self.btn_pin.setToolTip("Keep window floating on top of screen (P)")
            self.btn_pin.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.05);
                    color: #94A3B8;
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 8px;
                    padding: 5px 10px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    color: #00F0FF;
                    background-color: rgba(0, 240, 255, 0.14);
                    border-color: rgba(0, 240, 255, 0.35);
                }
            """)
        self.show()
        self._apply_win32_topmost(self._always_on_top)

    def toggle_mini_board(self) -> None:
        """Toggles visibility of the small visual chessboard in compact HUD mode."""
        self._show_mini_board = self.view_analysis.toggle_mini_board()
        if self._show_mini_board:
            self.btn_board_toggle.setText("♟ Board: ON")
            self.btn_board_toggle.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 255, 157, 0.14);
                    color: #00FF9D;
                    border: 1px solid rgba(0, 255, 157, 0.35);
                    border-radius: 8px;
                    padding: 5px 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: rgba(0, 255, 157, 0.24);
                    color: #FFFFFF;
                }
            """)
            if self._is_compact_mode:
                self.resize(380, 680)
        else:
            self.btn_board_toggle.setText("♟ Board: OFF")
            self.btn_board_toggle.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.04);
                    color: #64748B;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 8px;
                    padding: 5px 10px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    color: #94A3B8;
                    background-color: rgba(255, 255, 255, 0.08);
                }
            """)
            if self._is_compact_mode:
                self.resize(370, 420)

    def toggle_compact_mode(self, force_compact: Optional[bool] = None) -> None:
        """Toggles between sleek compact HUD card and full desktop view."""
        new_state = (not self._is_compact_mode) if force_compact is None else force_compact
        self._is_compact_mode = new_state

        self.view_analysis.set_compact_mode(new_state, show_mini_board=self._show_mini_board)

        # Toggle secondary controls for a super-clean, distraction-free HUD
        self.lbl_brand.setVisible(not new_state)
        self.btn_select_board.setVisible(True)  # Both recognition modes accessible in compact & expanded
        self.btn_select_moves.setVisible(True)
        self.btn_set_pos.setVisible(not new_state)
        self.mode_widget.setVisible(not new_state)
        self.btn_menu.setVisible(not new_state)
        self.btn_diag.setVisible(not new_state)
        self.btn_board_toggle.setVisible(new_state)

        if new_state:
            self._saved_full_size = self.size()
            self.btn_select_board.setText("♟ Board")
            self.btn_select_moves.setText("📝 Moves")
            self.btn_compact_toggle.setText("⛶ Expand")
            self.btn_compact_toggle.setToolTip("Expand to full board view (C)")
            self.btn_compact_toggle.setStyleSheet("""
                QPushButton {
                    background-color: rgba(168, 85, 247, 0.16);
                    color: #D8B4FE;
                    border: 1px solid rgba(168, 85, 247, 0.45);
                    border-radius: 8px;
                    padding: 5px 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: rgba(168, 85, 247, 0.28);
                    color: #FFFFFF;
                }
            """)
            if self._show_mini_board:
                self.resize(380, 680)
            else:
                self.resize(370, 420)
        else:
            self.btn_select_board.setText("♟ Select Board (Vision)")
            self.btn_select_moves.setText("📝 Select Moves Tab")
            self.btn_compact_toggle.setText("🗗 Compact HUD")
            self.btn_compact_toggle.setToolTip("Shrink to sleek floating HUD (C)")
            self.btn_compact_toggle.setStyleSheet("""
                QPushButton {
                    background-color: rgba(168, 85, 247, 0.14);
                    color: #C084FC;
                    border: 1px solid rgba(168, 85, 247, 0.35);
                    border-radius: 8px;
                    padding: 5px 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: rgba(168, 85, 247, 0.24);
                    color: #FFFFFF;
                }
            """)
            w = max(880, self._saved_full_size.width() if hasattr(self._saved_full_size, 'width') else self._saved_full_size[0])
            h = max(600, self._saved_full_size.height() if hasattr(self._saved_full_size, 'height') else self._saved_full_size[1])
            self.resize(w, h)

        self._update_mode_button_styles()

    def _toggle_diagnostics(self) -> None:
        self._diagnostics_visible = not self._diagnostics_visible
        self.diagnostics_panel.setVisible(self._diagnostics_visible)

    def open_position_dialog(self) -> None:
        """Opens the position and starting side setup dialog."""
        from ui.widgets.position_dialog import PositionSetupDialog
        dlg = PositionSetupDialog(self.game_state_mgr, self)
        dlg.exec()

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+S"), self, self.open_moves_tab_selector)
        QShortcut(QKeySequence("S"), self, self.open_moves_tab_selector)
        QShortcut(QKeySequence("Ctrl+P"), self, self.open_position_dialog)
        QShortcut(QKeySequence("C"), self, self.toggle_compact_mode)
        QShortcut(QKeySequence("P"), self, self.toggle_always_on_top)
        QShortcut(QKeySequence("M"), self, self.toggle_mini_board)
        QShortcut(QKeySequence("B"), self, self.open_board_selector)
        QShortcut(QKeySequence("O"), self, self.toggle_screen_overlay)
        QShortcut(QKeySequence("D"), self, self._toggle_diagnostics)
        QShortcut(QKeySequence("F9"), self, self._on_flag_wrong_move)
        QShortcut(QKeySequence(Qt.Key_Backspace), self, self._on_undo_last_ply)
        QShortcut(QKeySequence(Qt.Key_Left), self, self.game_state_mgr.board_state.step_backward)
        QShortcut(QKeySequence(Qt.Key_Right), self, self.game_state_mgr.board_state.step_forward)
        QShortcut(QKeySequence(Qt.Key_F), self, self.game_state_mgr.toggle_orientation)

    def _on_flag_wrong_move(self) -> None:
        """Saves an incident snapshot to data/sessions/ for offline analysis."""
        from core.vision.session_recorder import SessionRecorder
        rec = SessionRecorder.get_instance()
        incident_path = rec.save_incident("User flagged wrong move (F9)")
        if incident_path:
            name = incident_path.name
            self.sync_pill.setText(f"🚩 Incident saved: {name}")
            self.sync_pill.setStyleSheet("background-color: rgba(255, 42, 133, 0.20); color: #FF2A85; border-left: 3px solid #FF2A85; border-radius: 8px; padding: 5px 12px; font-size: 11px; font-weight: 700;")
            QTimer.singleShot(3500, self._on_game_state_changed)
        else:
            self.sync_pill.setText("Buffer empty (no frames)")
            QTimer.singleShot(2000, self._on_game_state_changed)

    def _on_undo_last_ply(self) -> None:
        """Safety net: reverts the last confirmed move."""
        success = self.game_state_mgr.undo_last_ply()
        if success:
            if hasattr(self, "moves_tab_observer"):
                self.moves_tab_observer.on_undo(
                    self.game_state_mgr.live_moves,
                    self.game_state_mgr.live_board
                )
            self.sync_pill.setText("↩ Undid last move")
            self.sync_pill.setStyleSheet("background-color: rgba(0, 240, 255, 0.20); color: #00F0FF; border-left: 3px solid #00F0FF; border-radius: 8px; padding: 5px 12px; font-size: 11px; font-weight: 700;")
            QTimer.singleShot(2500, self._on_game_state_changed)

    def _connect_signals(self) -> None:
        self.game_state_mgr.add_listener(self._on_game_state_changed)
        self.game_state_mgr.orientation_changed.connect(self._on_orientation_changed)
        self.game_state_mgr.add_diagnostics_listener(self.diagnostics_panel.update_diagnostics)
        self.view_analysis.screen_hud_requested.connect(self.toggle_screen_overlay)
        self._on_game_state_changed()

    def _on_orientation_changed(self, white_bottom: bool) -> None:
        if self.moves_tab_observer and hasattr(self.moves_tab_observer, "calibration"):
            self.moves_tab_observer.calibration.orientation_white_bottom = white_bottom

        if hasattr(self, "screen_overlay") and self.screen_overlay:
            self.screen_overlay.set_white_at_bottom(white_bottom)

        if white_bottom:
            self.btn_side_toggle.setText("♔ White")
            self.btn_side_toggle.setToolTip("Playing as White (White at bottom). Click or press F to switch to Black")
            self.btn_side_toggle.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #F8FAFC;
                    border: 1px solid rgba(255, 255, 255, 0.20);
                    border-radius: 8px;
                    padding: 5px 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.14);
                }
            """)
        else:
            self.btn_side_toggle.setText("♚ Black")
            self.btn_side_toggle.setToolTip("Playing as Black (Black at bottom). Click or press F to switch to White")
            self.btn_side_toggle.setStyleSheet("""
                QPushButton {
                    background-color: rgba(168, 85, 247, 0.14);
                    color: #C084FC;
                    border: 1px solid rgba(168, 85, 247, 0.40);
                    border-radius: 8px;
                    padding: 5px 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: rgba(168, 85, 247, 0.24);
                }
            """)

    def _on_mode_changed(self, text: str) -> None:
        for m in OperatingMode:
            if m.value == text:
                self.mode_mgr.set_mode(m)
                break

    def _on_game_state_changed(self) -> None:
        status = self.game_state_mgr.sync_status
        msg = self.game_state_mgr.status_message

        if status == SyncStatus.SYNCHRONIZED:
            time_diff = int(time.time() - self.game_state_mgr.last_sync_time)
            time_txt = f"{time_diff}s ago" if time_diff > 0 else "just now"
            self.sync_pill.setText(f"Synchronized ({time_txt})")
            self.sync_pill.setStyleSheet("background-color: rgba(0, 255, 157, 0.14); color: #00FF9D; border-left: 3px solid #00FF9D; border-radius: 8px; padding: 5px 12px; font-size: 11px; font-weight: 700;")
        elif status == SyncStatus.SYNCHRONIZING:
            self.sync_pill.setText("Synchronizing...")
            self.sync_pill.setStyleSheet("background-color: rgba(255, 184, 0, 0.14); color: #FFB800; border-left: 3px solid #FFB800; border-radius: 8px; padding: 5px 12px; font-size: 11px; font-weight: 700;")
        elif status == SyncStatus.POSITION_UNCERTAIN:
            self.sync_pill.setText("Position uncertain")
            self.sync_pill.setStyleSheet("background-color: rgba(255, 42, 133, 0.14); color: #FF2A85; border-left: 3px solid #FF2A85; border-radius: 8px; padding: 5px 12px; font-size: 11px; font-weight: 700;")
        else:
            self.sync_pill.setText("Moves tab unavailable")
            self.sync_pill.setStyleSheet("background-color: rgba(255, 255, 255, 0.04); color: #94A3B8; border-left: 3px solid #64748B; border-radius: 8px; padding: 5px 12px; font-size: 11px; font-weight: 600;")

        self._sync_screen_overlay()

    def _sync_screen_overlay(self) -> None:
        """Propagates latest moves and board perspective to the on-screen live overlay."""
        if hasattr(self, "screen_overlay") and self.screen_overlay and self.screen_overlay.isVisible():
            orient = getattr(self.game_state_mgr, "orientation_white_bottom", True)
            if callable(orient):
                orient = orient()
            self.screen_overlay.set_white_at_bottom(bool(orient))
            self.screen_overlay.set_candidate_moves(self.game_state_mgr.candidates)

    def toggle_screen_overlay(self) -> None:
        """
        Toggles live on-screen HUD overlay that paints neon move arrows directly
        over the physical chessboard of the match being played on screen.
        """
        if hasattr(self, "screen_overlay") and self.screen_overlay and self.screen_overlay.isVisible():
            self.screen_overlay.hide()
            self.view_analysis.set_screen_hud_active(False)
        else:
            cal = getattr(self.observer, "calibration", None)
            if not cal or not cal.is_calibrated:
                self._activate_overlay_after_calibration = True
                self.open_board_selector()
                return

            orient = getattr(self.game_state_mgr, "orientation_white_bottom", True)
            if callable(orient):
                orient = orient()
            self.screen_overlay.update_calibration(cal)
            self.screen_overlay.set_white_at_bottom(bool(orient))
            self.screen_overlay.set_candidate_moves(self.game_state_mgr.candidates)
            self.screen_overlay.show()
            self.view_analysis.set_screen_hud_active(True)

    def _refresh_sync_pill_time(self) -> None:
        if self.game_state_mgr.sync_status == SyncStatus.SYNCHRONIZED:
            time_diff = int(time.time() - self.game_state_mgr.last_sync_time)
            time_txt = f"{time_diff}s ago" if time_diff > 0 else "just now"
            self.sync_pill.setText(f"Synchronized ({time_txt})")

    def closeEvent(self, event) -> None:
        self._sync_timer.stop()
        self.moves_tab_observer.stop()
        self.observer.stop()
        if hasattr(self, "screen_overlay") and self.screen_overlay:
            try:
                self.screen_overlay.close()
            except Exception:
                pass
        self.game_state_mgr.engine_mgr.stop_engine()
        super().closeEvent(event)
