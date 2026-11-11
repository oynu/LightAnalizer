"""
Opponent profiling engine: extracts empirical patterns from historical moves and games.
Strictly distinguishes confirmed observations, emerging patterns, and low-confidence hypotheses.
"""
from __future__ import annotations
from typing import List, Dict, Tuple, Optional
from collections import Counter
import chess
from core.types import OpponentInsight, ConfidenceLevel
from core.opponent.models import Opponent, GameRecord, MoveObservation
from core.opponent.repository import OpponentRepository

class OpponentProfiler:
    """
    Analyzes historical game data to generate evidence-based opponent profiles.
    """
    def __init__(self, repo: OpponentRepository):
        self.repo = repo

    def generate_profile_insights(self, opponent_id: int) -> List[OpponentInsight]:
        games = self.repo.get_games_for_opponent(opponent_id)
        if not games:
            return [
                OpponentInsight(
                    title="No Historical Games Recorded",
                    text="Analyze or import games played by this opponent to build an empirical profile.",
                    confidence=ConfidenceLevel.HYPOTHESIS,
                    sample_size=0,
                    evidence_summary="0 recorded games available.",
                    category="General"
                )
            ]

        moves = self.repo.get_all_opponent_moves(opponent_id)
        insights: List[OpponentInsight] = []

        # 1. Opening tendencies
        opening_insights = self._analyze_openings(games, moves)
        insights.extend(opening_insights)

        # 2. Tactical vulnerabilities
        tactical_insights = self._analyze_tactical_behavior(moves, len(games))
        insights.extend(tactical_insights)

        # 3. Positional tendencies
        positional_insights = self._analyze_positional_tendencies(moves, games)
        insights.extend(positional_insights)

        # 4. Time management (if clock info present)
        time_insights = self._analyze_time_management(moves)
        insights.extend(time_insights)

        return insights

    def _determine_confidence(self, count: int, total: int, ratio: float) -> ConfidenceLevel:
        if count >= 5 and ratio >= 0.65:
            return ConfidenceLevel.CONFIRMED
        elif count >= 3:
            return ConfidenceLevel.EMERGING
        else:
            return ConfidenceLevel.HYPOTHESIS

    def _analyze_openings(self, games: List[GameRecord], moves: List[MoveObservation]) -> List[OpponentInsight]:
        insights = []
        total_games = len(games)

        # Analyze responses to 1.e4 and 1.d4
        responses_to_e4 = []
        responses_to_d4 = []

        for g in games:
            # Check early moves from move observations
            game_moves = [m for m in moves if m.game_id == g.id]
            game_moves.sort(key=lambda m: m.move_ply)
            
            if len(game_moves) >= 2:
                # Ply 1: White's first move, Ply 2: Black's response
                first_move = game_moves[0].move_san
                second_move = game_moves[1].move_san
                if first_move == "e4":
                    responses_to_e4.append(second_move)
                elif first_move == "d4":
                    responses_to_d4.append(second_move)

        if responses_to_e4:
            c = Counter(responses_to_e4)
            most_common, count = c.most_common(1)[0]
            ratio = count / len(responses_to_e4)
            conf = self._determine_confidence(count, len(responses_to_e4), ratio)
            insights.append(OpponentInsight(
                title=f"Response to 1.e4: {most_common}",
                text=f"Plays {most_common} in {count} of {len(responses_to_e4)} recorded games ({ratio*100:.0f}%) against 1.e4.",
                confidence=conf,
                sample_size=len(responses_to_e4),
                evidence_summary=f"{count}/{len(responses_to_e4)} games selected {most_common}.",
                category="Opening",
                historical_examples=[f"Played {most_common} in {count} games"]
            ))

        if responses_to_d4:
            c = Counter(responses_to_d4)
            most_common, count = c.most_common(1)[0]
            ratio = count / len(responses_to_d4)
            conf = self._determine_confidence(count, len(responses_to_d4), ratio)
            insights.append(OpponentInsight(
                title=f"Response to 1.d4: {most_common}",
                text=f"Plays {most_common} in {count} of {len(responses_to_d4)} recorded games ({ratio*100:.0f}%) against 1.d4.",
                confidence=conf,
                sample_size=len(responses_to_d4),
                evidence_summary=f"{count}/{len(responses_to_d4)} games selected {most_common}.",
                category="Opening",
                historical_examples=[f"Played {most_common} in {count} games"]
            ))

        # Overall favored opening systems (ECO codes)
        ecos = [g.eco for g in games if g.eco]
        if ecos:
            eco_counts = Counter(ecos)
            favored_eco, cnt = eco_counts.most_common(1)[0]
            favored_name = next((g.opening_name for g in games if g.eco == favored_eco and g.opening_name), favored_eco)
            ratio = cnt / total_games
            conf = self._determine_confidence(cnt, total_games, ratio)
            insights.append(OpponentInsight(
                title=f"Favored System: {favored_name} ({favored_eco})",
                text=f"Selected {favored_name} in {cnt} of {total_games} games ({ratio*100:.0f}%).",
                confidence=conf,
                sample_size=total_games,
                evidence_summary=f"{cnt} of {total_games} games under ECO {favored_eco}.",
                category="Opening"
            ))

        return insights

    def _analyze_tactical_behavior(self, moves: List[MoveObservation], total_games: int) -> List[OpponentInsight]:
        insights = []
        if not moves:
            return insights

        blunders = [m for m in moves if m.is_blunder]
        mistakes = [m for m in moves if m.is_mistake]
        blunder_count = len(blunders)

        # Tactical blunder categories
        blunder_categories = [b.blunder_category for b in blunders if b.blunder_category]
        if blunder_categories:
            cat_counts = Counter(blunder_categories)
            top_vuln, vuln_cnt = cat_counts.most_common(1)[0]
            ratio = vuln_cnt / blunder_count
            conf = self._determine_confidence(vuln_cnt, blunder_count, ratio)
            insights.append(OpponentInsight(
                title=f"Tactical Vulnerability: {top_vuln.capitalize()}",
                text=f"Repeatedly vulnerable to {top_vuln} ({vuln_cnt} observed blunders out of {blunder_count} total blunders).",
                confidence=conf,
                sample_size=blunder_count,
                evidence_summary=f"{vuln_cnt} blunders categorized under '{top_vuln}'.",
                category="Tactical"
            ))

        # Average centipawn loss (ACPL)
        eval_losses = [m.eval_loss for m in moves if m.eval_loss is not None and m.eval_loss > 0]
        if eval_losses:
            avg_loss = sum(eval_losses) / len(eval_losses)
            conf = ConfidenceLevel.CONFIRMED if len(eval_losses) >= 50 else ConfidenceLevel.EMERGING
            insights.append(OpponentInsight(
                title="Decision Accuracy (ACPL)",
                text=f"Average centipawn loss of {avg_loss:.1f} cp across {len(eval_losses)} evaluated moves.",
                confidence=conf,
                sample_size=len(eval_losses),
                evidence_summary=f"Calculated from {len(eval_losses)} historical moves.",
                category="Decision"
            ))

        return insights

    def _analyze_positional_tendencies(self, moves: List[MoveObservation], games: List[GameRecord]) -> List[OpponentInsight]:
        insights = []
        # Check queen trade frequency
        queen_trades = 0
        games_with_queen_moves = 0
        for g in games:
            g_moves = [m.move_san for m in moves if m.game_id == g.id]
            # Check if queens traded early
            has_q_trade = any("Qx" in m for m in g_moves[:30])
            if has_q_trade:
                queen_trades += 1

        if games:
            ratio = queen_trades / len(games)
            if ratio >= 0.6:
                conf = self._determine_confidence(queen_trades, len(games), ratio)
                insights.append(OpponentInsight(
                    title="Positional Habit: Frequent Piece Simplification",
                    text=f"Promptly exchanges queens into endgames in {queen_trades} of {len(games)} games ({ratio*100:.0f}%).",
                    confidence=conf,
                    sample_size=len(games),
                    evidence_summary=f"{queen_trades}/{len(games)} games feature early queen trades.",
                    category="Positional"
                ))
            elif ratio <= 0.2 and len(games) >= 4:
                conf = self._determine_confidence(len(games) - queen_trades, len(games), 1.0 - ratio)
                insights.append(OpponentInsight(
                    title="Positional Habit: Maintains Tension & Avoids Early Simplification",
                    text=f"Retains queens on board in {(1.0-ratio)*100:.0f}% of recorded games, favoring complex middlegames.",
                    confidence=conf,
                    sample_size=len(games),
                    evidence_summary=f"{len(games)-queen_trades}/{len(games)} games maintain queen tension.",
                    category="Positional"
                ))

        return insights

    def _analyze_time_management(self, moves: List[MoveObservation]) -> List[OpponentInsight]:
        insights = []
        time_moves = [m for m in moves if m.clock_remaining is not None]
        if not time_moves:
            return insights

        # Check blunders under low time (< 30s)
        low_time_blunders = [m for m in time_moves if m.clock_remaining is not None and m.clock_remaining < 30.0 and m.is_blunder]
        if len(low_time_blunders) >= 2:
            conf = ConfidenceLevel.CONFIRMED if len(low_time_blunders) >= 4 else ConfidenceLevel.EMERGING
            insights.append(OpponentInsight(
                title="Time Pressure Susceptibility",
                text=f"Observed {len(low_time_blunders)} blunders when clock falls below 30 seconds.",
                confidence=conf,
                sample_size=len(low_time_blunders),
                evidence_summary=f"{len(low_time_blunders)} moves with clock < 30s resulted in severe evaluation loss.",
                category="Time"
            ))

        return insights
