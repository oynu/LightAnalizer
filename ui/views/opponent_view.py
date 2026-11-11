"""
Opponent intelligence browser and management view.
Tracks historical opening repertoires, tactical vulnerabilities, and persistent games.
"""
from __future__ import annotations
import io
from typing import Optional, List
import chess.pgn
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QLineEdit, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QInputDialog, QFrame, QScrollArea
)
from PySide6.QtCore import Qt
from core.opponent.models import Opponent, GameRecord, MoveObservation
from core.opponent.repository import OpponentRepository
from core.opponent.profiling import OpponentProfiler
from core.board_state import BoardState
from ui.widgets.insight_card import InsightCard

class OpponentView(QWidget):
    """
    Renders the persistent opponent intelligence database, repertoire, and tactical tendencies.
    """
    def __init__(self, repo: OpponentRepository, board_state: BoardState, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.repo = repo
        self.board_state = board_state
        self.profiler = OpponentProfiler(repo)
        self._selected_opp_id: Optional[int] = None

        self._setup_ui()
        self._load_opponents_list()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal)

        # ---------------- LEFT PANEL: OPPONENT LIST ----------------
        left_panel = QFrame()
        left_panel.setFixedWidth(240)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        lbl_list = QLabel("Opponent Profiles")
        lbl_list.setStyleSheet("font-size: 14px; font-weight: 800; color: #F8FAFC;")
        left_layout.addWidget(lbl_list)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search opponents...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.05);
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 7px 10px;
            }
            QLineEdit:focus {
                border-color: #00F0FF;
            }
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        left_layout.addWidget(self.search_input)

        self.opp_list_widget = QListWidget()
        self.opp_list_widget.setStyleSheet("""
            QListWidget {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                color: #F8FAFC;
                padding: 4px;
            }
            QListWidget::item {
                border-radius: 6px;
                padding: 6px 8px;
            }
            QListWidget::item:selected {
                background-color: rgba(0, 240, 255, 0.20);
                color: #00F0FF;
            }
        """)
        self.opp_list_widget.itemClicked.connect(self._on_opponent_selected)
        left_layout.addWidget(self.opp_list_widget, stretch=1)

        btn_new_opp = QPushButton("+ New Opponent")
        btn_new_opp.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 240, 255, 0.12);
                color: #00F0FF;
                font-weight: 700;
                padding: 8px;
                border: 1px solid rgba(0, 240, 255, 0.35);
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 0.22);
            }
        """)
        btn_new_opp.clicked.connect(self._create_new_opponent)
        left_layout.addWidget(btn_new_opp)

        splitter.addWidget(left_panel)

        # ---------------- RIGHT PANEL: PROFILE DETAILS ----------------
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 0, 0, 0)
        right_layout.setSpacing(12)

        # Header Info Row
        header_row = QHBoxLayout()
        self.lbl_profile_name = QLabel("Select an opponent")
        self.lbl_profile_name.setStyleSheet("font-size: 18px; font-weight: 800; color: #F8FAFC;")
        header_row.addWidget(self.lbl_profile_name)
        header_row.addStretch()

        self.btn_import_pgn = QPushButton("Import PGN Game")
        self.btn_import_pgn.setStyleSheet("""
            QPushButton {
                background-color: #00F0FF;
                color: #080B12;
                font-weight: 800;
                padding: 7px 16px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background-color: #38BDF8;
            }
        """)
        self.btn_import_pgn.clicked.connect(self._import_pgn_for_opponent)
        header_row.addWidget(self.btn_import_pgn)

        self.btn_delete_opp = QPushButton("Delete Profile")
        self.btn_delete_opp.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 42, 133, 0.12);
                color: #FF2A85;
                border: 1px solid rgba(255, 42, 133, 0.35);
                padding: 7px 14px;
                border-radius: 8px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: rgba(255, 42, 133, 0.22);
            }
        """)
        self.btn_delete_opp.clicked.connect(self._delete_opponent)
        header_row.addWidget(self.btn_delete_opp)

        right_layout.addLayout(header_row)

        # Profile Insights Scroll Area
        lbl_ins = QLabel("EMPIRICAL TENDENCIES & INSIGHTS")
        lbl_ins.setStyleSheet("font-size: 11px; font-weight: 700; color: #9CA3AF;")
        right_layout.addWidget(lbl_ins)

        self.insights_scroll = QScrollArea()
        self.insights_scroll.setWidgetResizable(True)
        self.insights_scroll.setFixedHeight(180)
        self.insights_container = QWidget()
        self.insights_layout = QVBoxLayout(self.insights_container)
        self.insights_layout.setContentsMargins(0, 0, 0, 0)
        self.insights_layout.setSpacing(8)
        self.insights_layout.addStretch()
        self.insights_scroll.setWidget(self.insights_container)
        right_layout.addWidget(self.insights_scroll)

        # Recorded Games Table
        lbl_games = QLabel("RECORDED HISTORICAL GAMES")
        lbl_games.setStyleSheet("font-size: 11px; font-weight: 700; color: #9CA3AF;")
        right_layout.addWidget(lbl_games)

        self.games_table = QTableWidget(0, 6)
        self.games_table.setHorizontalHeaderLabels(["ID", "Date", "White", "Black", "Result", "ECO"])
        self.games_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.games_table.verticalHeader().setVisible(False)
        self.games_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.games_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.games_table.cellDoubleClicked.connect(self._on_game_double_clicked)
        right_layout.addWidget(self.games_table, stretch=1)

        splitter.addWidget(right_panel)
        splitter.setSizes([240, 700])
        main_layout.addWidget(splitter)

    def _load_opponents_list(self) -> None:
        self.opp_list_widget.clear()
        query = self.search_input.text().strip()
        opponents = self.repo.list_opponents(search=query)
        for opp in opponents:
            item = QListWidgetItem(f"{opp.name} ({opp.games_count} games)")
            item.setData(Qt.UserRole, opp.id)
            self.opp_list_widget.addItem(item)

        if opponents and self._selected_opp_id is None:
            self._select_opponent_by_id(opponents[0].id)

    def _on_search_changed(self, text: str) -> None:
        self._load_opponents_list()

    def _on_opponent_selected(self, item: QListWidgetItem) -> None:
        opp_id = item.data(Qt.UserRole)
        self._select_opponent_by_id(opp_id)

    def _select_opponent_by_id(self, opp_id: int) -> None:
        self._selected_opp_id = opp_id
        opp = self.repo.get_opponent_by_id(opp_id)
        if not opp:
            return

        self.lbl_profile_name.setText(f"{opp.name} ({opp.games_count} recorded games)")

        # Render insights
        insights = self.profiler.generate_profile_insights(opp_id)
        while self.insights_layout.count() > 1:
            child = self.insights_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for ins in insights:
            card = InsightCard(ins)
            self.insights_layout.insertWidget(self.insights_layout.count() - 1, card)

        # Render games table
        games = self.repo.get_games_for_opponent(opp_id)
        self.games_table.setRowCount(len(games))
        for idx, g in enumerate(games):
            self.games_table.setItem(idx, 0, QTableWidgetItem(str(g.id)))
            self.games_table.setItem(idx, 1, QTableWidgetItem(g.date))
            self.games_table.setItem(idx, 2, QTableWidgetItem(g.white))
            self.games_table.setItem(idx, 3, QTableWidgetItem(g.black))
            self.games_table.setItem(idx, 4, QTableWidgetItem(g.result))
            self.games_table.setItem(idx, 5, QTableWidgetItem(f"{g.eco} - {g.opening_name}"))

    def _create_new_opponent(self) -> None:
        name, ok = QInputDialog.getText(self, "Create Opponent", "Enter opponent name:")
        if ok and name.strip():
            opp = self.repo.get_or_create_opponent(name.strip())
            self._load_opponents_list()
            self._select_opponent_by_id(opp.id)

    def _delete_opponent(self) -> None:
        if self._selected_opp_id:
            reply = QMessageBox.question(
                self, "Delete Profile",
                "Are you sure you want to permanently delete this opponent profile and associated games?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.repo.delete_opponent(self._selected_opp_id)
                self._selected_opp_id = None
                self._load_opponents_list()

    def _import_pgn_for_opponent(self) -> None:
        if not self._selected_opp_id:
            QMessageBox.information(self, "Select Opponent", "Please select an opponent profile first.")
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Import PGN", "", "PGN Files (*.pgn);;All Files (*)")
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                pgn_text = f.read()

            game = chess.pgn.read_game(io.StringIO(pgn_text))
            if not game:
                QMessageBox.warning(self, "Invalid PGN", "Could not parse chess game from file.")
                return

            # Extract game records and move observations
            white = game.headers.get("White", "Unknown")
            black = game.headers.get("Black", "Unknown")
            result = game.headers.get("Result", "*")
            date = game.headers.get("Date", "")
            eco = game.headers.get("ECO", "")
            opening = game.headers.get("Opening", "")

            game_rec = GameRecord(
                opponent_id=self._selected_opp_id,
                white=white,
                black=black,
                result=result,
                date=date,
                eco=eco,
                opening_name=opening,
                pgn=pgn_text
            )

            # Extract moves
            b = game.board()
            moves_obs = []
            ply = 1
            node = game
            while node.variations:
                next_node = node.variations[0]
                m = next_node.move
                san = b.san(m)
                fen_before = b.fen()
                moves_obs.append(MoveObservation(
                    move_ply=ply,
                    fen_before=fen_before,
                    move_san=san
                ))
                b.push(m)
                node = next_node
                ply += 1

            self.repo.record_game(game_rec, moves_obs)
            self._load_opponents_list()
            self._select_opponent_by_id(self._selected_opp_id)
            QMessageBox.information(self, "Game Imported", f"Successfully recorded game with {len(moves_obs)} moves.")

        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import PGN: {e}")

    def _on_game_double_clicked(self, row: int, col: int) -> None:
        if not self._selected_opp_id:
            return
        games = self.repo.get_games_for_opponent(self._selected_opp_id)
        if row < len(games):
            g = games[row]
            if self.board_state.load_pgn(g.pgn):
                QMessageBox.information(self, "Loaded", f"Game between {g.white} and {g.black} loaded to board.")
