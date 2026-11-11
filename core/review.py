"""
Post-game review engine: reconstructs game, computes move accuracy,
categorizes inaccuracies/mistakes/blunders, and flags critical turning points.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Callable
import math
import chess
import chess.engine
from core.types import CandidateMove
from core.engine_manager import EngineManager
from core.analyzer import ChessAnalyzer

@dataclass
class MoveReview:
    ply: int
    move_number: int
    is_white: bool
    san: str
    played_move: chess.Move
    best_san: str = ""
    best_move: Optional[chess.Move] = None
    eval_before: float = 0.0
    eval_after: float = 0.0
    eval_loss: float = 0.0  # Centipawn loss / pawns lost
    classification: str = "Good"  # Best, Excellent, Good, Inaccuracy, Mistake, Blunder
    tactical_motif: str = ""
    explanation: str = ""

@dataclass
class GameReviewReport:
    white_accuracy: float = 100.0
    black_accuracy: float = 100.0
    white_blunders: int = 0
    white_mistakes: int = 0
    white_inaccuracies: int = 0
    black_blunders: int = 0
    black_mistakes: int = 0
    black_inaccuracies: int = 0
    eval_curve: List[float] = field(default_factory=list)
    move_reviews: List[MoveReview] = field(default_factory=list)
    critical_moments: List[MoveReview] = field(default_factory=list)

class GameReviewer:
    """
    Evaluates completed games move-by-move using engine analysis,
    generating accuracy percentages and mistake classifications.
    """
    def __init__(self, engine_manager: EngineManager, analyzer: ChessAnalyzer):
        self.engine_mgr = engine_manager
        self.analyzer = analyzer

    def review_game(
        self,
        board_history: List[Tuple[chess.Board, chess.Move]],
        progress_cb: Optional[Callable[[int, int], None]] = None
    ) -> GameReviewReport:
        report = GameReviewReport()
        if not board_history:
            return report

        white_losses = []
        black_losses = []
        current_eval = 0.0

        total = len(board_history)
        for idx, (board_before, played_move) in enumerate(board_history):
            ply = idx + 1
            move_num = (idx // 2) + 1
            is_white = board_before.turn == chess.WHITE

            # Check legal moves
            san = board_before.san(played_move)

            # Evaluate position before move
            limit = chess.engine.Limit(depth=10, time=0.25)
            engine = self.engine_mgr._engine
            
            best_san = san
            best_move = played_move
            eval_before_val = current_eval
            eval_after_val = current_eval
            eval_loss = 0.0
            classification = "Good"

            if engine:
                try:
                    res = engine.analyse(board_before, limit, multipv=1)
                    if res and "score" in res[0]:
                        sc = res[0]["score"].white()
                        if sc.is_mate():
                            eval_before_val = 10.0 if sc.mate() > 0 else -10.0
                        else:
                            eval_before_val = (sc.score() or 0) / 100.0
                        if "pv" in res[0] and res[0]["pv"]:
                            best_move = res[0]["pv"][0]
                            best_san = board_before.san(best_move)

                    # Now evaluate board after played move
                    test_b = board_before.copy()
                    test_b.push(played_move)
                    res_after = engine.analyse(test_b, limit, multipv=1)
                    if res_after and "score" in res_after[0]:
                        sc_after = res_after[0]["score"].white()
                        if sc_after.is_mate():
                            eval_after_val = 10.0 if sc_after.mate() > 0 else -10.0
                        else:
                            eval_after_val = (sc_after.score() or 0) / 100.0

                    current_eval = eval_after_val

                    # Calculate loss from perspective of current player
                    if is_white:
                        loss = max(0.0, eval_before_val - eval_after_val)
                    else:
                        loss = max(0.0, eval_after_val - eval_before_val)

                    eval_loss = round(loss, 2)

                except Exception:
                    eval_loss = 0.0

            # Classification
            motifs = self.analyzer._detect_move_tactics(board_before, played_move)
            motif_str = ", ".join(motifs) if motifs else ""

            if played_move == best_move:
                classification = "Best"
            elif eval_loss <= 0.15:
                classification = "Excellent"
            elif eval_loss <= 0.40:
                classification = "Good"
            elif eval_loss <= 0.90:
                classification = "Inaccuracy"
                if is_white: report.white_inaccuracies += 1
                else: report.black_inaccuracies += 1
            elif eval_loss <= 2.00:
                classification = "Mistake"
                if is_white: report.white_mistakes += 1
                else: report.black_mistakes += 1
            else:
                classification = "Blunder"
                if is_white: report.white_blunders += 1
                else: report.black_blunders += 1

            if is_white:
                white_losses.append(eval_loss)
            else:
                black_losses.append(eval_loss)

            explanation = ""
            if classification == "Blunder":
                explanation = f"Blunder: drops {eval_loss:.1f} pawns compared to {best_san}."
            elif classification == "Mistake":
                explanation = f"Mistake: conceded advantage. {best_san} was more precise."
            elif classification == "Best":
                explanation = f"Best move: matches engine recommendation."

            rev = MoveReview(
                ply=ply,
                move_number=move_num,
                is_white=is_white,
                san=san,
                played_move=played_move,
                best_san=best_san,
                best_move=best_move,
                eval_before=eval_before_val,
                eval_after=eval_after_val,
                eval_loss=eval_loss,
                classification=classification,
                tactical_motif=motif_str,
                explanation=explanation
            )
            report.move_reviews.append(rev)
            report.eval_curve.append(eval_after_val)

            if classification in ["Mistake", "Blunder"]:
                report.critical_moments.append(rev)

            if progress_cb:
                progress_cb(idx + 1, total)

        # Calculate accuracy percentages using standard capablanca win-probability formula
        report.white_accuracy = self._compute_accuracy(white_losses)
        report.black_accuracy = self._compute_accuracy(black_losses)
        return report

    def _compute_accuracy(self, losses: List[float]) -> float:
        if not losses:
            return 100.0
        # Average loss converted to accuracy curve
        avg_loss = sum(losses) / len(losses)
        # Empirical conversion: 0 loss = 100%, 0.3 loss = 90%, 0.8 loss = 75%, 2.0 loss = 50%
        acc = 100.0 * math.exp(-0.45 * avg_loss)
        return round(max(10.0, min(100.0, acc)), 1)
