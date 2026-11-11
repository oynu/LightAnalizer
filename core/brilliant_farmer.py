"""
Brilliant Farmer: Engine-backed detection and farming of Brilliant Moves (!!).
Identifies high-impact material sacrifices that lead to favorable positions,
king exposure, tactical breakthroughs, Greek Gift attacks, and stalemate traps.
"""
from __future__ import annotations
from typing import List, Optional, Tuple, Dict
import chess
from core.types import CandidateMove

class BrilliantFarmer:
    """
    Identifies and prioritizes Brilliant Moves (!!) according to competitive chess standards:
    1. Material sacrifice (piece, exchange, queen, or pawn sacrifice).
    2. Best or near-best move by engine evaluation (drop-off to alternatives).
    3. Non-obvious tactical idea (deep calculation, king shelter destruction, deflection).
    4. Favorable outcome (winning advantage or drawing resource in difficult positions).
    5. Competitive context (not already completely winning e.g. +15 cp).
    """

    PIECE_VALUES: Dict[chess.PieceType, int] = {
        chess.PAWN: 100,
        chess.KNIGHT: 320,
        chess.BISHOP: 330,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 0
    }

    PIECE_NAMES: Dict[chess.PieceType, str] = {
        chess.PAWN: "pawn",
        chess.KNIGHT: "knight",
        chess.BISHOP: "bishop",
        chess.ROOK: "rook",
        chess.QUEEN: "queen",
        chess.KING: "king"
    }

    def process_candidates(
        self,
        board: chess.Board,
        candidates: List[CandidateMove]
    ) -> List[CandidateMove]:
        """
        Analyzes candidate moves in the position. If a sound, favorable material sacrifice
        is identified, promotes it to the top recommendation and tags it as Brilliant (!!).
        """
        if not candidates:
            return []

        processed: List[CandidateMove] = []
        brilliant_cands: List[Tuple[CandidateMove, str]] = []

        # Find best candidate evaluation for drop-off comparison
        best_cand = candidates[0]
        best_score = best_cand.score_cp if best_cand.score_cp is not None else 0

        for cand in candidates:
            is_brill, reason = self.evaluate_move_brilliance(board, cand, best_cand)
            if is_brill:
                cand.is_brilliant = True
                cand.brilliant_reason = reason
                brilliant_cands.append((cand, reason))
            processed.append(cand)

        # If a brilliant sacrifice is found, promote it to Rank 1
        if brilliant_cands:
            # Sort brilliant candidates by eval (mate first, then score_cp)
            brilliant_cands.sort(
                key=lambda x: (
                    10000 if (x[0].mate_in and x[0].mate_in > 0)
                    else (-10000 if (x[0].mate_in and x[0].mate_in < 0)
                    else (x[0].score_cp or 0))
                ),
                reverse=True
            )
            top_brilliant, reason = brilliant_cands[0]

            # Re-order: place top brilliant move at index 0 (Rank 1)
            reordered = [top_brilliant]
            for c in processed:
                if c.move != top_brilliant.move:
                    reordered.append(c)

            # Re-assign ranks 1, 2, 3
            for idx, c in enumerate(reordered[:3]):
                c.rank = idx + 1
                c.is_best = (idx == 0)

            return reordered

        return processed

    def evaluate_move_brilliance(
        self,
        board: chess.Board,
        cand: CandidateMove,
        best_cand: CandidateMove
    ) -> Tuple[bool, str]:
        """
        Evaluates whether a candidate move qualifies as a Brilliant Move (!!).
        Returns (is_brilliant, reason_string).
        """
        move = cand.move
        turn = board.turn
        opp = not turn

        # 1. Favorable Outcome Requirement:
        # Move must be Rank 1 or within 0.35 pawns of the engine's top choice
        if cand.eval_diff is not None and cand.eval_diff < -0.35:
            return False, ""

        # Score must be favorable (positive, winning, or holding draw in lost position)
        if cand.mate_in is not None:
            if cand.mate_in < 0:
                return False, ""  # Don't sacrifice into opponent forced mate
        elif cand.score_cp is not None:
            # Not already overwhelmingly winning (+12.0) where any random move wins
            if cand.score_cp > 1200:
                return False, ""
            # Must lead to playable/good position (score >= -40 cp)
            if cand.score_cp < -50:
                # Exception: Stalemate trick from a dead-lost position
                if not self._is_stalemate_desperado(board, move):
                    return False, ""

        # 2. Material Sacrifice Requirement:
        is_sac, sac_type, sac_desc = self._is_material_sacrifice(board, move)
        if not is_sac:
            return False, ""

        # 3. Non-Obvious / Tactical Depth Check:
        # Avoid simple trades: if opponent cannot recapture, it's not a sacrifice, just a free piece.
        test_board = board.copy()
        test_board.push(move)

        # Build compelling brilliant description
        reason = f"{sac_type}: {sac_desc}"
        return True, reason

    def _is_material_sacrifice(
        self,
        board: chess.Board,
        move: chess.Move
    ) -> Tuple[bool, str, str]:
        """
        Detects if a move gives up material (piece, exchange, queen, or key pawn).
        Returns (is_sacrifice, sacrifice_type, description).
        """
        turn = board.turn
        opp = not turn
        piece = board.piece_at(move.from_square)
        captured = board.piece_at(move.to_square)

        if not piece:
            return False, "", ""

        p_type = piece.piece_type
        p_val = self.PIECE_VALUES[p_type]
        c_val = self.PIECE_VALUES[captured.piece_type] if captured else 0

        # Simulation after move
        test_board = board.copy()
        test_board.push(move)
        dest_attackers = test_board.attackers(opp, move.to_square)
        dest_defenders = test_board.attackers(turn, move.to_square)

        # ----------------------------------------------------
        # Pattern 1: Classic Greek Gift Bishop Sacrifice (Bxh7+ / Bxh2+)
        # ----------------------------------------------------
        if p_type == chess.BISHOP and captured and captured.piece_type == chess.PAWN:
            if turn == chess.WHITE and move.to_square == chess.H7:
                opp_king = board.king(chess.BLACK)
                if opp_king in [chess.G8, chess.H8]:
                    return True, "Greek Gift Sacrifice", "Sacrifices bishop on h7 shattering king shelter to unleash decisive mating attack"
            elif turn == chess.BLACK and move.to_square == chess.H2:
                opp_king = board.king(chess.WHITE)
                if opp_king in [chess.G1, chess.H1]:
                    return True, "Greek Gift Sacrifice", "Sacrifices bishop on h2 shattering king shelter to unleash decisive mating attack"

        # ----------------------------------------------------
        # Pattern 2: Queen Sacrifice (giving up Queen for lesser piece or square)
        # ----------------------------------------------------
        if p_type == chess.QUEEN and len(dest_attackers) > 0:
            if c_val < 900:
                p_opp_name = self.PIECE_NAMES[captured.piece_type] if captured else "empty square"
                return True, "Queen Sacrifice", f"Sacrifices queen into {chess.square_name(move.to_square)} forcing an unstoppable tactical breakthrough"

        # ----------------------------------------------------
        # Pattern 3: Exchange Sacrifice (Rook for Minor or Pawn)
        # ----------------------------------------------------
        if p_type == chess.ROOK:
            # Direct exchange capture: Rook takes Bishop or Knight
            if captured and captured.piece_type in [chess.BISHOP, chess.KNIGHT]:
                if len(dest_attackers) > 0:
                    c_name = self.PIECE_NAMES[captured.piece_type]
                    return True, "Exchange Sacrifice", f"Gives up rook for {c_name} on {chess.square_name(move.to_square)} to seize dominant tactical initiative"
            # Rook takes Pawn where Rook will be recaptured
            elif captured and captured.piece_type == chess.PAWN:
                if len(dest_attackers) > 0:
                    return True, "Exchange Sacrifice", f"Sacrifices rook on {chess.square_name(move.to_square)} cracking opponent pawn chain"
            # Rook enters attacked square undefended or attacked by lower piece
            elif not captured and len(dest_attackers) > 0:
                pawn_attackers = [sq for sq in dest_attackers if test_board.piece_at(sq) and test_board.piece_at(sq).piece_type == chess.PAWN]
                minor_attackers = [sq for sq in dest_attackers if test_board.piece_at(sq) and test_board.piece_at(sq).piece_type in [chess.KNIGHT, chess.BISHOP]]
                if pawn_attackers or minor_attackers or len(dest_attackers) > len(dest_defenders):
                    return True, "Exchange Sacrifice", f"Offers rook sacrifice on {chess.square_name(move.to_square)} to infiltrate opponent camp"

        # ----------------------------------------------------
        # Pattern 4: Minor Piece Sacrifice (Knight or Bishop)
        # ----------------------------------------------------
        if p_type in [chess.KNIGHT, chess.BISHOP]:
            p_name = self.PIECE_NAMES[p_type]
            # Capture pawn/minor with net negative material
            if captured and p_val > c_val + 150:
                if len(dest_attackers) > 0:
                    return True, f"{p_name.capitalize()} Sacrifice", f"Sacrifices {p_name} taking pawn on {chess.square_name(move.to_square)} tearing open lines"
            # Piece moved to attacked square with fewer defenders than attackers, or attacked by pawn
            elif not captured and len(dest_attackers) > 0:
                pawn_attackers = [sq for sq in dest_attackers if test_board.piece_at(sq) and test_board.piece_at(sq).piece_type == chess.PAWN]
                if pawn_attackers or len(dest_attackers) > len(dest_defenders):
                    return True, f"{p_name.capitalize()} Sacrifice", f"Places {p_name} on {chess.square_name(move.to_square)} en prise to deflect defenders"

        # ----------------------------------------------------
        # Pattern 5: Leaving a more valuable piece en prise (Counter-attack)
        # ----------------------------------------------------
        # Check if an existing Queen or Rook was attacked and we moved a pawn/minor instead
        if p_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP]:
            for sq in chess.SQUARES:
                my_p = board.piece_at(sq)
                if my_p and my_p.color == turn and my_p.piece_type in [chess.QUEEN, chess.ROOK] and sq != move.from_square:
                    # Was this piece attacked before, and still attacked after?
                    if board.is_attacked_by(opp, sq) and test_board.is_attacked_by(opp, sq):
                        # Moving piece did not defend it
                        if sq not in test_board.attacks(move.to_square):
                            valuable_name = self.PIECE_NAMES[my_p.piece_type]
                            return True, f"Counter-Intuitive {valuable_name.capitalize()} Sacrifice", f"Ignores attack on {valuable_name} to launch lethal counter-strike"

        # ----------------------------------------------------
        # Pattern 6: Desperado Stalemate Sacrifice
        # ----------------------------------------------------
        if self._is_stalemate_desperado(board, move):
            return True, "Desperado Stalemate Trick", "Sacrifices piece to force stalemate defense from difficult position"

        return False, "", ""

    def _is_stalemate_desperado(self, board: chess.Board, move: chess.Move) -> bool:
        """Checks if sacrificing the piece forces a stalemate draw."""
        test_board = board.copy()
        test_board.push(move)
        # Check if opponent has capture that leads to stalemate
        for opp_move in test_board.legal_moves:
            if opp_move.to_square == move.to_square:
                sub_board = test_board.copy()
                sub_board.push(opp_move)
                if sub_board.is_stalemate():
                    return True
        return False
