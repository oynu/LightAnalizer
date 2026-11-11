"""
Data models for opponent profiling, games, and move observations.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Opponent:
    id: Optional[int] = None
    name: str = "Unknown"
    rating: Optional[int] = None
    games_count: int = 0
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

@dataclass
class GameRecord:
    id: Optional[int] = None
    opponent_id: int = 0
    white: str = ""
    black: str = ""
    result: str = "*"
    date: str = ""
    time_control: str = ""
    eco: str = ""
    opening_name: str = ""
    pgn: str = ""

@dataclass
class MoveObservation:
    id: Optional[int] = None
    game_id: int = 0
    move_ply: int = 0
    fen_before: str = ""
    move_san: str = ""
    eval_cp: Optional[int] = None
    eval_loss: Optional[int] = None
    clock_remaining: Optional[float] = None
    is_inaccuracy: bool = False
    is_mistake: bool = False
    is_blunder: bool = False
    blunder_category: str = ""
