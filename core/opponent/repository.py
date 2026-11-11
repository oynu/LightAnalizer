"""
SQLite persistence repository for opponents, games, and move observations.
"""
from __future__ import annotations
import sqlite3
import os
import threading
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from core.opponent.models import Opponent, GameRecord, MoveObservation

class OpponentRepository:
    """
    Manages local SQLite database for persistent player profiling and historical games.
    """
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_dir = os.path.join(base_dir, "data")
            os.makedirs(db_dir, exist_ok=True)
            old_db = os.path.join(db_dir, "grandmaster.db")
            new_db = os.path.join(db_dir, "lightanalizer.db")
            if os.path.exists(old_db) and not os.path.exists(new_db):
                try:
                    import shutil
                    shutil.copy2(old_db, new_db)
                except Exception:
                    pass
            self.db_path = new_db if (os.path.exists(new_db) or not os.path.exists(old_db)) else old_db
        else:
            self.db_path = db_path

        self._lock = threading.Lock()
        if self.db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
        else:
            self._mem_conn = None

        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        if self._mem_conn is None:
            conn.close()

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                # Opponents table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS opponents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    rating INTEGER,
                    games_count INTEGER DEFAULT 0,
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """)

                # Games table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opponent_id INTEGER NOT NULL,
                    white TEXT NOT NULL,
                    black TEXT NOT NULL,
                    result TEXT NOT NULL,
                    date TEXT,
                    time_control TEXT,
                    eco TEXT,
                    opening_name TEXT,
                    pgn TEXT NOT NULL,
                    FOREIGN KEY (opponent_id) REFERENCES opponents(id) ON DELETE CASCADE
                )
                """)

                # Move observations table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS move_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    move_ply INTEGER NOT NULL,
                    fen_before TEXT NOT NULL,
                    move_san TEXT NOT NULL,
                    eval_cp INTEGER,
                    eval_loss INTEGER,
                    clock_remaining REAL,
                    is_inaccuracy INTEGER DEFAULT 0,
                    is_mistake INTEGER DEFAULT 0,
                    is_blunder INTEGER DEFAULT 0,
                    blunder_category TEXT DEFAULT '',
                    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
                )
                """)

                # Indices for fast lookups
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_opponent ON games(opponent_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_moves_fen ON move_observations(fen_before)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_moves_game ON move_observations(game_id)")

                conn.commit()
            finally:
                self._close_conn(conn)

    def get_or_create_opponent(self, name: str, rating: Optional[int] = None) -> Opponent:
        name = name.strip() or "Anonymous"
        now = datetime.now().isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM opponents WHERE name = ?", (name,))
                row = cursor.fetchone()
                if row:
                    return Opponent(
                        id=row["id"],
                        name=row["name"],
                        rating=row["rating"],
                        games_count=row["games_count"],
                        notes=row["notes"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"]
                    )
                cursor.execute(
                    "INSERT INTO opponents (name, rating, games_count, notes, created_at, updated_at) VALUES (?, ?, 0, '', ?, ?)",
                    (name, rating, now, now)
                )
                conn.commit()
                opp_id = cursor.lastrowid
                return Opponent(id=opp_id, name=name, rating=rating, games_count=0, notes="", created_at=now, updated_at=now)
            finally:
                self._close_conn(conn)

    def get_opponent_by_id(self, opp_id: int) -> Optional[Opponent]:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM opponents WHERE id = ?", (opp_id,))
                row = cursor.fetchone()
                if row:
                    return Opponent(
                        id=row["id"],
                        name=row["name"],
                        rating=row["rating"],
                        games_count=row["games_count"],
                        notes=row["notes"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"]
                    )
                return None
            finally:
                self._close_conn(conn)

    def list_opponents(self, search: str = "") -> List[Opponent]:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                if search:
                    cursor.execute("SELECT * FROM opponents WHERE name LIKE ? ORDER BY games_count DESC, name ASC", (f"%{search}%",))
                else:
                    cursor.execute("SELECT * FROM opponents ORDER BY games_count DESC, name ASC")
                rows = cursor.fetchall()
                return [
                    Opponent(
                        id=r["id"],
                        name=r["name"],
                        rating=r["rating"],
                        games_count=r["games_count"],
                        notes=r["notes"],
                        created_at=r["created_at"],
                        updated_at=r["updated_at"]
                    )
                    for r in rows
                ]
            finally:
                self._close_conn(conn)

    def update_opponent(self, opp: Opponent) -> None:
        now = datetime.now().isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE opponents SET name = ?, rating = ?, notes = ?, updated_at = ? WHERE id = ?",
                    (opp.name, opp.rating, opp.notes, now, opp.id)
                )
                conn.commit()
            finally:
                self._close_conn(conn)

    def delete_opponent(self, opp_id: int) -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM opponents WHERE id = ?", (opp_id,))
                conn.commit()
            finally:
                self._close_conn(conn)

    def record_game(self, game: GameRecord, moves: List[MoveObservation]) -> int:
        now = datetime.now().isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO games (opponent_id, white, black, result, date, time_control, eco, opening_name, pgn)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (game.opponent_id, game.white, game.black, game.result, game.date, game.time_control, game.eco, game.opening_name, game.pgn))
                game_id = cursor.lastrowid

                # Insert moves
                for m in moves:
                    cursor.execute("""
                    INSERT INTO move_observations (
                        game_id, move_ply, fen_before, move_san, eval_cp, eval_loss,
                        clock_remaining, is_inaccuracy, is_mistake, is_blunder, blunder_category
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        game_id, m.move_ply, m.fen_before, m.move_san, m.eval_cp, m.eval_loss,
                        m.clock_remaining, int(m.is_inaccuracy), int(m.is_mistake), int(m.is_blunder), m.blunder_category
                    ))

                # Update opponent games count
                cursor.execute("""
                UPDATE opponents SET
                    games_count = (SELECT COUNT(*) FROM games WHERE opponent_id = ?),
                    updated_at = ?
                WHERE id = ?
                """, (game.opponent_id, now, game.opponent_id))

                conn.commit()
                return game_id
            finally:
                self._close_conn(conn)

    def get_games_for_opponent(self, opp_id: int) -> List[GameRecord]:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM games WHERE opponent_id = ? ORDER BY id DESC", (opp_id,))
                rows = cursor.fetchall()
                return [
                    GameRecord(
                        id=r["id"],
                        opponent_id=r["opponent_id"],
                        white=r["white"],
                        black=r["black"],
                        result=r["result"],
                        date=r["date"] or "",
                        time_control=r["time_control"] or "",
                        eco=r["eco"] or "",
                        opening_name=r["opening_name"] or "",
                        pgn=r["pgn"]
                    )
                    for r in rows
                ]
            finally:
                self._close_conn(conn)

    def get_moves_by_fen(self, fen_prefix: str, opp_id: Optional[int] = None) -> List[Tuple[str, int]]:
        """
        Finds moves played from this FEN (or position prefix), returning (move_san, count).
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                if opp_id:
                    cursor.execute("""
                    SELECT m.move_san, COUNT(*) as cnt
                    FROM move_observations m
                    JOIN games g ON m.game_id = g.id
                    WHERE m.fen_before LIKE ? AND g.opponent_id = ?
                    GROUP BY m.move_san ORDER BY cnt DESC
                    """, (f"{fen_prefix}%", opp_id))
                else:
                    cursor.execute("""
                    SELECT move_san, COUNT(*) as cnt
                    FROM move_observations
                    WHERE fen_before LIKE ?
                    GROUP BY move_san ORDER BY cnt DESC
                    """, (f"{fen_prefix}%",))
                return [(r["move_san"], r["cnt"]) for r in cursor.fetchall()]
            finally:
                self._close_conn(conn)

    def get_all_opponent_moves(self, opp_id: int) -> List[MoveObservation]:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT m.*
                FROM move_observations m
                JOIN games g ON m.game_id = g.id
                WHERE g.opponent_id = ?
                ORDER BY m.id ASC
                """, (opp_id,))
                rows = cursor.fetchall()
                return [
                    MoveObservation(
                        id=r["id"],
                        game_id=r["game_id"],
                        move_ply=r["move_ply"],
                        fen_before=r["fen_before"],
                        move_san=r["move_san"],
                        eval_cp=r["eval_cp"],
                        eval_loss=r["eval_loss"],
                        clock_remaining=r["clock_remaining"],
                        is_inaccuracy=bool(r["is_inaccuracy"]),
                        is_mistake=bool(r["is_mistake"]),
                        is_blunder=bool(r["is_blunder"]),
                        blunder_category=r["blunder_category"] or ""
                    )
                    for r in rows
                ]
            finally:
                conn.close()
