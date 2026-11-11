"""
Board state and game history management.
"""
from __future__ import annotations
from typing import List, Optional, Callable
import io
import chess
import chess.pgn

class BoardState:
    """
    Manages current chess position, full move history, navigation, and rules validation.
    """
    def __init__(self, fen: Optional[str] = None):
        self.game = chess.pgn.Game()
        self.headers = self.game.headers
        self.headers["Event"] = "LightAnalizer Analysis"
        self.headers["Site"] = "Local"
        self.headers["White"] = "White"
        self.headers["Black"] = "Black"
        self.headers["Result"] = "*"

        self._board = chess.Board(fen) if fen else chess.Board()
        self._history_nodes: List[chess.pgn.GameNode] = [self.game]
        self._current_index: int = 0
        self._listeners: List[Callable[[], None]] = []

        if fen and fen != chess.STARTING_FEN:
            self.game.setup(self._board)

    @property
    def board(self) -> chess.Board:
        """Returns the active board at the current navigation ply."""
        return self._board

    @property
    def current_ply(self) -> int:
        return self._current_index

    @property
    def total_plies(self) -> int:
        return len(self._history_nodes) - 1

    def add_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        for cb in self._listeners:
            try:
                cb()
            except Exception as e:
                print(f"[BoardState] Listener error: {e}")

    def reset(self, fen: Optional[str] = None) -> None:
        self.game = chess.pgn.Game()
        self.headers = self.game.headers
        self.headers["Event"] = "LightAnalizer Analysis"
        self.headers["Result"] = "*"
        self._board = chess.Board(fen) if fen else chess.Board()
        if fen and fen != chess.STARTING_FEN:
            self.game.setup(self._board)
        self._history_nodes = [self.game]
        self._current_index = 0
        self._notify()

    def push_move(self, move: chess.Move) -> bool:
        """
        Executes a legal move from the current position.
        If moving from an earlier ply, branches or replaces subsequent moves.
        """
        if move not in self._board.legal_moves:
            return False

        # If we are in the middle of history, truncate forward history or extend
        current_node = self._history_nodes[self._current_index]
        new_node = current_node.add_variation(move)
        
        # Advance board
        self._board.push(move)
        self._history_nodes = self._history_nodes[: self._current_index + 1] + [new_node]
        self._current_index += 1
        self._notify()
        return True

    def push_san(self, san: str) -> bool:
        try:
            move = self._board.parse_san(san)
            return self.push_move(move)
        except (chess.IllegalMoveError, chess.InvalidMoveError, ValueError):
            return False

    def push_uci(self, uci: str) -> bool:
        try:
            move = chess.Move.from_uci(uci)
            return self.push_move(move)
        except (ValueError, chess.IllegalMoveError):
            return False

    def step_backward(self) -> bool:
        if self._current_index > 0:
            self._current_index -= 1
            self._reconstruct_board_at_current_index()
            self._notify()
            return True
        return False

    def step_forward(self) -> bool:
        if self._current_index < len(self._history_nodes) - 1:
            self._current_index += 1
            self._reconstruct_board_at_current_index()
            self._notify()
            return True
        return False

    def go_to_start(self) -> None:
        if self._current_index != 0:
            self._current_index = 0
            self._reconstruct_board_at_current_index()
            self._notify()

    def go_to_end(self) -> None:
        last = len(self._history_nodes) - 1
        if self._current_index != last:
            self._current_index = last
            self._reconstruct_board_at_current_index()
            self._notify()

    def go_to_ply(self, ply: int) -> bool:
        if 0 <= ply < len(self._history_nodes):
            if self._current_index != ply:
                self._current_index = ply
                self._reconstruct_board_at_current_index()
                self._notify()
            return True
        return False

    def get_history_boards(self) -> List[chess.Board]:
        """Returns boards for each ply in the current game history."""
        boards = []
        b = self.game.board()
        boards.append(b.copy())
        for idx in range(1, len(self._history_nodes)):
            target_node = self._history_nodes[idx]
            if target_node.move:
                b.push(target_node.move)
                boards.append(b.copy())
        return boards

    def _reconstruct_board_at_current_index(self) -> None:
        # Reconstruct board from root up to current index
        node = self.game
        self._board = node.board()
        for idx in range(1, self._current_index + 1):
            target_node = self._history_nodes[idx]
            if target_node.move:
                self._board.push(target_node.move)

    def load_pgn(self, pgn_str: str) -> bool:
        try:
            game = chess.pgn.read_game(io.StringIO(pgn_str))
            if game is None:
                return False
            self.game = game
            self.headers = game.headers
            self._history_nodes = [game]
            node = game
            while node.variations:
                node = node.variations[0]
                self._history_nodes.append(node)
            self._current_index = len(self._history_nodes) - 1
            self._reconstruct_board_at_current_index()
            self._notify()
            return True
        except Exception as e:
            print(f"[BoardState] Failed to load PGN: {e}")
            return False

    def export_pgn(self) -> str:
        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        return self.game.accept(exporter)

    def export_fen(self) -> str:
        return self._board.fen()

    def load_fen(self, fen_str: str) -> bool:
        try:
            board = chess.Board(fen_str)
            if not board.is_valid():
                return False
            self.reset(fen_str)
            return True
        except ValueError:
            return False

    def get_move_list_san(self) -> List[str]:
        moves = []
        for i in range(1, len(self._history_nodes)):
            node = self._history_nodes[i]
            if node.move:
                parent_board = self._history_nodes[i - 1].board()
                moves.append(parent_board.san(node.move))
        return moves

    def is_game_over(self) -> bool:
        return self._board.is_game_over()

    def game_result(self) -> str:
        if self._board.is_checkmate():
            return "0-1" if self._board.turn == chess.WHITE else "1-0"
        elif self._board.is_stalemate() or self._board.is_insufficient_material() or self._board.is_fivefold_repetition():
            return "1/2-1/2"
        return "*"
