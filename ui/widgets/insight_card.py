"""
Opponent insight card widget displaying empirical patterns and confidence tags.
"""
from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget
from core.types import OpponentInsight, ConfidenceLevel

class InsightCard(QFrame):
    """
    Renders an empirical opponent insight with strict confidence rating and evidence details.
    """
    def __init__(self, insight: OpponentInsight, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.insight = insight
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet("""
            QFrame {
                background-color: #18191E;
                border: 1px solid #23252B;
                border-radius: 8px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Header: Title + Category Pill + Confidence Pill
        header = QHBoxLayout()
        header.setSpacing(6)

        title_lbl = QLabel(self.insight.title)
        title_lbl.setStyleSheet("font-weight: 600; font-size: 13px; color: #FFFFFF;")

        cat_lbl = QLabel(self.insight.category)
        cat_lbl.setStyleSheet("""
            background-color: #1F2937;
            color: #9CA3AF;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 10px;
            font-weight: 600;
        """)

        conf_lbl = QLabel(self.insight.confidence.value)
        if self.insight.confidence == ConfidenceLevel.CONFIRMED:
            conf_lbl.setStyleSheet("background-color: #064E3B; color: #34D399; border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: 600;")
        elif self.insight.confidence == ConfidenceLevel.EMERGING:
            conf_lbl.setStyleSheet("background-color: #451A03; color: #FBBF24; border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: 600;")
        else:
            conf_lbl.setStyleSheet("background-color: #27272A; color: #A1A1AA; border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: 600;")

        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(cat_lbl)
        header.addWidget(conf_lbl)
        layout.addLayout(header)

        # Body text
        text_lbl = QLabel(self.insight.text)
        text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet("color: #D1D5DB; font-size: 12px; line-height: 1.4;")
        layout.addWidget(text_lbl)

        # Evidence footer
        footer_lbl = QLabel(f"Evidence: {self.insight.evidence_summary} (sample size: {self.insight.sample_size})")
        footer_lbl.setStyleSheet("color: #6B7280; font-size: 11px;")
        layout.addWidget(footer_lbl)
