"""
Position analysis, tactical motif detection, and natural language chess explanations.
Grounds all statements in concrete board evaluations and engine variations.
"""
from __future__ import annotations
from typing import List, Dict, Optional, Tuple, Set
import chess
from core.types import CandidateMove, PositionSummary

class ChessAnalyzer:
    """
    Evaluates tactical motifs, positional factors, king safety, and material balance.
    Generates truthful, non-hallucinatory chess explanations.
    """
    PIECE_VALUES = {
        chess.PAWN: 100,
        chess.KNIGHT: 320,
        chess.BISHOP: 330,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 0
    }

    PIECE_NAMES = {
        chess.PAWN: "pawn",
        chess.KNIGHT: "knight",
        chess.BISHOP: "bishop",
        chess.ROOK: "rook",
        chess.QUEEN: "queen",
        chess.KING: "king"
    }

    def analyze_position(
        self,
        board: chess.Board,
        candidates: List[CandidateMove]
    ) -> PositionSummary:
        """
        Creates a comprehensive, compact summary of the current position.
        """
        turn = board.turn
        opponent = not turn
        
        # 1. Material balance
        white_mat, black_mat = self._compute_material(board)
        diff = white_mat - black_mat
        if diff == 0:
            mat_str = "Equal material"
        elif diff > 0:
            mat_str = f"White is up +{diff/100:.1f} in material"
        else:
            mat_str = f"Black is up +{(-diff)/100:.1f} in material"

        # 2. King safety
        white_ks = self._evaluate_king_safety(board, chess.WHITE)
        black_ks = self._evaluate_king_safety(board, chess.BLACK)

        # 3. Tactical threats & hanging pieces for both sides
        current_threats = self._find_hanging_and_threatened_pieces(board, turn)
        opp_threats = self._find_hanging_and_threatened_pieces(board, opponent)

        # 4. Positional factors
        pos_factors = self._evaluate_positional_factors(board, turn)

        # 5. Objectives & Natural inaccuracy warnings
        objective = self._determine_main_objective(board, turn, diff)
        warning = self._check_natural_inaccuracies(board, candidates)

        # 6. Coach takeaway
        coach_takeaway = self._generate_coach_takeaway(board, candidates, objective)

        # Populate explanations for each candidate move
        self._enrich_candidate_explanations(board, candidates)

        return PositionSummary(
            fen=board.fen(),
            turn=turn,
            material_balance_cp=diff,
            material_str=mat_str,
            king_safety_white=white_ks,
            king_safety_black=black_ks,
            tactical_threats=current_threats,
            positional_factors=pos_factors,
            opponent_threats=opp_threats,
            main_objective=objective,
            natural_inaccuracy_warning=warning,
            coach_takeaway=coach_takeaway,
            is_check=board.is_check(),
            is_checkmate=board.is_checkmate(),
            is_stalemate=board.is_stalemate()
        )

    def _compute_material(self, board: chess.Board) -> Tuple[int, int]:
        white_val = 0
        black_val = 0
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece:
                val = self.PIECE_VALUES[piece.piece_type]
                if piece.color == chess.WHITE:
                    white_val += val
                else:
                    black_val += val
        return white_val, black_val

    def _evaluate_king_safety(self, board: chess.Board, color: chess.Color) -> str:
        king_sq = board.king(color)
        if king_sq is None:
            return "No king"

        king_file = chess.square_file(king_sq)
        king_rank = chess.square_rank(king_sq)
        
        # Check pawn shield if king is on castled flank
        shield_intact = True
        if (color == chess.WHITE and king_rank <= 1) or (color == chess.BLACK and king_rank >= 6):
            target_rank = king_rank + (1 if color == chess.WHITE else -1)
            for f in range(max(0, king_file - 1), min(8, king_file + 2)):
                sq = chess.square(f, target_rank)
                p = board.piece_at(sq)
                if not (p and p.piece_type == chess.PAWN and p.color == color):
                    shield_intact = False
                    break

        # Check open files near king
        enemy_attackers = len(board.attackers(not color, king_sq))
        if board.is_check() and board.turn == color:
            return "In check! Immediate defense required."
        if enemy_attackers > 0:
            return "Vulnerable: direct enemy piece lines pointing to king."
        if not shield_intact and ((color == chess.WHITE and king_rank <= 2) or (color == chess.BLACK and king_rank >= 5)):
            return "Partially exposed: pawn shield disrupted."
        return "Secure and defended."

    def _find_hanging_and_threatened_pieces(self, board: chess.Board, defending_color: chess.Color) -> List[str]:
        threats = []
        attacking_color = not defending_color

        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.color == defending_color and piece.piece_type != chess.KING:
                attackers = board.attackers(attacking_color, sq)
                defenders = board.attackers(defending_color, sq)
                
                if attackers:
                    p_name = self.PIECE_NAMES[piece.piece_type]
                    sq_name = chess.square_name(sq)
                    if not defenders:
                        threats.append(f"Hanging {p_name} on {sq_name} (completely undefended).")
                    elif len(attackers) > len(defenders):
                        threats.append(f"Under-defended {p_name} on {sq_name} ({len(attackers)} attackers vs {len(defenders)} defenders).")
                    else:
                        # Check lowest attacker vs piece value
                        cheapest_attacker_val = min(self.PIECE_VALUES[board.piece_at(a).piece_type] for a in attackers if board.piece_at(a))
                        if cheapest_attacker_val < self.PIECE_VALUES[piece.piece_type]:
                            threats.append(f"{p_name.capitalize()} on {sq_name} threatened by cheaper piece.")

        return threats[:4]

    def _evaluate_positional_factors(self, board: chess.Board, turn: chess.Color) -> List[str]:
        factors = []
        # Center control (e4, d4, e5, d5)
        center_sqs = [chess.E4, chess.D4, chess.E5, chess.D5]
        friendly_ctrl = sum(len(board.attackers(turn, s)) for s in center_sqs)
        enemy_ctrl = sum(len(board.attackers(not turn, s)) for s in center_sqs)

        if friendly_ctrl > enemy_ctrl + 2:
            factors.append("Dominant central control (+2 over opponent).")
        elif enemy_ctrl > friendly_ctrl + 2:
            factors.append("Opponent exerts heavy pressure in the center.")

        # Open files for rooks
        for f in range(8):
            has_pawns = False
            for r in range(8):
                p = board.piece_at(chess.square(f, r))
                if p and p.piece_type == chess.PAWN:
                    has_pawns = True
                    break
            if not has_pawns:
                file_name = chr(ord('a') + f)
                # Check who has rook on this file
                rooks = [s for s in chess.SQUARES if chess.square_file(s) == f and board.piece_at(s) and board.piece_at(s).piece_type == chess.ROOK]
                if rooks:
                    owner = "White" if board.piece_at(rooks[0]).color == chess.WHITE else "Black"
                    factors.append(f"Open {file_name}-file occupied by {owner} rook.")

        # Outposts for knights
        for sq in chess.SQUARES:
            p = board.piece_at(sq)
            if p and p.piece_type == chess.KNIGHT and p.color == turn:
                rank = chess.square_rank(sq)
                if (turn == chess.WHITE and rank in [3, 4, 5]) or (turn == chess.BLACK and rank in [2, 3, 4]):
                    # Check pawn support
                    defenders = board.attackers(turn, sq)
                    has_pawn_support = any(board.piece_at(d) and board.piece_at(d).piece_type == chess.PAWN for d in defenders)
                    if has_pawn_support:
                        factors.append(f"Active outpost knight established on {chess.square_name(sq)}.")
                        break

        # Passed pawns
        for sq in chess.SQUARES:
            p = board.piece_at(sq)
            if p and p.piece_type == chess.PAWN and p.color == turn:
                if self._is_passed_pawn(board, sq, turn):
                    factors.append(f"Passed pawn advancing on {chess.square_name(sq)}.")
                    break

        if not factors:
            factors.append("Balanced piece coordination and standard structure.")

        return factors

    def _is_passed_pawn(self, board: chess.Board, sq: chess.Square, color: chess.Color) -> bool:
        f = chess.square_file(sq)
        r = chess.square_rank(sq)
        direction = 1 if color == chess.WHITE else -1
        enemy_color = not color

        # Check front and adjacent files ahead
        start_rank = r + direction
        end_rank = 8 if color == chess.WHITE else -1
        step = direction

        for test_f in range(max(0, f - 1), min(8, f + 2)):
            for test_r in range(start_rank, end_rank, step):
                test_sq = chess.square(test_f, test_r)
                p = board.piece_at(test_sq)
                if p and p.piece_type == chess.PAWN and p.color == enemy_color:
                    return False
        return True

    def _determine_main_objective(self, board: chess.Board, turn: chess.Color, mat_diff: int) -> str:
        # Check if endgame
        queens = [sq for sq in chess.SQUARES if board.piece_at(sq) and board.piece_at(sq).piece_type == chess.QUEEN]
        is_endgame = len(queens) == 0 or len(board.piece_map()) <= 10

        if is_endgame:
            if (turn == chess.WHITE and mat_diff > 150) or (turn == chess.BLACK and mat_diff < -150):
                return "Convert material superiority: activate king and push passed pawns."
            elif (turn == chess.WHITE and mat_diff < -150) or (turn == chess.BLACK and mat_diff > 150):
                return "Defensive blockade: liquidate dangerous pawns and seek fortress/stalemate."
            return "Active king placement and battle for key breakthrough squares."

        # Opening/Middlegame
        if board.fullmove_number <= 10:
            return "Complete minor piece development, secure king safety, and contest the center."

        return "Coordinate pieces against enemy pawn weaknesses and create tactical breakthrough."

    def _check_natural_inaccuracies(self, board: chess.Board, candidates: List[CandidateMove]) -> Optional[str]:
        if len(candidates) < 2:
            return None
        
        best = candidates[0]
        second = candidates[1]

        # If significant evaluation gap
        if second.eval_diff and abs(second.eval_diff) >= 0.8:
            return f"Caution: '{second.san}' is a tempting alternative, but drops {abs(second.eval_diff):.2f} pawns compared to '{best.san}' due to subtle tactical refutation."
        return None

    def _generate_coach_takeaway(
        self,
        board: chess.Board,
        candidates: List[CandidateMove],
        objective: str
    ) -> str:
        if not candidates:
            if board.is_checkmate():
                return "Checkmate on the board! Game is concluded."
            if board.is_stalemate():
                return "Stalemate. Drawn game."
            return "No legal moves remaining."

        best = candidates[0]
        eval_txt = best.eval_str
        
        if best.mate_in:
            return f"Forced checkmate in {abs(best.mate_in)}: play {best.san} to maintain the mating net."
        
        # Grounded coach takeaway
        if best.tactical_motifs:
            motifs_str = ", ".join(best.tactical_motifs)
            return f"Play {best.san} ({eval_txt}) to exploit tactical theme: {motifs_str}."
        
        if board.is_capture(best.move):
            return f"Play {best.san} ({eval_txt}) winning material or initiating favorable trades."
        
        return f"Best plan: {best.san} ({eval_txt}). Follows priority: {objective}."

    def _enrich_candidate_explanations(
        self,
        board: chess.Board,
        candidates: List[CandidateMove]
    ) -> None:
        best_cand = candidates[0] if candidates else None

        for cand in candidates:
            # 1. Detect tactical motifs executed by this move
            motifs = self._detect_move_tactics(board, cand.move)
            cand.tactical_motifs = motifs

            # 2. Formulate strategic idea
            idea = self._generate_strategic_idea(board, cand.move, motifs)
            cand.strategic_idea = idea

            # 3. Formulate short explanation
            if cand.is_best:
                if cand.mate_in:
                    cand.short_explanation = f"Forces mate in {abs(cand.mate_in)} with unstoppable king attack."
                elif motifs:
                    cand.short_explanation = f"Top engine choice ({cand.eval_str}): executes {', '.join(motifs)}."
                elif board.is_capture(cand.move):
                    captured = board.piece_at(cand.move.to_square)
                    cap_name = self.PIECE_NAMES[captured.piece_type] if captured else "piece"
                    cand.short_explanation = f"Top engine choice ({cand.eval_str}): captures {cap_name} on {chess.square_name(cand.move.to_square)}."
                else:
                    cand.short_explanation = f"Top engine choice ({cand.eval_str}): optimal development and control."
            else:
                diff = abs(cand.eval_diff or 0.0)
                if diff >= 1.0:
                    cand.short_explanation = f"Significantly weaker ({cand.eval_diff:+.2f}): concedes initiative or misses tactical advantage."
                elif diff >= 0.4:
                    cand.short_explanation = f"Playable alternative ({cand.eval_diff:+.2f}): viable practical choice, though slightly less precise."
                else:
                    cand.short_explanation = f"Solid alternative ({cand.eval_diff:+.2f}): nearly equal engine evaluation to the main line."

            # 4. Risks and likely opponent responses
            cand.risks_and_responses = self._determine_risks_and_responses(board, cand)

    def _detect_move_tactics(self, board: chess.Board, move: chess.Move) -> List[str]:
        motifs = []
        piece = board.piece_at(move.from_square)
        if not piece:
            return motifs

        turn = board.turn
        opp = not turn

        # Test position after move
        test_board = board.copy()
        test_board.push(move)

        # A. Check or mate
        if test_board.is_checkmate():
            motifs.append("checkmate")
            return motifs
        elif test_board.is_check():
            motifs.append("check")

        # B. Fork detection: piece attacks 2 or more valuable enemy pieces
        attacks = test_board.attacks(move.to_square)
        valuable_targets = []
        for sq in attacks:
            target = test_board.piece_at(sq)
            if target and target.color == opp and (target.piece_type != chess.PAWN or piece.piece_type == chess.PAWN):
                valuable_targets.append(self.PIECE_NAMES[target.piece_type])
        if len(valuable_targets) >= 2:
            motifs.append(f"fork on {' and '.join(valuable_targets[:2])}")

        # C. Discovered attack: piece moves uncovering line of a sliding piece
        from_sq = move.from_square
        for sq in chess.SQUARES:
            slider = test_board.piece_at(sq)
            if slider and slider.color == turn and slider.piece_type in [chess.BISHOP, chess.ROOK, chess.QUEEN]:
                if from_sq in test_board.attacks(sq):
                    # Check if slider now attacks enemy king or queen
                    enemy_king = test_board.king(opp)
                    if enemy_king and enemy_king in test_board.attacks(sq):
                        motifs.append("discovered check")
                        break
                    for e_sq in test_board.attacks(sq):
                        e_p = test_board.piece_at(e_sq)
                        if e_p and e_p.color == opp and e_p.piece_type in [chess.QUEEN, chess.ROOK]:
                            motifs.append(f"discovered attack on {self.PIECE_NAMES[e_p.piece_type]}")
                            break

        # D. Pin detection: piece pins enemy piece to king or queen
        for target_sq in chess.SQUARES:
            target_piece = test_board.piece_at(target_sq)
            if target_piece and target_piece.color == opp:
                if test_board.is_pinned(opp, target_sq):
                    motifs.append(f"absolute pin against {self.PIECE_NAMES[target_piece.piece_type]}")
                    break

        return motifs

    def _generate_strategic_idea(self, board: chess.Board, move: chess.Move, motifs: List[str]) -> str:
        piece = board.piece_at(move.from_square)
        if not piece:
            return "Active move"

        p_name = self.PIECE_NAMES[piece.piece_type].capitalize()
        to_sq = chess.square_name(move.to_square)

        if motifs:
            return f"Tactical strike: {', '.join(motifs)}."

        if move.promotion:
            return f"Pawn promotion to {self.PIECE_NAMES[move.promotion]} on {to_sq}."

        if board.is_castling(move):
            return "Castles king into safety and connects the rooks."

        if piece.piece_type == chess.PAWN:
            if move.to_square in [chess.E4, chess.D4, chess.E5, chess.D5]:
                return f"Stakes central space claim with {to_sq}."
            return f"Pawn advance to {to_sq} reinforcing structural control."

        if piece.piece_type == chess.KNIGHT:
            return f"Reposition knight to active square {to_sq}."

        if piece.piece_type == chess.BISHOP:
            return f"Develop bishop along diagonal controlling {to_sq}."

        if piece.piece_type == chess.ROOK:
            return f"Activate rook to {to_sq} contesting file."

        if piece.piece_type == chess.QUEEN:
            return f"Centralize queen on {to_sq} with wide board vision."

        return f"Move {p_name} to {to_sq}."

    def _determine_risks_and_responses(self, board: chess.Board, cand: CandidateMove) -> str:
        if not cand.pv or len(cand.pv) < 2:
            return "Opponent will react according to best defensive resources."

        # Expected opponent reply is PV[1]
        test_board = board.copy()
        test_board.push(cand.move)
        reply = cand.pv[1]
        try:
            reply_san = test_board.san(reply)
            return f"Likely opponent response is {reply_san} to challenge the position."
        except Exception:
            return "Opponent will seek defensive consolidation."
