"""
Brilliant Farmer: Engine-backed detection, discovery, and farming of Brilliant Moves (!!).
Identifies high-impact material sacrifices that lead to favorable positions, king shelter
destruction, en prise counter-attacks, Greek Gift sacrifices, gambit breaks, and stalemate traps.
"""
from __future__ import annotations
from typing import List, Optional, Tuple, Dict, Set
import chess
from core.types import CandidateMove

class BrilliantFarmer:
    """
    Identifies, prioritizes, and farms Brilliant Moves (!!) according to competitive standards:
    1. Material sacrifice: Gives up Queen, Rook, Minor piece, or key Pawn, or leaves a piece en prise.
    2. Favorable or winning outcome: Retains solid advantage or positive eval (within reasonable delta).
    3. Non-obvious tactical initiative: King attacks, deflections, line clearances, or counter-blows.
    4. Not already overwhelmingly trivial (e.g. not +15 cp where any blunder still wins).
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
        Analyzes candidate moves in the position. If a sound material sacrifice is identified,
        promotes it to Rank 1 and flags it as Brilliant (!!).
        """
        if not candidates:
            return []

        processed: List[CandidateMove] = []
        brilliant_cands: List[Tuple[CandidateMove, str]] = []

        best_cand = candidates[0]

        for cand in candidates:
            is_brill, reason = self.evaluate_move_brilliance(board, cand, best_cand)
            if is_brill:
                cand.is_brilliant = True
                cand.brilliant_reason = reason
                brilliant_cands.append((cand, reason))
            else:
                cand.is_brilliant = False
                cand.brilliant_reason = ""
            processed.append(cand)

        # If one or more brilliant moves are discovered, promote the best brilliant move to Rank 1
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
            top_brilliant, _ = brilliant_cands[0]

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

        # 1. Competitive Context:
        # Not already completely crushed (+12.00 cp / mate-in-1 against zero pieces)
        if cand.score_cp is not None and cand.score_cp > 1200:
            return False, ""

        # 2. Favorable / Sound Outcome:
        # Avoid blunders: do not sacrifice into an opponent forced mate
        if cand.mate_in is not None and cand.mate_in < 0:
            return False, ""

        # Drop-off check:
        # On Chess.com, a sacrifice does not need to be 0.00 delta.
        # It is brilliant if it is best move, OR within 0.85 pawns of best move,
        # OR still maintains a solid advantage (score_cp >= 75 cp or forced mate).
        diff = cand.eval_diff if cand.eval_diff is not None else 0.0
        score = cand.score_cp if cand.score_cp is not None else 0
        mate = cand.mate_in

        is_competitive_or_sound = (
            cand.is_best
            or diff >= -0.85
            or score >= 75
            or (mate is not None and mate > 0)
        )
        if not is_competitive_or_sound:
            # Exception: Stalemate desperado trick from lost position
            if not self._is_stalemate_desperado(board, move):
                return False, ""

        # Avoid sacrifices into dead lost positions (score < -150 cp) unless desperado
        if score < -150 and mate is None:
            if not self._is_stalemate_desperado(board, move):
                return False, ""

        # 3. Material Sacrifice Detection:
        is_sac, sac_type, sac_desc = self._is_material_sacrifice(board, move)
        if not is_sac:
            return False, ""

        reason = f"{sac_type}: {sac_desc}"
        return True, reason

    def is_move_sound_sacrifice(self, board: chess.Board, move: chess.Move) -> Tuple[bool, str]:
        """Direct check if a legal move is a recognized material sacrifice."""
        is_sac, sac_type, sac_desc = self._is_material_sacrifice(board, move)
        if is_sac:
            return True, f"{sac_type}: {sac_desc}"
        return False, ""

    def _is_material_sacrifice(
        self,
        board: chess.Board,
        move: chess.Move
    ) -> Tuple[bool, str, str]:
        """
        Comprehensive material sacrifice detection covering:
        1. Greek Gift & King Shelter destruction (Bxh7+, Bxf7+, Bxh6, etc.)
        2. Queen sacrifices
        3. Exchange sacrifices (Rook for Minor/Pawn)
        4. Minor piece sacrifices (Knight / Bishop en prise or capturing into defense)
        5. En Prise counter-attacks (leaving friendly Q, R, B, N or key pawn attacked)
        6. Tactical pawn sacrifices (gambit breaks, deflections, clearance)
        7. Desperado stalemate sacrifices
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

        # Post-move simulated position
        test_board = board.copy()
        test_board.push(move)
        dest_attackers = test_board.attackers(opp, move.to_square)
        dest_defenders = test_board.attackers(turn, move.to_square)

        # ----------------------------------------------------
        # 1. King Shelter Destruction & Greek Gift Sacrifices
        # ----------------------------------------------------
        opp_king = board.king(opp)
        is_near_king = opp_king is not None and chess.square_distance(move.to_square, opp_king) <= 2

        if p_type == chess.BISHOP and captured and captured.piece_type == chess.PAWN:
            if (turn == chess.WHITE and move.to_square == chess.H7 and opp_king in [chess.G8, chess.H8]) or \
               (turn == chess.BLACK and move.to_square == chess.H2 and opp_king in [chess.G1, chess.H1]):
                return True, "Greek Gift Sacrifice", "Sacrifices bishop on h7/h2 shattering king shelter to unleash decisive attack"
            if move.to_square in [chess.F7, chess.F2, chess.H6, chess.H3, chess.G7, chess.G2] and len(dest_attackers) > 0:
                return True, "King Shelter Sacrifice", f"Sacrifices bishop on {chess.square_name(move.to_square)} obliterating king defense"

        if p_type == chess.KNIGHT and captured and captured.piece_type == chess.PAWN:
            if move.to_square in [chess.F7, chess.F2, chess.H7, chess.H2, chess.G7, chess.G2] and len(dest_attackers) > 0:
                return True, "Knight King-Attack Sacrifice", f"Sacrifices knight on {chess.square_name(move.to_square)} opening lines against opponent king"

        # ----------------------------------------------------
        # 2. Queen Sacrifices
        # ----------------------------------------------------
        if p_type == chess.QUEEN and len(dest_attackers) > 0:
            # If captured piece is not a queen (i.e. not a simple queen trade)
            if c_val < 900:
                # Check if opponent can capture Queen with lesser piece or Queen is underdefended
                lowest_att = min(self.PIECE_VALUES[test_board.piece_at(a).piece_type] for a in dest_attackers if test_board.piece_at(a))
                if lowest_att < 900 or len(dest_attackers) > len(dest_defenders):
                    return True, "Queen Sacrifice", f"Sacrifices queen into {chess.square_name(move.to_square)} forcing a decisive tactical breakthrough"

        # ----------------------------------------------------
        # 3. Exchange Sacrifices (Rook for Minor or Pawn)
        # ----------------------------------------------------
        if p_type == chess.ROOK:
            if captured and captured.piece_type in [chess.BISHOP, chess.KNIGHT]:
                if len(dest_attackers) > 0:
                    c_name = self.PIECE_NAMES[captured.piece_type]
                    return True, "Exchange Sacrifice", f"Gives up rook for {c_name} on {chess.square_name(move.to_square)} to seize dominant initiative"
            elif captured and captured.piece_type == chess.PAWN:
                if len(dest_attackers) > 0:
                    return True, "Exchange Sacrifice", f"Sacrifices rook on {chess.square_name(move.to_square)} cracking pawn structure"
            elif not captured and len(dest_attackers) > 0:
                # Rook moved into square attacked by minor/pawn or undefended
                lowest_att = min(self.PIECE_VALUES[test_board.piece_at(a).piece_type] for a in dest_attackers if test_board.piece_at(a))
                if lowest_att < 500 or len(dest_attackers) > len(dest_defenders):
                    return True, "Exchange Sacrifice", f"Offers rook sacrifice on {chess.square_name(move.to_square)} to infiltrate opponent camp"

        # ----------------------------------------------------
        # 4. Minor Piece Sacrifices (Knight or Bishop)
        # ----------------------------------------------------
        if p_type in [chess.KNIGHT, chess.BISHOP]:
            p_name = self.PIECE_NAMES[p_type]
            if captured and p_val > c_val + 150:
                if len(dest_attackers) > 0:
                    return True, f"{p_name.capitalize()} Sacrifice", f"Sacrifices {p_name} taking pawn on {chess.square_name(move.to_square)} tearing open lines"
            elif not captured and len(dest_attackers) > 0:
                # Square attacked by pawn (can be taken by pawn) or undefended/underdefended
                pawn_att = any(test_board.piece_at(a) and test_board.piece_at(a).piece_type == chess.PAWN for a in dest_attackers)
                if pawn_att or len(dest_defenders) == 0 or len(dest_attackers) > len(dest_defenders):
                    return True, f"{p_name.capitalize()} Sacrifice", f"Places {p_name} on {chess.square_name(move.to_square)} en prise to deflect defenders"

        # ----------------------------------------------------
        # 5. En Prise Counter-Attacks (Leaving pieces hanging)
        # ----------------------------------------------------
        # Check if ANY player piece (Queen, Rook, Bishop, Knight, or advanced pawn) is left en prise
        for sq in chess.SQUARES:
            my_p = test_board.piece_at(sq)
            if my_p and my_p.color == turn and sq != move.to_square and my_p.piece_type != chess.KING:
                opp_att = test_board.attackers(opp, sq)
                if not opp_att:
                    continue
                my_def = test_board.attackers(turn, sq)
                p_val_sq = self.PIECE_VALUES[my_p.piece_type]
                lowest_att_val = min(self.PIECE_VALUES[test_board.piece_at(a).piece_type] for a in opp_att if test_board.piece_at(a))

                # Piece is hanging if completely undefended, or attacked by a lesser piece (e.g. minor attacked by pawn)
                if p_val_sq >= 300 and (len(my_def) == 0 or lowest_att_val < p_val_sq):
                    valuable_name = self.PIECE_NAMES[my_p.piece_type]
                    return True, f"Counter-Intuitive {valuable_name.capitalize()} Sacrifice", f"Boldly ignores attack on {valuable_name} to launch lethal counter-strike"

        # ----------------------------------------------------
        # 6. Tactical Pawn Sacrifices (Gambits, Breaks, Clearance)
        # ----------------------------------------------------
        if p_type == chess.PAWN and len(dest_attackers) > 0:
            # Pawn moved into attack undefended or attacked by pawn/minor
            if len(dest_defenders) == 0:
                return True, "Pawn Sacrifice", f"Sacrifices pawn on {chess.square_name(move.to_square)} to crack open lines and seize momentum"
            # Sacrificing a pawn with check or central deflection break
            if test_board.is_check() or move.to_square in [chess.D5, chess.E5, chess.D4, chess.E4, chess.C5, chess.C4, chess.F5, chess.F4]:
                pawn_att = any(test_board.piece_at(a) and test_board.piece_at(a).piece_type == chess.PAWN for a in dest_attackers)
                if pawn_att:
                    return True, "Tactical Pawn Break", f"Offers pawn sacrifice on {chess.square_name(move.to_square)} creating irresistible initiative"

        # ----------------------------------------------------
        # 7. Desperado Stalemate Sacrifice
        # ----------------------------------------------------
        if self._is_stalemate_desperado(board, move):
            return True, "Desperado Stalemate Trick", "Sacrifices piece to force stalemate defense from difficult position"

        return False, "", ""

    def _is_stalemate_desperado(self, board: chess.Board, move: chess.Move) -> bool:
        """Checks if sacrificing the piece forces a stalemate draw."""
        test_board = board.copy()
        test_board.push(move)
        for opp_move in test_board.legal_moves:
            if opp_move.to_square == move.to_square:
                sub_board = test_board.copy()
                sub_board.push(opp_move)
                if sub_board.is_stalemate():
                    return True
        return False
