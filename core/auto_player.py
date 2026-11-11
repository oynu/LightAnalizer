"""
Auto-Move planner: decides WHICH candidate (best / 2nd / 3rd) to play and HOW LONG to "think"
before the mouse clicks it. Pure logic (no Qt, no OS calls) so it is fully unit-testable.

Think-time model (seconds):
  * only legal move / forced reply ........ ~0.3 - 2.5
  * opening (first moves) ................. ~0.8 - 4
  * obvious recapture / crushing gap ...... ~0.8 - 3.5
  * clearly best move ..................... ~3 - 8
  * normal middlegame decision ............ ~10 - 30 (skewed to ~17)
  * sacrifices / brilliant ideas .......... ~14 - 30 (looks like deep calculation)
"""
from __future__ import annotations
import random
from typing import List, Optional, Tuple
import chess
from core.types import CandidateMove


def _eval_cp(c: CandidateMove) -> int:
    if c.mate_in is not None:
        return (10000 - abs(c.mate_in)) if c.mate_in > 0 else (-10000 + abs(c.mate_in))
    return c.score_cp if c.score_cp is not None else 0


class AutoMovePlanner:
    def __init__(self, rng: Optional[random.Random] = None, speed: float = 1.0):
        self.rng = rng or random.Random()
        self.speed = max(0.05, speed)       # >1 slower, <1 faster
        self.min_delay = 0.2
        # Alternative-move acceptance: maximum eval loss (pawns) and probability per rank
        self.rank2_max_loss = 0.18
        self.rank2_prob = 0.22
        self.rank3_max_loss = 0.28
        self.rank3_prob = 0.10

    # ------------------------------------------------------------------
    # Move choice
    # ------------------------------------------------------------------
    def choose_move(
        self,
        board: chess.Board,
        candidates: List[CandidateMove],
        brilliant_mode: bool = False
    ) -> Optional[Tuple[CandidateMove, str]]:
        """Returns (candidate, label) with label in {'best', '2nd best', '3rd best'} or None."""
        pool = [c for c in candidates[:3] if c.move in board.legal_moves]
        if not pool:
            return None

        top = pool[0]
        if len(pool) == 1 or board.legal_moves.count() == 1:
            return top, "best"
        if top.mate_in is not None and top.mate_in > 0:
            return top, "best"
        if brilliant_mode and top.is_brilliant:
            return top, "best"

        top_val = _eval_cp(top)
        roll = self.rng.random()
        for idx, (max_loss, prob) in ((1, (self.rank2_max_loss, self.rank2_prob)),
                                      (2, (self.rank3_max_loss, self.rank3_prob))):
            if idx >= len(pool):
                continue
            alt = pool[idx]
            if alt.mate_in is not None and alt.mate_in < 0:
                continue
            alt_val = _eval_cp(alt)
            loss = (top_val - alt_val) / 100.0
            if loss > max_loss:
                continue
            if top_val >= 200 and alt_val < 150:          # never throw away a winning position
                continue
            if top_val > -150 and alt_val <= -150:         # never step into a lost position
                continue
            if roll < prob:
                return alt, ("2nd best" if idx == 1 else "3rd best")
            roll -= prob
        return top, "best"

    # ------------------------------------------------------------------
    # Think time
    # ------------------------------------------------------------------
    def think_delay(
        self,
        board: chess.Board,
        chosen: CandidateMove,
        candidates: List[CandidateMove],
        last_opponent_move: Optional[chess.Move] = None
    ) -> Tuple[float, str]:
        """Returns (seconds_to_wait, reason)."""
        r = self.rng
        legal = board.legal_moves.count()
        pool = candidates[:3]
        gap = 9.0
        if len(pool) > 1:
            gap = (_eval_cp(pool[0]) - _eval_cp(pool[1])) / 100.0
        ply = board.ply()
        move = chosen.move
        mate = chosen.mate_in is not None and chosen.mate_in > 0
        is_sacrifice = bool(chosen.is_brilliant)

        if legal == 1:
            d, why = r.uniform(0.25, 0.7), "only move"
        elif board.is_check() and legal <= 3:
            d, why = r.uniform(0.8, 2.5), "forced reply to check"
        elif ply < 10 and not is_sacrifice:
            d, why = r.uniform(0.8, 3.5), "opening"
        elif ply < 14 and is_sacrifice:
            d, why = r.uniform(2.0, 6.0), "prepared gambit"
        elif (last_opponent_move is not None and board.is_capture(move)
              and last_opponent_move.to_square == move.to_square and gap >= 1.0):
            d, why = r.uniform(0.8, 2.5), "obvious recapture"
        elif mate or gap >= 3.0:
            d, why = r.uniform(1.0, 3.5), "obvious"
        elif gap >= 1.5:
            d, why = r.uniform(3.0, 8.0), "clear move"
        else:
            base = r.triangular(10.0, 30.0, 17.0)
            if legal >= 35:
                base *= 1.08
            if gap < 0.15:
                base *= 1.10
            if is_sacrifice:
                base = max(base, r.uniform(14.0, 30.0))
            d, why = min(30.0, max(10.0, base)), ("deep calculation" if is_sacrifice else "thinking")

        return max(self.min_delay, d * self.speed), why
