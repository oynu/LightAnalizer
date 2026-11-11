"""
Candidate move card widget.
Displays move notation, evaluation, delta, natural language explanation,
and expandable principal variation (PV).
"""
from __future__ import annotations
from typing import Optional, Callable
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget
)
from PySide6.QtCore import Qt, Signal
from core.types import CandidateMove

class CandidateCard(QFrame):
    """
    Renders an individual candidate move with badge, eval, delta, and PV expander.
    """
    card_hovered = Signal(int)           # Emits rank or -1
    candidate_clicked = Signal(object)   # Emits CandidateMove

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._candidate: Optional[CandidateMove] = None
        self._is_expanded = False
        self._on_pv_click: Optional[Callable[[CandidateMove], None]] = None
        self.setCursor(Qt.PointingHandCursor)
        self._setup_ui()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if self._candidate:
            self.card_hovered.emit(self._candidate.rank)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.card_hovered.emit(-1)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton and self._candidate:
            self.candidate_clicked.emit(self._candidate)

    def _setup_ui(self) -> None:
        self.setObjectName("CandidateCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame#CandidateCard {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 14px;
            }
        """)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(8)

        # Top row: Rank badge, Move SAN, Eval badge, Delta badge
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.rank_badge = QLabel("#1")
        self.rank_badge.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.08);
            color: #94A3B8;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 8px;
            padding: 2px 7px;
            font-size: 11px;
            font-weight: 700;
            font-family: 'JetBrains Mono', 'Consolas', monospace;
        """)

        self.san_label = QLabel("--")
        self.san_label.setStyleSheet("""
            font-size: 17px;
            font-weight: 800;
            color: #F8FAFC;
            font-family: 'JetBrains Mono', 'Consolas', monospace;
        """)

        self.eval_badge = QLabel("0.0")
        self.eval_badge.setStyleSheet("""
            background-color: rgba(0, 240, 255, 0.14);
            color: #00F0FF;
            border: 1px solid rgba(0, 240, 255, 0.32);
            border-radius: 8px;
            padding: 3px 9px;
            font-size: 12px;
            font-weight: 700;
            font-family: 'JetBrains Mono', 'Consolas', monospace;
        """)

        self.delta_label = QLabel("+0.00")
        self.delta_label.setStyleSheet("""
            color: #64748B;
            font-size: 11px;
            font-weight: 600;
            font-family: 'JetBrains Mono', 'Consolas', monospace;
        """)

        top_row.addWidget(self.rank_badge)
        top_row.addWidget(self.san_label)
        top_row.addStretch()
        top_row.addWidget(self.delta_label)
        top_row.addWidget(self.eval_badge)
        self._layout.addLayout(top_row)

        # Middle: Natural language explanation
        self.explanation_label = QLabel("Awaiting engine calculation...")
        self.explanation_label.setWordWrap(True)
        self.explanation_label.setStyleSheet("color: #CBD5E1; font-size: 12px; line-height: 1.4;")
        self._layout.addWidget(self.explanation_label)

        # Strategic idea & response row
        self.idea_label = QLabel("")
        self.idea_label.setWordWrap(True)
        self.idea_label.setStyleSheet("color: #94A3B8; font-size: 11px; font-style: italic;")
        self._layout.addWidget(self.idea_label)

        # Bottom row: Expand PV button & PV container
        self.pv_btn = QPushButton("Show Variation (PV) ▼")
        self.pv_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #00F0FF;
                font-size: 11px;
                font-weight: 600;
                text-align: left;
                padding: 2px 0px;
            }
            QPushButton:hover {
                color: #A855F7;
            }
        """)
        self.pv_btn.clicked.connect(self._toggle_pv)
        self._layout.addWidget(self.pv_btn)

        self.pv_text = QLabel("")
        self.pv_text.setWordWrap(True)
        self.pv_text.setStyleSheet("""
            background-color: rgba(10, 14, 24, 0.70);
            color: #00F0FF;
            border: 1px solid rgba(255, 255, 255, 0.08);
            padding: 6px 10px;
            border-radius: 8px;
            font-family: 'JetBrains Mono', 'Consolas', monospace;
            font-size: 11px;
        """)
        self.pv_text.setVisible(False)
        self._layout.addWidget(self.pv_text)

    def set_candidate(self, cand: CandidateMove) -> None:
        self._candidate = cand
        self.san_label.setText(cand.san)
        self.eval_badge.setText(cand.eval_str)

        # Style based on rank with Liquid Glass + Neon styling
        if cand.rank == 1:
            self.setStyleSheet("""
                QFrame#CandidateCard {
                    background-color: rgba(0, 240, 255, 0.06);
                    border: 1px solid rgba(0, 240, 255, 0.50);
                    border-radius: 14px;
                }
            """)
            self.rank_badge.setText("BEST")
            self.rank_badge.setStyleSheet("""
                background-color: rgba(0, 255, 157, 0.16);
                color: #00FF9D;
                border: 1px solid rgba(0, 255, 157, 0.35);
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 800;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
            """)
            self.eval_badge.setStyleSheet("""
                background-color: rgba(0, 240, 255, 0.18);
                color: #00F0FF;
                border: 1px solid rgba(0, 240, 255, 0.45);
                border-radius: 8px;
                padding: 3px 9px;
                font-size: 12px;
                font-weight: 800;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
            """)
            self.delta_label.setText("Top Choice")
            self.delta_label.setStyleSheet("color: #00FF9D; font-size: 11px; font-weight: 700; font-family: 'JetBrains Mono', 'Consolas', monospace;")
        elif cand.rank == 2:
            self.setStyleSheet("""
                QFrame#CandidateCard {
                    background-color: rgba(168, 85, 247, 0.05);
                    border: 1px solid rgba(168, 85, 247, 0.35);
                    border-radius: 14px;
                }
            """)
            self.rank_badge.setText("ALT")
            self.rank_badge.setStyleSheet("""
                background-color: rgba(168, 85, 247, 0.18);
                color: #C084FC;
                border: 1px solid rgba(168, 85, 247, 0.35);
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 800;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
            """)
            self.eval_badge.setStyleSheet("""
                background-color: rgba(168, 85, 247, 0.15);
                color: #D8B4FE;
                border: 1px solid rgba(168, 85, 247, 0.30);
                border-radius: 8px;
                padding: 3px 9px;
                font-size: 12px;
                font-weight: 700;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
            """)
            self.delta_label.setText(f"{cand.eval_diff:+.2f} cp" if cand.eval_diff is not None else "")
            self.delta_label.setStyleSheet("color: #C084FC; font-size: 11px; font-weight: 600; font-family: 'JetBrains Mono', 'Consolas', monospace;")
        else:
            self.setStyleSheet("""
                QFrame#CandidateCard {
                    background-color: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 14px;
                }
            """)
            self.rank_badge.setText("#3")
            self.rank_badge.setStyleSheet("""
                background-color: rgba(255, 184, 0, 0.14);
                color: #FFB800;
                border: 1px solid rgba(255, 184, 0, 0.30);
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 800;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
            """)
            self.eval_badge.setStyleSheet("""
                background-color: rgba(255, 255, 255, 0.07);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 3px 9px;
                font-size: 12px;
                font-weight: 700;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
            """)
            self.delta_label.setText(f"{cand.eval_diff:+.2f} cp" if cand.eval_diff is not None else "")
            self.delta_label.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 600; font-family: 'JetBrains Mono', 'Consolas', monospace;")

        self.explanation_label.setText(cand.short_explanation or "Engine evaluated candidate continuation.")
        
        details = []
        if cand.strategic_idea:
            details.append(f"Idea: {cand.strategic_idea}")
        if cand.risks_and_responses:
            details.append(f"Response: {cand.risks_and_responses}")
        self.idea_label.setText(" | ".join(details) if details else "")

        # Format PV string
        if cand.pv_san:
            self.pv_text.setText(" ".join(cand.pv_san[:8]))
            self.pv_btn.setVisible(True)
        else:
            self.pv_btn.setVisible(False)

    def _toggle_pv(self) -> None:
        self._is_expanded = not self._is_expanded
        self.pv_text.setVisible(self._is_expanded)
        self.pv_btn.setText("Hide Variation ▲" if self._is_expanded else "Show Variation (PV) ▼")
