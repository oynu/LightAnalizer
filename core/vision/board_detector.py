"""
Robust chessboard localization, 8x8 grid detection, and orientation determination.
Identifies real chessboards on desktop screens and distinguishes them from arbitrary windows.
"""
from __future__ import annotations
import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
import chess

class BoardDetector:
    """
    Detects chessboard boundaries, refines user-selected regions, and segments into 64 squares.
    """
    def __init__(self):
        pass

    def compute_checkerboard_score(self, crop: np.ndarray) -> float:
        """
        Calculates alternating contrast score for an 8x8 grid.
        Returns high values (>25.0) for genuine chessboards and low values for non-boards.
        """
        if crop is None or crop.size == 0:
            return 0.0

        h, w = crop.shape[:2]
        if h < 80 or w < 80:
            return 0.0

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        cell_h = h / 8.0
        cell_w = w / 8.0

        values = np.zeros((8, 8), dtype=np.float32)
        for r in range(8):
            for c in range(8):
                # Sample central 50% of the square to avoid piece borders
                y1 = int((r + 0.25) * cell_h)
                y2 = int((r + 0.75) * cell_h)
                x1 = int((c + 0.25) * cell_w)
                x2 = int((c + 0.75) * cell_w)
                patch = gray[y1:y2, x1:x2]
                if patch.size > 0:
                    values[r, c] = float(np.median(patch))

        # Checkerboard pattern: 1 for light squares, -1 for dark squares
        pattern_a = np.array([[1.0 if (r + c) % 2 == 0 else -1.0 for c in range(8)] for r in range(8)])
        pattern_b = -pattern_a

        corr_a = float(np.sum(values * pattern_a)) / 64.0
        corr_b = float(np.sum(values * pattern_b)) / 64.0
        max_corr = max(abs(corr_a), abs(corr_b))

        # Check contrast between light squares and dark squares
        light_vals = [values[r, c] for r in range(8) for c in range(8) if (r + c) % 2 == 0]
        dark_vals = [values[r, c] for r in range(8) for c in range(8) if (r + c) % 2 != 0]
        contrast = abs(float(np.mean(light_vals)) - float(np.mean(dark_vals)))

        return max(max_corr, contrast)

    def detect_chessboards(self, full_image: np.ndarray) -> List[Tuple[int, int, int, int, float]]:
        """
        Scans image and finds all candidate chessboard bounding boxes.
        Returns list of (x, y, w, h, score) sorted descending by confidence score.
        """
        if full_image is None or full_image.size == 0:
            return []

        h, w = full_image.shape[:2]
        gray = cv2.cvtColor(full_image, cv2.COLOR_BGR2GRAY) if len(full_image.shape) == 3 else full_image

        # Multi-scale contour search
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 40, 120)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []

        min_board_dim = min(w, h) * 0.12  # At least 12% of screen dimension
        max_board_dim = max(w, h) * 1.05  # Accommodate full-height chessboards in browser windows

        for c in contours:
            area = cv2.contourArea(c)
            if area < (min_board_dim * min_board_dim * 0.7):
                continue

            rx, ry, rw, rh = cv2.boundingRect(c)
            aspect_ratio = rw / float(rh) if rh > 0 else 0.0

            if 0.90 <= aspect_ratio <= 1.10 and rw >= min_board_dim and rw <= max_board_dim:
                crop = full_image[ry:ry + rh, rx:rx + rw]
                score = self.compute_checkerboard_score(crop)
                if score >= 15.0:  # Valid checkerboard contrast
                    candidates.append((rx, ry, rw, rh, score))

        # Deduplicate overlapping bounding boxes
        unique_candidates = []
        for cand in sorted(candidates, key=lambda x: x[4], reverse=True):
            cx, cy, cw, ch, c_score = cand
            overlap = False
            for ux, uy, uw, uh, _ in unique_candidates:
                # Calculate Intersection over Union (IoU)
                ix1 = max(cx, ux)
                iy1 = max(cy, uy)
                ix2 = min(cx + cw, ux + uw)
                iy2 = min(cy + ch, uy + uh)
                if ix2 > ix1 and iy2 > iy1:
                    inter_area = (ix2 - ix1) * (iy2 - iy1)
                    union_area = (cw * ch) + (uw * uh) - inter_area
                    if inter_area / float(union_area) > 0.4:
                        overlap = True
                        break
            if not overlap:
                unique_candidates.append(cand)

        return unique_candidates

    def refine_inner_board(self, region_crop: np.ndarray) -> Tuple[int, int, int, int]:
        """
        If user selected a window region that contains a board with surrounding margins/captures,
        finds the inner 8x8 square board boundaries relative to region_crop using edge projection.
        Returns relative (rx, ry, rw, rh).
        """
        if region_crop is None or region_crop.size == 0:
            return 0, 0, 0, 0

        h, w = region_crop.shape[:2]
        if h < 60 or w < 60:
            dim = min(w, h)
            return (w - dim) // 2, (h - dim) // 2, dim, dim

        # 1. Edge projection to snap grid boundaries (strips rank/file labels, margins, and borders)
        gray = cv2.cvtColor(region_crop, cv2.COLOR_BGR2GRAY) if len(region_crop.shape) == 3 else region_crop
        edges = cv2.Canny(gray, 30, 90)
        v_proj = np.sum(edges, axis=0)
        h_proj = np.sum(edges, axis=1)

        max_v = float(np.max(v_proj)) if len(v_proj) > 0 else 0.0
        max_h = float(np.max(h_proj)) if len(h_proj) > 0 else 0.0

        if max_v > 0 and max_h > 0:
            thresh_v = max_v * 0.32
            thresh_h = max_h * 0.32
            v_peaks = np.where(v_proj > thresh_v)[0]
            h_peaks = np.where(h_proj > thresh_h)[0]

            if len(v_peaks) >= 2 and len(h_peaks) >= 2:
                x1, x2 = int(v_peaks[0]), int(v_peaks[-1])
                y1, y2 = int(h_peaks[0]), int(h_peaks[-1])
                bw = x2 - x1
                bh = y2 - y1
                if bw >= int(w * 0.65) and bh >= int(h * 0.65):
                    ar = bw / float(bh)
                    if 0.88 <= ar <= 1.12:
                        dim = min(bw, bh)
                        cx = x1 + bw // 2
                        cy = y1 + bh // 2
                        rx = max(0, min(w - dim, cx - dim // 2))
                        ry = max(0, min(h - dim, cy - dim // 2))
                        return rx, ry, dim, dim

        # 2. Check for inner chessboards using multi-scale detection
        inner_candidates = self.detect_chessboards(region_crop)
        if inner_candidates:
            bx, by, bw, bh, sc = inner_candidates[0]
            if sc >= 15.0:
                return bx, by, bw, bh

        # 3. Fallback: largest square centered inside region
        dim = min(w, h)
        return (w - dim) // 2, (h - dim) // 2, dim, dim


    def segment_squares(
        self,
        board_img: np.ndarray,
        white_at_bottom: bool = True
    ) -> Dict[chess.Square, np.ndarray]:
        """
        Divides the board image into 64 individual square crops.
        Maps correctly to chess.Square (0..63).
        """
        squares = {}
        if board_img is None or board_img.size == 0:
            return squares

        bh, bw = board_img.shape[:2]
        sq_w = bw / 8.0
        sq_h = bh / 8.0

        for r_idx in range(8):  # 0 is top row, 7 is bottom row
            for c_idx in range(8):  # 0 is left col, 7 is right col
                x1 = int(round(c_idx * sq_w))
                x2 = int(round((c_idx + 1) * sq_w))
                y1 = int(round(r_idx * sq_h))
                y2 = int(round((r_idx + 1) * sq_h))

                square_crop = board_img[y1:y2, x1:x2]

                if white_at_bottom:
                    file_idx = c_idx           # 0=A, 7=H
                    rank_idx = 7 - r_idx       # 0 (top row) = rank 8, 7 (bottom row) = rank 1
                else:
                    file_idx = 7 - c_idx       # 0=H, 7=A
                    rank_idx = r_idx           # 0 (top row) = rank 1, 7 (bottom row) = rank 8

                sq = chess.square(file_idx, rank_idx)
                squares[sq] = square_crop

        return squares

    def determine_orientation(self, crops: Dict[chess.Square, np.ndarray]) -> bool:
        """
        Determines if White is at bottom by checking piece color distribution on ranks 1-2 vs ranks 7-8.
        White pieces are located on ranks 1-2 when White is at bottom.
        """
        if not crops:
            return True

        w_bottom_votes = 0
        b_bottom_votes = 0

        # Sample squares on ranks 1-2 (bottom when white_at_bottom=True)
        # vs ranks 7-8 (top when white_at_bottom=True)
        r12_sqs = [chess.square(f, r) for r in [0, 1] for f in range(8)]
        r78_sqs = [chess.square(f, r) for r in [6, 7] for f in range(8)]

        for sq in r12_sqs:
            crop = crops.get(sq)
            if crop is not None and crop.size > 0:
                h, w = crop.shape[:2]
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
                cy1, cy2 = int(h * 0.20), int(h * 0.80)
                cx1, cx2 = int(w * 0.20), int(w * 0.80)
                center = gray[cy1:cy2, cx1:cx2]
                # High luminance pixels = White piece
                bright_px = int(np.count_nonzero(center > 145))
                dark_px = int(np.count_nonzero(center < 105))
                if bright_px > dark_px + 10:
                    w_bottom_votes += 1
                elif dark_px > bright_px + 10:
                    b_bottom_votes += 1

        for sq in r78_sqs:
            crop = crops.get(sq)
            if crop is not None and crop.size > 0:
                h, w = crop.shape[:2]
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
                cy1, cy2 = int(h * 0.20), int(h * 0.80)
                cx1, cx2 = int(w * 0.20), int(w * 0.80)
                center = gray[cy1:cy2, cx1:cx2]
                bright_px = int(np.count_nonzero(center > 145))
                dark_px = int(np.count_nonzero(center < 105))
                if bright_px > dark_px + 10:
                    b_bottom_votes += 1  # White pieces on rank 7-8 means Black is at bottom
                elif dark_px > bright_px + 10:
                    w_bottom_votes += 1

        if w_bottom_votes > b_bottom_votes + 2:
            return True
        elif b_bottom_votes > w_bottom_votes + 2:
            return False

        # Fallback to rank average luminance
        r2_brightness = [float(np.mean(crops[chess.square(f, 1)])) for f in range(8) if chess.square(f, 1) in crops]
        r7_brightness = [float(np.mean(crops[chess.square(f, 6)])) for f in range(8) if chess.square(f, 6) in crops]
        avg_r2 = float(np.mean(r2_brightness)) if r2_brightness else 128.0
        avg_r7 = float(np.mean(r7_brightness)) if r7_brightness else 128.0

        if avg_r2 > avg_r7 + 10.0:
            return True
        elif avg_r7 > avg_r2 + 10.0:
            return False

        return True

