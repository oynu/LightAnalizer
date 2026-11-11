"""
Brilliant Farmer: Engine-backed detection, discovery, and farming of Brilliant Moves (!!).
Identifies high-impact material sacrifices that lead to favorable positions, king shelter
destruction, en prise counter-attacks, Greek Gift sacrifices, gambit breaks, rook sacrifices
and stalemate traps.

Pipeline (brilliant mode):
  1. EngineManager runs a wide MultiPV search, then PROBES sacrifice-shaped root moves
     (see `probe_moves`) so sacrifices that fall outside the top lines still get an engine score.
  2. `process_candidates` verifies each sacrifice by replaying the engine PV and measuring the
     real material deficit once the position is quiet, checks the engine score is still sound
     (best / near-best / not already completely winning) and promotes the best one to Rank 1.
"""
from __future__ import annotations
from typing import List, Optional, Tuple, Dict, Set
import chess
from core.types import CandidateMove
from core.gambits import GambitsAndTraps

class BrilliantFarmer:
    """
    Identifies, prioritizes, and farms Brilliant Moves (!!) according to competitive standards:
    1. Material sacrifice: Gives up Queen, Rook, Minor piece, or key Pawn, or leaves a piece en prise.
    2. Favorable or winning outcome: Retains solid advantage or positive eval (within reasonable delta).
    3. Non-obvious tactical initiative: King attacks, deflections, line clearances, or counter-blows.
    4. Not already overwhelmingly trivial (e.g. not +7 where any move still wins).
    """

    # Position is "already completely winning" above this engine score (centipawns).
    CRUSHING_CP = 700
    # Net material deficit (centipawns) at the end of the verified PV that counts as a real sacrifice.
    PV_SAC_STRONG = -150
    PV_SAC_LIGHT = -100

    def __init__(self):
        self.gambits = GambitsAndTraps()

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

    # ------------------------------------------------------------------
    # Evaluation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _eval_cp(c: CandidateMove) -> int:
        """Unified centipawn value of a candidate from the mover's perspective (mates mapped to +/-10000)."""
        if c.mate_in is not None:
            return (10000 - abs(c.mate_in)) if c.mate_in > 0 else (-10000 + abs(c.mate_in))
        return c.score_cp if c.score_cp is not None else 0

    def _material_balance(self, board: chess.Board, color: chess.Color) -> int:
        total = 0
        for pt, val in self.PIECE_VALUES.items():
            if pt == chess.KING:
                continue
            total += val * len(board.pieces(pt, color))
            total -= val * len(board.pieces(pt, not color))
        return total

    def pv_material_delta(self, board: chess.Board, pv: List[chess.Move]) -> Optional[int]:
        """
        Replays the engine PV and returns the mover's net material change (centipawns) at the last
        QUIET position of the line (no capture / check just played). A strongly negative value means
        the first move starts a genuine material sacrifice that is not regained inside the PV.
        Returns None if the PV is unusable / too short to judge.
        """
        if not pv or len(pv) < 3:
            return None
        mover = board.turn
        b = board.copy()
        base = self._material_balance(b, mover)
        snapshots: List[Tuple[bool, int]] = []
        for m in pv[:10]:
            if m not in b.legal_moves:
                break
            was_capture = b.is_capture(m)
            b.push(m)
            quiet = (not was_capture) and (not b.is_check())
            snapshots.append((quiet, self._material_balance(b, mover)))
        if len(snapshots) < 3:
            return None
        for quiet, bal in reversed(snapshots):
            if quiet:
                return bal - base
        return snapshots[-1][1] - base

    def is_greek_gift_setup(self, board: chess.Board, move: chess.Move) -> bool:
        """Strict Greek Gift pattern: Bxh7+/Bxh2+ with knight + queen ready to follow up."""
        piece = board.piece_at(move.from_square)
        if not piece or piece.piece_type != chess.BISHOP:
            return False
        turn = board.turn
        if turn == chess.WHITE:
            target, kings, follow_knight, defend_knight = chess.H7, (chess.G8, chess.H8), (chess.F3, chess.G5), chess.F6
        else:
            target, kings, follow_knight, defend_knight = chess.H2, (chess.G1, chess.H1), (chess.F6, chess.G4), chess.F3
        if move.to_square != target:
            return False
        victim = board.piece_at(target)
        if not victim or victim.piece_type != chess.PAWN or victim.color == turn:
            return False
        if board.king(not turn) not in kings:
            return False
        my_knight = chess.Piece(chess.KNIGHT, turn)
        if not any(board.piece_at(s) == my_knight for s in follow_knight):
            return False
        if board.piece_at(defend_knight) == chess.Piece(chess.KNIGHT, not turn):
            return False
        return len(board.pieces(chess.QUEEN, turn)) > 0

    # ------------------------------------------------------------------
    # Probing: which sacrifice-shaped root moves should the engine evaluate?
    # ------------------------------------------------------------------
    def _probe_priority(self, board: chess.Board, move: chess.Move) -> int:
        if self.is_greek_gift_setup(board, move):
            return 100
        try:
            if self._is_stalemate_desperado(board, move):
                return 90
            is_sac, sac_type, _ = self._is_material_sacrifice(board, move)
        except Exception:
            return 0
        if not is_sac or sac_type.startswith("Counter-Intuitive"):
            return 0
        if "Queen" in sac_type:
            return 80
        if "King" in sac_type:
            return 75
        if "Exchange" in sac_type:
            return 70
        if "Bishop" in sac_type or "Knight" in sac_type:
            return 60
        if sac_type == "Pawn Sacrifice":
            return 40
        return 30

    def probe_moves(self, board: chess.Board, known: List[chess.Move], limit: int = 6) -> List[chess.Move]:
        """Returns up to `limit` sacrifice-shaped legal moves not already evaluated by MultiPV."""
        scored: List[Tuple[int, chess.Move]] = []
        for m in board.legal_moves:
            if m in known:
                continue
            pri = self._probe_priority(board, m)
            if pri > 0:
                scored.append((pri, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    # ------------------------------------------------------------------
    # Candidate processing
    # ------------------------------------------------------------------
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

        best_cand = max(candidates, key=self._eval_cp)

        # Check known aggressive opening gambits and tactical traps
        gambit_hit = self.gambits.find_gambit_or_trap(board)
        if gambit_hit:
            g_move, g_name, g_sac_type, g_idea = gambit_hit
            try:
                g_san = board.san(g_move)
            except Exception:
                g_san = g_move.uci()

            found_cand = None
            for c in candidates:
                if c.move == g_move:
                    found_cand = c
                    break

            # Never push a gambit that the engine considers clearly losing (> 1.3 pawns worse than best)
            gambit_ok = True
            if found_cand is not None and (self._eval_cp(best_cand) - self._eval_cp(found_cand)) > 130:
                gambit_ok = False

            if gambit_ok and found_cand:
                found_cand.is_brilliant = True
                found_cand.brilliant_reason = f"{g_name} ({g_sac_type}): {g_idea}"
                found_cand.rank = 1
                found_cand.is_best = True
                reordered = [found_cand] + [c for c in candidates if c.move != g_move]
                for idx, c in enumerate(reordered[:3]):
                    c.rank = idx + 1
                    c.is_best = (idx == 0)
                return reordered
            elif gambit_ok:
                new_c = CandidateMove(
                    move=g_move,
                    san=g_san,
                    rank=1,
                    score_cp=35,
                    eval_str="+0.35",
                    eval_diff=0.0,
                    short_explanation=f"Aggressive Opening Gambit: {g_name}",
                    strategic_idea=g_idea,
                    is_best=True,
                    is_brilliant=True,
                    brilliant_reason=f"{g_name} ({g_sac_type}): {g_idea}"
                )
                reordered = [new_c] + list(candidates)
                for idx, c in enumerate(reordered[:3]):
                    c.rank = idx + 1
                    c.is_best = (idx == 0)
                return reordered

        processed: List[CandidateMove] = []
        brilliant_cands: List[Tuple[CandidateMove, str, int]] = []

        for cand in candidates:
            is_brill, reason = self.evaluate_move_brilliance(board, cand, best_cand)
            if is_brill:
                cand.is_brilliant = True
                cand.brilliant_reason = reason
                brilliant_cands.append((cand, reason, self._farm_priority(board, cand, reason)))
            else:
                cand.is_brilliant = False
                cand.brilliant_reason = ""
            processed.append(cand)

        # If one or more brilliant moves are discovered, promote the best brilliant move to Rank 1
        if brilliant_cands:
            brilliant_cands.sort(key=lambda x: (x[2], self._eval_cp(x[0])), reverse=True)
            top_brilliant = brilliant_cands[0][0]
            others_brill = [b[0] for b in brilliant_cands[1:]]

            # Re-order: top brilliant first, then other brilliants, then the remaining engine lines
            reordered = [top_brilliant] + others_brill
            for c in processed:
                if c.move != top_brilliant.move and c not in others_brill:
                    reordered.append(c)

            for idx, c in enumerate(reordered[:3]):
                c.rank = idx + 1
                c.is_best = (idx == 0)

            return reordered

        return processed

    def _farm_priority(self, board: chess.Board, cand: CandidateMove, reason: str) -> int:
        """Ranking among several brilliant candidates (higher = farm it first)."""
        pri = 0
        if "Greek Gift" in reason:
            pri += 60
        if reason.startswith("Verified"):
            pri += 40
        for key, val in (("Queen", 35), ("Rook", 30), ("Exchange", 25), ("Stalemate", 20),
                         ("Bishop", 18), ("Knight", 18), ("King", 22), ("Pawn", 8)):
            if key in reason:
                pri += val
                break
        if cand.mate_in is not None and cand.mate_in > 0:
            pri += 30
        return pri

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
        if move not in board.legal_moves:
            return False, ""

        score = cand.score_cp if cand.score_cp is not None else 0
        mate = cand.mate_in
        best_val = self._eval_cp(best_cand)
        cand_val = self._eval_cp(cand)
        diff = (cand_val - best_val) / 100.0

        # 1. Competitive Context: never inside a completely won / crushing position
        if mate is None and score > 1200:
            return False, ""
        if best_cand.mate_in is None and best_cand.score_cp is not None and best_cand.score_cp > self.CRUSHING_CP:
            return False, ""

        # 2. Favorable / Sound Outcome: never sacrifice into a forced mate
        if mate is not None and mate < 0:
            return False, ""

        losing_before = best_val <= -150
        winning_before = best_val >= 150
        tolerance = 0.30 if winning_before else (0.60 if best_val >= -50 else 0.90)
        floor = (best_val - 50) if losing_before else -100

        sound = (
            cand is best_cand
            or cand.is_best
            or (mate is not None and mate > 0)
            or (diff >= -tolerance and cand_val >= floor)
        )

        stalemate_trick = False
        if losing_before or not sound:
            if self._is_stalemate_desperado(board, move) and (mate is None) and score >= -60:
                stalemate_trick = True
        if not sound and not stalemate_trick:
            return False, ""

        # 3. Verify the sacrifice against the engine's principal variation when available
        pv_delta = self.pv_material_delta(board, cand.pv) if cand.pv else None
        is_sac, sac_type, sac_desc = self._is_material_sacrifice(board, move)

        if stalemate_trick:
            return True, "Verified Stalemate Trap: Sacrifices material so that capturing leads to stalemate and saves the game"

        greek = self.is_greek_gift_setup(board, move)

        if pv_delta is not None:
            if pv_delta <= self.PV_SAC_STRONG:
                label = sac_type if is_sac and not sac_type.startswith("Counter-Intuitive") else self._generic_sac_label(board, move)
                desc = sac_desc if is_sac and not sac_type.startswith("Counter-Intuitive") else (
                    f"Engine line gives up about {abs(pv_delta) / 100:.1f} pawns of material for a decisive initiative")
                if greek:
                    label, desc = "Greek Gift Sacrifice", "Bishop sacrifice on h7/h2 exposes the king; Ng5+ and Qh5 follow with a crushing attack"
                return True, f"Verified {label}: {desc}"
            if pv_delta <= self.PV_SAC_LIGHT and is_sac and not sac_type.startswith("Counter-Intuitive"):
                return True, f"{sac_type}: {sac_desc}"
            if greek and pv_delta <= 0:
                return True, "Greek Gift Sacrifice: Bishop sacrifice on h7/h2 exposes the king; Ng5+ and Qh5 follow"
            # PV shows material is regained: an exchange, not a sacrifice
            return False, ""

        # No usable PV: fall back to the static sacrifice heuristics
        if not is_sac:
            return False, ""
        return True, f"{sac_type}: {sac_desc}"

    def _generic_sac_label(self, board: chess.Board, move: chess.Move) -> str:
        piece = board.piece_at(move.from_square)
        if not piece:
            return "Material Sacrifice"
        return f"{self.PIECE_NAMES[piece.piece_type].capitalize()} Sacrifice"

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
