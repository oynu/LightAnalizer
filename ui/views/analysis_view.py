"""
Streamlined primary analysis view.
Focuses strictly on the prominent live chessboard and top-3 candidate moves.
"""
from __future__ import annotations
from typing import Optional, List
import chess
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFrame, QLabel,
    QPushButton, QScrollArea, QSplitter
)
from PySide6.QtCore import Qt
from core.types import CandidateMove, PositionSummary, SyncStatus
from core.game_state_manager import GameStateManager
from core.modes import ModeManager
from ui.widgets.chessboard import ChessboardWidget
from ui.widgets.eval_bar import EvalBarWidget
from ui.widgets.candidate_card import CandidateCard
from ui.widgets.move_list import MoveListWidget

class AnalysisView(QWidget):
    """
    Focused live analysis workspace with high-visibility board and clear candidate move recommendations.
    """
    def __init__(
        self,
        game_state_mgr: GameStateManager,
        mode_mgr: ModeManager,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.game_state_mgr = game_state_mgr
        self.mode_mgr = mode_mgr

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(16, 12, 16, 12)
        self.main_layout.setSpacing(16)

        # ---------------- LEFT: PROMINENT BOARD CONTAINER ----------------
        self.board_container = QFrame()
        self.board_container.setObjectName("BoardContainer")
        board_layout = QVBoxLayout(self.board_container)
        board_layout.setContentsMargins(0, 0, 0, 0)
        board_layout.setSpacing(8)

        # Variation Exploration Banner (hidden by default)
        self.variation_banner = QFrame()
        self.variation_banner.setStyleSheet("""
            QFrame {
                background-color: rgba(168, 85, 247, 0.16);
                border: 1px solid rgba(168, 85, 247, 0.40);
                border-radius: 10px;
                padding: 6px 14px;
            }
            QLabel {
                color: #E9D5FF;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton {
                background-color: #A855F7;
                color: #080B12;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: 800;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #C084FC;
            }
        """)
        var_layout = QHBoxLayout(self.variation_banner)
        var_layout.setContentsMargins(8, 4, 8, 4)
        var_layout.addWidget(QLabel("🔍 Exploring Analysis Variation"))
        var_layout.addStretch()
        self.btn_return_live = QPushButton("Return to Live Game ↩")
        self.btn_return_live.clicked.connect(self._on_return_to_live)
        var_layout.addWidget(self.btn_return_live)
        self.variation_banner.setVisible(False)
        board_layout.addWidget(self.variation_banner)

        # Board + Eval Bar row
        board_row = QHBoxLayout()
        board_row.setSpacing(10)

        self.eval_bar = EvalBarWidget()
        self.board_widget = ChessboardWidget()

        board_row.addWidget(self.eval_bar)
        board_row.addWidget(self.board_widget, stretch=1)
        board_layout.addLayout(board_row, stretch=1)

        # Board Navigation Controls
        self.ctrl_row_widget = QWidget()
        ctrl_row = QHBoxLayout(self.ctrl_row_widget)
        ctrl_row.setContentsMargins(0, 0, 0, 0)
        ctrl_row.setSpacing(8)

        btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 0.14);
                border-color: rgba(0, 240, 255, 0.35);
                color: #00F0FF;
            }
        """

        self.btn_flip = QPushButton("Flip Board ⟲")
        self.btn_flip.setStyleSheet(btn_style)
        self.btn_flip.clicked.connect(self._on_flip_board)
        ctrl_row.addWidget(self.btn_flip)

        self.btn_reset_pos = QPushButton("⚡ Position...")
        self.btn_reset_pos.setToolTip("Set starting position (White/Black, FEN, or common openings)")
        self.btn_reset_pos.setStyleSheet(btn_style)
        self.btn_reset_pos.clicked.connect(self._open_position_dialog)
        ctrl_row.addWidget(self.btn_reset_pos)

        self.btn_toggle_arrows = QPushButton("Arrows ✓")
        self.btn_toggle_arrows.setStyleSheet(btn_style)
        self.btn_toggle_arrows.clicked.connect(self._toggle_arrows)
        ctrl_row.addWidget(self.btn_toggle_arrows)

        ctrl_row.addStretch()
        board_layout.addWidget(self.ctrl_row_widget)

        self.main_layout.addWidget(self.board_container, stretch=6)

        # ---------------- RIGHT: MOVE ANALYSIS & COACH TAKEAWAY ----------------
        self.analysis_container = QFrame()
        self.analysis_container.setObjectName("AnalysisContainer")
        self.analysis_container.setStyleSheet("""
            QFrame#AnalysisContainer {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 16px;
            }
        """)
        self.analysis_layout = QVBoxLayout(self.analysis_container)
        self.analysis_layout.setContentsMargins(14, 14, 14, 14)
        self.analysis_layout.setSpacing(10)

        # Header: Coach Takeaway
        self.coach_card = QFrame()
        self.coach_card.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 240, 255, 0.08);
                border: 1px solid rgba(0, 240, 255, 0.35);
                border-left: 4px solid #00F0FF;
                border-radius: 12px;
                padding: 10px;
            }
        """)
        coach_layout = QVBoxLayout(self.coach_card)
        coach_layout.setContentsMargins(8, 6, 8, 6)
        coach_layout.setSpacing(4)
        self.lbl_coach = QLabel("● WHITE TO MOVE")
        self.lbl_coach.setStyleSheet("font-size: 11px; font-weight: 800; color: #00F0FF; letter-spacing: 0.8px;")
        self.coach_text = QLabel("Awaiting engine calculation...")
        self.coach_text.setWordWrap(True)
        self.coach_text.setStyleSheet("font-size: 13px; color: #F8FAFC; line-height: 1.4;")
        coach_layout.addWidget(self.lbl_coach)
        coach_layout.addWidget(self.coach_text)
        self.analysis_layout.addWidget(self.coach_card)

        # Top 3 Candidates
        cand_scroll = QScrollArea()
        cand_scroll.setWidgetResizable(True)
        cand_scroll.setFrameShape(QFrame.NoFrame)
        cand_widget = QWidget()
        cand_vbox = QVBoxLayout(cand_widget)
        cand_vbox.setContentsMargins(0, 0, 0, 0)
        cand_vbox.setSpacing(8)

        self.card_1 = CandidateCard()
        self.card_2 = CandidateCard()
        self.card_3 = CandidateCard()

        cand_vbox.addWidget(self.card_1)
        cand_vbox.addWidget(self.card_2)
        cand_vbox.addWidget(self.card_3)
        cand_vbox.addStretch()
        cand_scroll.setWidget(cand_widget)
        self.analysis_layout.addWidget(cand_scroll, stretch=1)

        # Compact Move History Stepper at bottom
        self.move_list_widget = MoveListWidget()
        self.move_list_widget.setFixedHeight(95)
        self.analysis_layout.addWidget(self.move_list_widget)

        self.main_layout.addWidget(self.analysis_container, stretch=5)

        self._prev_rendered_move: Optional[chess.Move] = None

    def set_compact_mode(self, enabled: bool, show_mini_board: bool = True) -> None:
        """
        Toggles between compact HUD mode and full desktop view.
        In compact mode, arranges vertically with a crisp small mini-board (if enabled)
        and the top candidate move recommendations.
        """
        from PySide6.QtWidgets import QBoxLayout
        self._is_compact = enabled
        self._show_mini_board = show_mini_board

        if enabled:
            self.main_layout.setDirection(QBoxLayout.TopToBottom)
            self.move_list_widget.setVisible(False)
            self.eval_bar.setVisible(False)
            self.ctrl_row_widget.setVisible(False)

            if show_mini_board:
                self.board_container.setVisible(True)
                self.board_widget.setMaximumSize(220, 220)
                self.board_widget.setMinimumSize(140, 140)
            else:
                self.board_container.setVisible(False)

            self.main_layout.setContentsMargins(6, 4, 6, 4)
            self.main_layout.setSpacing(6)
            self.analysis_layout.setContentsMargins(6, 4, 6, 4)
        else:
            self.main_layout.setDirection(QBoxLayout.LeftToRight)
            self.board_container.setVisible(True)
            self.eval_bar.setVisible(True)
            self.ctrl_row_widget.setVisible(True)
            self.board_widget.setMaximumSize(16777215, 16777215)
            self.board_widget.setMinimumSize(220, 220)
            self.move_list_widget.setVisible(True)

            self.main_layout.setContentsMargins(16, 12, 16, 12)
            self.main_layout.setSpacing(16)
            self.analysis_layout.setContentsMargins(14, 14, 14, 14)

    def toggle_mini_board(self) -> bool:
        """Toggles mini-board visibility when in compact mode."""
        self._show_mini_board = not getattr(self, "_show_mini_board", True)
        if getattr(self, "_is_compact", False):
            self.set_compact_mode(True, show_mini_board=self._show_mini_board)
        return self._show_mini_board

    def _connect_signals(self) -> None:
        self.game_state_mgr.add_listener(self._on_state_updated)
        self.game_state_mgr.orientation_changed.connect(self._on_orientation_changed)
        self.board_widget.set_on_move_made(self._on_board_move_made)

        # Wire card hover highlighting and click to explore
        self.card_1.card_hovered.connect(self._on_candidate_hovered)
        self.card_2.card_hovered.connect(self._on_candidate_hovered)
        self.card_3.card_hovered.connect(self._on_candidate_hovered)

        self.card_1.candidate_clicked.connect(self._on_candidate_clicked)
        self.card_2.candidate_clicked.connect(self._on_candidate_clicked)
        self.card_3.candidate_clicked.connect(self._on_candidate_clicked)

        self.move_list_widget.set_callbacks(
            on_jump=self.game_state_mgr.board_state.go_to_ply,
            on_back=self.game_state_mgr.board_state.step_backward,
            on_forward=self.game_state_mgr.board_state.step_forward,
            on_start=self.game_state_mgr.board_state.go_to_start,
            on_end=self.game_state_mgr.board_state.go_to_end
        )

        self._on_state_updated()

    def _toggle_arrows(self) -> None:
        shown = self.board_widget.toggle_arrows()
        self.btn_toggle_arrows.setText("Arrows ✓" if shown else "Arrows ✕")

    def _on_candidate_hovered(self, rank: int) -> None:
        self.board_widget.set_highlighted_candidate_rank(rank if rank > 0 else None)

    def _on_candidate_clicked(self, cand: CandidateMove) -> None:
        if cand and cand.move:
            self.game_state_mgr.user_played_analysis_move(cand.move)

    def _on_flip_board(self) -> None:
        self.game_state_mgr.toggle_orientation()

    def _on_orientation_changed(self, white_bottom: bool) -> None:
        self.board_widget.set_white_at_bottom(white_bottom)
        self.eval_bar.set_white_at_bottom(white_bottom)
        self._on_state_updated()

    def _on_reset_board(self) -> None:
        self.game_state_mgr.board_state.reset()
        if hasattr(self.game_state_mgr, "observer") and self.game_state_mgr.observer:
            self.game_state_mgr.observer.set_known_board(chess.Board())

    def _open_position_dialog(self) -> None:
        from ui.widgets.position_dialog import PositionSetupDialog
        dlg = PositionSetupDialog(self.game_state_mgr, self)
        dlg.exec()

    def _on_board_move_made(self, move: chess.Move) -> None:
        self.game_state_mgr.user_played_analysis_move(move)

    def _on_return_to_live(self) -> None:
        self.game_state_mgr.return_to_live_game()

    def _on_state_updated(self) -> None:
        board = self.game_state_mgr.current_board
        last_move = self.game_state_mgr.last_confirmed_move

        if last_move and last_move != self._prev_rendered_move:
            self.board_widget.flash_move(last_move.from_square, last_move.to_square)
            self._prev_rendered_move = last_move

        self.board_widget.set_board(board, last_move)
        self.move_list_widget.set_moves(
            self.game_state_mgr.board_state.get_move_list_san(),
            self.game_state_mgr.board_state.current_ply
        )

        # Variation exploration state
        self.variation_banner.setVisible(self.game_state_mgr.is_exploring_variation)

        # Fair play check: if live observation mode, hide candidates
        if not self.mode_mgr.engine_recommendations_allowed():
            self.lbl_coach.setText("LIVE OBSERVATION")
            self.coach_card.setStyleSheet("""
                QFrame {
                    background-color: rgba(0, 240, 255, 0.08);
                    border: 1px solid rgba(0, 240, 255, 0.35);
                    border-left: 4px solid #00F0FF;
                    border-radius: 12px;
                    padding: 8px 12px;
                }
            """)
            self.coach_text.setText("Engine move recommendations are disabled during Live Observation to preserve Fair-Play compliance.")
            self.card_1.setVisible(False)
            self.card_2.setVisible(False)
            self.card_3.setVisible(False)
            self.board_widget.set_candidate_moves([])
            return

        candidates = self.game_state_mgr.candidates
        summary = self.game_state_mgr.summary

        turn = board.turn
        player_color = getattr(self.game_state_mgr, "player_color", chess.WHITE)
        is_player_turn = (turn == player_color)

        if board.is_checkmate():
            winner = "Black" if turn == chess.WHITE else "White"
            self.lbl_coach.setText(f"CHECKMATE — {winner.upper()} WINS!")
            self.lbl_coach.setStyleSheet("font-size: 11px; font-weight: 800; color: #FF2A85; letter-spacing: 0.8px;")
            self.coach_card.setStyleSheet("""
                QFrame {
                    background-color: rgba(255, 42, 133, 0.14);
                    border: 1px solid rgba(255, 42, 133, 0.40);
                    border-left: 4px solid #FF2A85;
                    border-radius: 12px;
                    padding: 8px 12px;
                }
            """)
            self.coach_text.setText(f"Game over by checkmate ({winner} wins).")
            self.card_1.setVisible(False)
            self.card_2.setVisible(False)
            self.card_3.setVisible(False)
            self.board_widget.set_candidate_moves([])
            return
        elif board.is_stalemate() or board.is_insufficient_material() or board.can_claim_draw():
            self.lbl_coach.setText("DRAW / STALEMATE")
            self.lbl_coach.setStyleSheet("font-size: 11px; font-weight: 800; color: #94A3B8; letter-spacing: 0.8px;")
            self.coach_card.setStyleSheet("""
                QFrame {
                    background-color: rgba(255, 255, 255, 0.04);
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-left: 4px solid #94A3B8;
                    border-radius: 12px;
                    padding: 8px 12px;
                }
            """)
            self.coach_text.setText("Game drawn.")
            self.card_1.setVisible(False)
            self.card_2.setVisible(False)
            self.card_3.setVisible(False)
            self.board_widget.set_candidate_moves([])
            return

        if turn == chess.WHITE:
            turn_name = "WHITE TO MOVE"
            badge_color = "#00F0FF"  # Electric Cyan
            bg_color = "rgba(0, 240, 255, 0.08)"
            border_color = "rgba(0, 240, 255, 0.35)"
        else:
            turn_name = "BLACK TO MOVE"
            badge_color = "#A855F7"  # Neon Violet
            bg_color = "rgba(168, 85, 247, 0.08)"
            border_color = "rgba(168, 85, 247, 0.35)"

        check_str = " (CHECK!)" if board.is_check() else ""

        if candidates:
            best = candidates[0]
            if is_player_turn:
                badge_title = f"● YOUR TURN [{turn_name}]{check_str}  ➔  PLAY: {best.san} ({best.eval_str})"
            else:
                badge_title = f"● OPPONENT'S TURN [{turn_name}]{check_str}  ➔  EXPECT: {best.san} ({best.eval_str})"
        else:
            if is_player_turn:
                badge_title = f"● YOUR TURN [{turn_name}]{check_str}  ➔  Calculating best move..."
            else:
                badge_title = f"● OPPONENT'S TURN [{turn_name}]{check_str}  ➔  Waiting for move..."

        self.lbl_coach.setText(badge_title)
        self.lbl_coach.setStyleSheet(f"font-size: 11px; font-weight: 800; color: {badge_color}; letter-spacing: 0.8px;")
        self.coach_card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-left: 4px solid {badge_color};
                border-radius: 12px;
                padding: 8px 12px;
            }}
        """)

        if summary and summary.coach_takeaway:
            self.coach_text.setText(summary.coach_takeaway)
        elif candidates:
            best = candidates[0]
            pv_preview = " ".join(best.pv_san[:5]) if best.pv_san else best.san
            self.coach_text.setText(f"Engine line: {pv_preview}")
        else:
            self.coach_text.setText("Analyzing position...")

        if candidates:
            best = candidates[0]
            self.eval_bar.set_evaluation(best.eval_str, best.score_cp, best.mate_in)
            self.card_1.set_candidate(best)
            self.card_1.setVisible(True)

            if len(candidates) >= 2:
                self.card_2.set_candidate(candidates[1])
                self.card_2.setVisible(True)
            else:
                self.card_2.setVisible(False)

            if len(candidates) >= 3:
                self.card_3.set_candidate(candidates[2])
                self.card_3.setVisible(True)
            else:
                self.card_3.setVisible(False)

            self.board_widget.set_candidate_moves(candidates[:3])
        else:
            self.card_1.setVisible(False)
            self.card_2.setVisible(False)
            self.card_3.setVisible(False)
            self.board_widget.set_candidate_moves([])
