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
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 12px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header: Title + Category Pill + Confidence Pill
        header = QHBoxLayout()
        header.setSpacing(6)

        title_lbl = QLabel(self.insight.title)
        title_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #F8FAFC;")

        cat_lbl = QLabel(self.insight.category)
        cat_lbl.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.08);
            color: #94A3B8;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 6px;
            padding: 2px 7px;
            font-size: 10px;
            font-weight: 600;
        """)

        conf_lbl = QLabel(self.insight.confidence.value)
        if self.insight.confidence == ConfidenceLevel.CONFIRMED:
            conf_lbl.setStyleSheet("background-color: rgba(0, 255, 157, 0.16); color: #00FF9D; border: 1px solid rgba(0, 255, 157, 0.35); border-radius: 6px; padding: 2px 7px; font-size: 10px; font-weight: 700;")
        elif self.insight.confidence == ConfidenceLevel.EMERGING:
            conf_lbl.setStyleSheet("background-color: rgba(255, 184, 0, 0.16); color: #FFB800; border: 1px solid rgba(255, 184, 0, 0.35); border-radius: 6px; padding: 2px 7px; font-size: 10px; font-weight: 700;")
        else:
            conf_lbl.setStyleSheet("background-color: rgba(148, 163, 184, 0.12); color: #94A3B8; border: 1px solid rgba(148, 163, 184, 0.25); border-radius: 6px; padding: 2px 7px; font-size: 10px; font-weight: 700;")

        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(cat_lbl)
        header.addWidget(conf_lbl)
        layout.addLayout(header)

        # Body text
        text_lbl = QLabel(self.insight.text)
        text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet("color: #CBD5E1; font-size: 12px; line-height: 1.4;")
        layout.addWidget(text_lbl)

        # Evidence footer
        footer_lbl = QLabel(f"Evidence: {self.insight.evidence_summary} (sample size: {self.insight.sample_size})")
        footer_lbl.setStyleSheet("color: #64748B; font-size: 11px;")
        layout.addWidget(footer_lbl)
