"""
Data-driven practical opponent prediction system.
Evaluates historical move tendencies in the current position, separate from engine evaluation.
"""
from __future__ import annotations
from typing import Optional, List
import chess
from core.types import PredictionResult, CandidateMove, ConfidenceLevel
from core.opponent.repository import OpponentRepository

class OpponentPredictor:
    """
    Predicts likely opponent moves based strictly on empirical historical records
    and identifies critical tactical responses to prepare for.
    """
    def __init__(self, repo: OpponentRepository):
        self.repo = repo

    def predict_tendency(
        self,
        board: chess.Board,
        opponent_id: Optional[int],
        engine_candidates: List[CandidateMove]
    ) -> PredictionResult:
        result = PredictionResult()
        if engine_candidates:
            result.engine_best_move = engine_candidates[0]

        # 1. Query exact or prefix FEN for historically played moves
        fen_key = " ".join(board.fen().split(" ")[:2])  # piece placement and turn
        history_moves = self.repo.get_moves_by_fen(fen_key, opponent_id) if opponent_id else []

        if history_moves:
            top_move_san, count = history_moves[0]
            total_seen = sum(c for _, c in history_moves)
            ratio = count / total_seen

            result.predicted_opponent_move = top_move_san
            result.sample_size = total_seen

            if count >= 4 and ratio >= 0.7:
                result.predicted_move_confidence = ConfidenceLevel.CONFIRMED
            elif count >= 2:
                result.predicted_move_confidence = ConfidenceLevel.EMERGING
            else:
                result.predicted_move_confidence = ConfidenceLevel.HYPOTHESIS

            result.predicted_evidence = (
                f"Opponent historically chose '{top_move_san}' in {count} of {total_seen} "
                f"recorded games ({ratio*100:.0f}%) from this position."
            )
        else:
            result.predicted_opponent_move = None
            result.predicted_evidence = "No historical games recorded for this exact position against this opponent."

        # 2. Critical tactical response from engine candidate continuation
        if engine_candidates and engine_candidates[0].pv and len(engine_candidates[0].pv) >= 2:
            best_cand = engine_candidates[0]
            test_board = board.copy()
            test_board.push(best_cand.move)
            critical_reply = best_cand.pv[1]
            try:
                reply_san = test_board.san(critical_reply)
                result.critical_tactical_response = reply_san
                result.tactical_response_reason = (
                    f"Objectively critical defense: Stockfish considers {reply_san} the most resilient counter "
                    f"to your best move {best_cand.san}."
                )
            except Exception:
                pass

        return result
