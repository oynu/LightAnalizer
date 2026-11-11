"""
State-based robust move inference and occupancy-driven board healing.
Validates candidate moves using 64-bit occupancy bitmasks, state transitions,
and ambiguity resolution before confirming live moves.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Set
import numpy as np
import chess

from core.vision.piece_classifier import PieceClassifier
from core.vision.move_inference import MoveInferenceEngine

class Verdict(str, Enum):
    NO_CHANGE = "NO_CHANGE"
    MOVES = "MOVES"
    UNCERTAIN = "UNCERTAIN"

@dataclass
class FrameResult:
    verdict: Verdict
    steps: List[Tuple[chess.Move, chess.Board]] = field(default_factory=list)
    confidence: float = 1.0
    reason: str = ""

class RobustMoveInference(MoveInferenceEngine):
    """
    State-based move inference engine that determines moves by comparing
    observed piece occupancy bitmasks against legal chess state transitions.
    """
    def __init__(self, classifier: Optional[PieceClassifier] = None):
        classifier = classifier or PieceClassifier()
        super().__init__(classifier)
        self.classifier = classifier

    def infer_frame(
        self,
        board: chess.Board,
        prev_crops: Dict[chess.Square, np.ndarray],
        curr_crops: Dict[chess.Square, np.ndarray]
    ) -> FrameResult:
        """
        Determines frame verdict (NO_CHANGE, MOVES, or UNCERTAIN) using state-based inference.

        1. Compute per-square pixel diffs; 'changed' = diff >= max(6.0, 2.5 * median_diff).
        2. If >= 16 squares changed -> UNCERTAIN.
        3. Classify ONLY changed squares. Unchanged squares keep state from known board.
        4. Build 64-bit white and black occupancy masks.
        5. If mismatch vs known board is <= 1 square (and no piece lifted) -> NO_CHANGE.
        6. Otherwise compare every legal move against observed occupancy masks.
        7. Accept only if best mismatch <= 1, best mismatch < mismatch of unchanged board,
           and runner-up (different masks) is worse by >= 2 squares.
        8. If no 1-ply match, repeat with 2-move sequences.
        9. If still none and side to move isn't in check, try again after a null move.
        10. Otherwise return UNCERTAIN.
        """
        if prev_crops is None or curr_crops is None or not prev_crops or not curr_crops:
            return FrameResult(Verdict.UNCERTAIN, reason="Missing square crops")

        # 1. Compute per-square pixel diffs between previous and current frame
        diffs: Dict[chess.Square, float] = {}
        for sq in chess.SQUARES:
            p_crop = prev_crops.get(sq)
            c_crop = curr_crops.get(sq)
            if p_crop is None or c_crop is None or p_crop.size == 0 or c_crop.size == 0:
                diffs[sq] = 0.0
            else:
                diffs[sq] = float(np.mean(np.abs(c_crop.astype(np.float32) - p_crop.astype(np.float32))))

        sorted_diffs = sorted(diffs.values())
        median_diff = float(np.median(sorted_diffs)) if sorted_diffs else 0.0
        eff_threshold = max(6.0, 2.5 * median_diff)
        changed_sqs = {sq for sq, d in diffs.items() if d >= eff_threshold}

        # 2. If >= 16 squares changed -> UNCERTAIN (board obscured / page changed)
        if len(changed_sqs) >= 16:
            return FrameResult(Verdict.UNCERTAIN, reason="Board obscured / page changed (>= 16 squares changed)")

        # 3. Classify ONLY the changed squares. Unchanged squares keep state from known board.
        obs_white = 0
        obs_black = 0
        lifted_piece = False

        for sq in chess.SQUARES:
            if sq in changed_sqs:
                crop = curr_crops.get(sq)
                if crop is not None and crop.size > 0:
                    is_occ, _ = self.classifier.is_square_occupied(crop)
                    if is_occ:
                        color = self.classifier.detect_piece_color(crop)
                        if color == chess.WHITE:
                            obs_white |= (1 << sq)
                        else:
                            obs_black |= (1 << sq)
                    else:
                        # Square is observed empty. If known_board had a piece, piece was lifted
                        if board.piece_at(sq) is not None:
                            lifted_piece = True
                else:
                    if board.piece_at(sq) is not None:
                        lifted_piece = True
            else:
                p = board.piece_at(sq)
                if p is not None:
                    if p.color == chess.WHITE:
                        obs_white |= (1 << sq)
                    else:
                        obs_black |= (1 << sq)

        known_white = board.occupied_co[chess.WHITE]
        known_black = board.occupied_co[chess.BLACK]
        mismatch_known = ((known_white ^ obs_white) | (known_black ^ obs_black)).bit_count()

        # Check for mid-drag: from-square empty, nothing else changed (mismatch == 1)
        if mismatch_known == 1 and lifted_piece:
            return FrameResult(Verdict.UNCERTAIN, reason="Piece in hand (holding piece)")

        # 5. If mismatch vs known board is <= 1 square (and no piece was lifted) -> NO_CHANGE
        if mismatch_known == 0:
            return FrameResult(Verdict.NO_CHANGE, confidence=1.0, reason="Board unchanged (mismatch 0)")
        if mismatch_known == 1 and not lifted_piece:
            return FrameResult(Verdict.NO_CHANGE, confidence=1.0, reason="Board unchanged (single square noise)")

        # Detect highlighted squares (Chess.com / Lichess move highlight tint)
        highlighted_sqs = {
            sq for sq in chess.SQUARES
            if (curr_crops.get(sq) is not None and curr_crops[sq].size > 0 and self.classifier.is_highlighted(curr_crops[sq]))
        }

        # 6 & 7. 1-ply search: push every legal move and evaluate mismatch
        match_1ply = self._find_matching_moves_1ply(
            board, obs_white, obs_black, diffs, mismatch_known, highlighted_sqs=highlighted_sqs
        )
        if match_1ply is not None:
            return match_1ply

        # 8. 2-ply sequence search (fast reply / premove)
        match_2ply = self._find_matching_moves_2ply(
            board, obs_white, obs_black, diffs, mismatch_known, highlighted_sqs=highlighted_sqs
        )
        if match_2ply is not None:
            return match_2ply

        # 9. Null move try (turn bookkeeping correction after mid-game join)
        if not board.is_check():
            b_null = board.copy(stack=False)
            b_null.push(chess.Move.null())
            match_null = self._find_matching_moves_1ply(
                b_null, obs_white, obs_black, diffs, mismatch_known, is_null_resync=True, highlighted_sqs=highlighted_sqs
            )
            if match_null is not None:
                return match_null

        # 10. Otherwise UNCERTAIN
        reason = "Piece in hand (holding / dragging piece)" if lifted_piece else "No legal move matched observed occupancy"
        return FrameResult(Verdict.UNCERTAIN, reason=reason)

    def _find_matching_moves_1ply(
        self,
        board: chess.Board,
        obs_white: int,
        obs_black: int,
        diffs: Dict[chess.Square, float],
        mismatch_known: int,
        is_null_resync: bool = False,
        highlighted_sqs: Optional[Set[chess.Square]] = None
    ) -> Optional[FrameResult]:
        highlighted_sqs = highlighted_sqs or set()
        candidates_by_mask: Dict[Tuple[int, int], List[Tuple[chess.Move, chess.Board, float, bool]]] = {}

        for m in board.legal_moves:
            b_cand = board.copy(stack=False)
            b_cand.push(m)
            mask_pair = (b_cand.occupied_co[chess.WHITE], b_cand.occupied_co[chess.BLACK])
            diff_metric = diffs.get(m.from_square, 0.0) + diffs.get(m.to_square, 0.0)
            hl_match = (len(highlighted_sqs) == 2 and {m.from_square, m.to_square} == highlighted_sqs)
            if hl_match:
                diff_metric += 100.0

            if mask_pair not in candidates_by_mask:
                candidates_by_mask[mask_pair] = []
            candidates_by_mask[mask_pair].append((m, b_cand, diff_metric, hl_match))

        if not candidates_by_mask:
            return None

        distinct_candidates = []
        for (w_mask, b_mask), move_list in candidates_by_mask.items():
            mismatch = ((w_mask ^ obs_white) | (b_mask ^ obs_black)).bit_count()
            # Sort: prefer queen promotion, then diff_metric descending
            move_list.sort(
                key=lambda x: (
                    0 if x[0].promotion in (None, chess.QUEEN) else 1,
                    -x[2]
                )
            )
            best_m, best_b, best_diff, best_hl = move_list[0]
            distinct_candidates.append({
                "mismatch": mismatch,
                "diff": best_diff,
                "move": best_m,
                "board": best_b,
                "highlight_match": best_hl,
                "mask_pair": (w_mask, b_mask)
            })

        distinct_candidates.sort(key=lambda c: (c["mismatch"], -c["diff"]))

        best = distinct_candidates[0]
        best_mismatch = best["mismatch"]
        runner_up_mismatch = distinct_candidates[1]["mismatch"] if len(distinct_candidates) > 1 else 999
        runner_up_diff = distinct_candidates[1]["diff"] if len(distinct_candidates) > 1 else 0.0

        # Condition 7: Accept if mismatch <= 1 and better than unchanged board,
        # with runner-up mismatch >= best + 2 OR decisive pixel diff tie-break OR highlight match
        is_clear_best = False
        if best_mismatch == 0:
            is_clear_best = True
        elif best_mismatch <= 1 and best_mismatch < mismatch_known:
            if best.get("highlight_match"):
                is_clear_best = True
            elif (runner_up_mismatch - best_mismatch) >= 2:
                is_clear_best = True
            elif (runner_up_mismatch - best_mismatch) >= 1 and best["diff"] > runner_up_diff * 1.25:
                is_clear_best = True
            elif len(distinct_candidates) == 1:
                is_clear_best = True

        if is_clear_best:
            conf = 1.0 if (best_mismatch == 0 or best.get("highlight_match")) else 0.90
            reason = f"1-ply legal move {best['move'].uci()} (mismatch={best_mismatch})"
            if best.get("highlight_match"):
                reason += " [highlight match]"
            if is_null_resync:
                reason = f"Turn-corrected move {best['move'].uci()}"
            return FrameResult(
                Verdict.MOVES,
                steps=[(best["move"], best["board"])],
                confidence=conf,
                reason=reason
            )

        return None

    def _find_matching_moves_2ply(
        self,
        board: chess.Board,
        obs_white: int,
        obs_black: int,
        diffs: Dict[chess.Square, float],
        mismatch_known: int,
        highlighted_sqs: Optional[Set[chess.Square]] = None
    ) -> Optional[FrameResult]:
        highlighted_sqs = highlighted_sqs or set()
        candidates_by_mask: Dict[Tuple[int, int], List[Tuple[chess.Move, chess.Board, chess.Move, chess.Board, float, bool]]] = {}

        for m1 in board.legal_moves:
            b1 = board.copy(stack=False)
            b1.push(m1)
            for m2 in b1.legal_moves:
                b2 = b1.copy(stack=False)
                b2.push(m2)
                mask_pair = (b2.occupied_co[chess.WHITE], b2.occupied_co[chess.BLACK])
                sqs = {m1.from_square, m1.to_square, m2.from_square, m2.to_square}
                diff_sum = sum(diffs.get(sq, 0.0) for sq in sqs)
                hl_match = (len(highlighted_sqs) == 2 and {m2.from_square, m2.to_square} == highlighted_sqs)
                if hl_match:
                    diff_sum += 100.0

                if mask_pair not in candidates_by_mask:
                    candidates_by_mask[mask_pair] = []
                candidates_by_mask[mask_pair].append((m1, b1, m2, b2, diff_sum, hl_match))

        if not candidates_by_mask:
            return None

        distinct_candidates = []
        for (w_mask, b_mask), seq_list in candidates_by_mask.items():
            mismatch = ((w_mask ^ obs_white) | (b_mask ^ obs_black)).bit_count()
            # Prefer queen promotion, then diff_sum descending
            seq_list.sort(
                key=lambda x: (
                    0 if (x[0].promotion in (None, chess.QUEEN) and x[2].promotion in (None, chess.QUEEN)) else 1,
                    -x[4]
                )
            )
            m1, b1, m2, b2, diff_sum, hl_match = seq_list[0]
            distinct_candidates.append({
                "mismatch": mismatch,
                "diff": diff_sum,
                "m1": m1, "b1": b1,
                "m2": m2, "b2": b2,
                "highlight_match": hl_match,
                "mask_pair": (w_mask, b_mask)
            })

        distinct_candidates.sort(key=lambda c: (c["mismatch"], -c["diff"]))

        best = distinct_candidates[0]
        best_mismatch = best["mismatch"]
        runner_up_mismatch = distinct_candidates[1]["mismatch"] if len(distinct_candidates) > 1 else 999
        runner_up_diff = distinct_candidates[1]["diff"] if len(distinct_candidates) > 1 else 0.0

        is_clear_best = False
        if best_mismatch == 0:
            is_clear_best = True
        elif best_mismatch <= 1 and best_mismatch < mismatch_known:
            if best.get("highlight_match"):
                is_clear_best = True
            elif (runner_up_mismatch - best_mismatch) >= 2:
                is_clear_best = True
            elif (runner_up_mismatch - best_mismatch) >= 1 and best["diff"] > runner_up_diff * 1.25:
                is_clear_best = True
            elif len(distinct_candidates) == 1:
                is_clear_best = True

        if is_clear_best:
            conf = 1.0 if (best_mismatch == 0 or best.get("highlight_match")) else 0.85
            reason = f"2-ply sequence {best['m1'].uci()} {best['m2'].uci()} (mismatch={best_mismatch})"
            if best.get("highlight_match"):
                reason += " [highlight match]"
            return FrameResult(
                Verdict.MOVES,
                steps=[(best["m1"], best["b1"]), (best["m2"], best["b2"])],
                confidence=conf,
                reason=reason
            )

        return None

    def heal_position(
        self,
        known_board: chess.Board,
        curr_crops: Dict[chess.Square, np.ndarray],
        continuous_uncertain_seconds: float = 0.0
    ) -> Tuple[Optional[chess.Board], float, str]:
        """
        D) Resync / healing:
        1. Only accept a position REACHABLE from known_board within <= 3 plies
           (beam search, beam width ~25, also try null-move-flipped start),
           matching observed masks within 1 square.
        2. Then try the starting position.
        3. Then opening-book occupancy match (exact).
        4. Only after >= 4 seconds of continuous uncertainty fall back to reconstruct_full_board
           with confidence >= 0.75.
        Never resync to 'similar-looking' old boards.
        """
        obs_white = 0
        obs_black = 0
        for sq in chess.SQUARES:
            crop = curr_crops.get(sq)
            if crop is not None and crop.size > 0:
                is_occ, _ = self.classifier.is_square_occupied(crop)
                if is_occ:
                    col = self.classifier.detect_piece_color(crop)
                    if col == chess.WHITE:
                        obs_white |= (1 << sq)
                    else:
                        obs_black |= (1 << sq)

        # 1. Reachable from known_board within <= 3 plies
        if known_board is not None:
            roots = [known_board.copy(stack=False)]
            if not known_board.is_check():
                b_null = known_board.copy(stack=False)
                b_null.push(chess.Move.null())
                roots.append(b_null)

            beam = roots
            beam_width = 25
            for ply in range(1, 4):
                next_beam = []
                for parent in beam:
                    for move in parent.legal_moves:
                        child = parent.copy(stack=False)
                        child.push(move)
                        mismatch = ((child.occupied_co[chess.WHITE] ^ obs_white) |
                                    (child.occupied_co[chess.BLACK] ^ obs_black)).bit_count()
                        if mismatch <= 1:
                            return child, 0.95, f"Reachable within {ply} plies"
                        next_beam.append((mismatch, child))

                if not next_beam:
                    break
                next_beam.sort(key=lambda x: x[0])
                beam = [b for _, b in next_beam[:beam_width]]

        # 2. Starting position
        start_board = chess.Board()
        start_mismatch = ((start_board.occupied_co[chess.WHITE] ^ obs_white) |
                          (start_board.occupied_co[chess.BLACK] ^ obs_black)).bit_count()
        if start_mismatch <= 1 or self._is_standard_starting_position(curr_crops):
            return start_board, 0.98, "Starting position match"

        # 3. Opening-book occupancy match (EXACT)
        if hasattr(self, "_opening_tree"):
            for tree_b in self._opening_tree.values():
                if (tree_b.occupied_co[chess.WHITE] == obs_white and
                    tree_b.occupied_co[chess.BLACK] == obs_black):
                    return tree_b.copy(), 0.95, "Opening book exact match"

        # 4. Fallback: only after >= 4 seconds of continuous uncertainty
        if continuous_uncertain_seconds >= 4.0:
            rec_b, rec_conf = self.reconstruct_full_board(curr_crops)
            if rec_b is not None and rec_conf >= 0.75:
                return rec_b, rec_conf, "Full board reconstruction fallback"

        return None, 0.0, "No valid resync position"
