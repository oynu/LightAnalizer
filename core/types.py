"""
Core domain types and data models for LightAnalizer chess assistant.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Any
import chess
import numpy as np

class OperatingMode(str, Enum):
    ANALYSIS = "Analysis Mode"
    TRAINING = "Training Mode"
    LIVE_OBSERVATION = "Live Observation Mode"
    POST_GAME_REVIEW = "Post-Game Review"

class SyncStatus(str, Enum):
    SYNCHRONIZED = "Synchronized"
    SYNCHRONIZING = "Synchronizing..."
    POSITION_UNCERTAIN = "Position uncertain"
    BOARD_UNAVAILABLE = "Board unavailable"

class ConfidenceLevel(str, Enum):
    CONFIRMED = "Confirmed observation"
    EMERGING = "Emerging pattern"
    HYPOTHESIS = "Low-confidence hypothesis"

@dataclass
class CandidateMove:
    move: chess.Move
    san: str
    rank: int  # 1 for best, 2 for second-best, 3 for third-best
    score_cp: Optional[int] = None
    mate_in: Optional[int] = None
    eval_str: str = "0.0"
    eval_diff: Optional[float] = 0.0  # Difference relative to the best move
    pv: List[chess.Move] = field(default_factory=list)
    pv_san: List[str] = field(default_factory=list)
    short_explanation: str = ""
    strategic_idea: str = ""
    risks_and_responses: str = ""
    tactical_motifs: List[str] = field(default_factory=list)
    is_best: bool = False

@dataclass
class PositionSummary:
    fen: str
    turn: chess.Color
    material_balance_cp: int = 0
    material_str: str = "Equal material"
    king_safety_white: str = "Safe"
    king_safety_black: str = "Safe"
    tactical_threats: List[str] = field(default_factory=list)
    positional_factors: List[str] = field(default_factory=list)
    opponent_threats: List[str] = field(default_factory=list)
    main_objective: str = ""
    natural_inaccuracy_warning: Optional[str] = None
    coach_takeaway: str = ""
    is_check: bool = False
    is_checkmate: bool = False
    is_stalemate: bool = False

@dataclass
class OpponentInsight:
    title: str
    text: str
    confidence: ConfidenceLevel
    sample_size: int
    evidence_summary: str
    category: str  # Opening, Tactical, Positional, Decision, Time
    historical_examples: List[str] = field(default_factory=list)

@dataclass
class PredictionResult:
    engine_best_move: Optional[CandidateMove] = None
    predicted_opponent_move: Optional[str] = None
    predicted_move_confidence: Optional[ConfidenceLevel] = None
    predicted_evidence: Optional[str] = None
    critical_tactical_response: Optional[str] = None
    tactical_response_reason: Optional[str] = None
    sample_size: int = 0

@dataclass
class BoardCalibration:
    x: int = 0
    y: int = 0
    width: int = 400
    height: int = 400
    device_pixel_ratio: float = 1.0
    orientation_white_bottom: bool = True
    confidence_threshold: float = 0.70
    is_calibrated: bool = False

@dataclass
class DiagnosticsData:
    capture_ms: float = 0.0
    recognition_ms: float = 0.0
    validation_ms: float = 0.0
    engine_ms: float = 0.0
    total_latency_ms: float = 0.0
    fps: float = 0.0
    sync_status: SyncStatus = SyncStatus.BOARD_UNAVAILABLE
    detected_fen: str = ""
    authoritative_fen: str = ""
    last_move_san: str = ""
    rejection_reason: str = ""
    confidence: float = 0.0
    cropped_image: Optional[np.ndarray] = None
    device_pixel_ratio: float = 1.0
