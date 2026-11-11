"""
Robust piece classifier using multi-feature background subtraction,
edge contours, and template correlation matching.
Distinguishes real pieces from empty squares, move highlights, and board textures.
"""
from __future__ import annotations
import os
from pathlib import Path
import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
import chess
import chess.svg
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray, QRect

class PieceClassifier:
    """
    Robust classifier for piece presence, color, and piece type.
    Maintains a dual-theme template bank for Chess.com ('neo') and Lichess ('cburnett').
    """
    def __init__(self, target_square_size: int = 64):
        self.target_size = target_square_size
        self._scales = (0.72, 0.80, 0.88, 0.96)
        self._templates: Dict[Tuple[chess.PieceType, chess.Color], np.ndarray] = {}
        self._masks: Dict[Tuple[chess.PieceType, chess.Color], np.ndarray] = {}
        self._edges: Dict[Tuple[chess.PieceType, chess.Color], np.ndarray] = {}
        self._multi_scale_templates: Dict[Tuple[chess.PieceType, chess.Color, float], np.ndarray] = {}
        self._multi_scale_masks: Dict[Tuple[chess.PieceType, chess.Color, float], np.ndarray] = {}
        self._multi_scale_edges: Dict[Tuple[chess.PieceType, chess.Color, float], np.ndarray] = {}
        self._theme_templates: Dict[Tuple[chess.PieceType, chess.Color, str, float], Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        self._init_templates()

    def _init_templates(self) -> None:
        """Renders standard piece vector templates across multiple themes and scales."""
        tmpl_size = max(24, int(self.target_size))
        self.tmpl_size = tmpl_size
        self._templates.clear()
        self._masks.clear()
        self._edges.clear()
        self._multi_scale_templates.clear()
        self._multi_scale_masks.clear()
        self._multi_scale_edges.clear()
        self._theme_templates.clear()

        piece_types = [
            chess.PAWN, chess.KNIGHT, chess.BISHOP,
            chess.ROOK, chess.QUEEN, chess.KING
        ]
        piece_chars = {
            chess.PAWN: 'p', chess.KNIGHT: 'n', chess.BISHOP: 'b',
            chess.ROOK: 'r', chess.QUEEN: 'q', chess.KING: 'k'
        }
        color_chars = {chess.WHITE: 'w', chess.BLACK: 'b'}

        # 1. Chess.com 'neo' theme templates (PNG assets from data/themes/neo)
        neo_dir = Path(__file__).resolve().parent.parent.parent / "data" / "themes" / "neo"
        if neo_dir.exists():
            for color in [chess.WHITE, chess.BLACK]:
                for pt in piece_types:
                    fn = neo_dir / f"{color_chars[color]}{piece_chars[pt]}.png"
                    if fn.exists():
                        raw = cv2.imread(str(fn), cv2.IMREAD_UNCHANGED)
                        for s in (0.90, 1.0, 1.05):
                            pw = max(16, int(round(tmpl_size * s)))
                            ph = max(16, int(round(tmpl_size * s)))
                            resized_p = cv2.resize(raw, (pw, ph), interpolation=cv2.INTER_AREA if s <= 1.0 else cv2.INTER_LINEAR)

                            canvas = np.zeros((tmpl_size, tmpl_size, 4), dtype=np.uint8)
                            ox = (tmpl_size - pw) // 2
                            oy = (tmpl_size - ph) // 2
                            x1_c, x2_c = max(0, ox), min(tmpl_size, ox + pw)
                            y1_c, y2_c = max(0, oy), min(tmpl_size, oy + ph)
                            x1_p, x2_p = max(0, -ox), pw - max(0, (ox + pw) - tmpl_size)
                            y1_p, y2_p = max(0, -oy), ph - max(0, (oy + ph) - tmpl_size)

                            if (y2_c > y1_c) and (x2_c > x1_c):
                                canvas[y1_c:y2_c, x1_c:x2_c] = resized_p[y1_p:y2_p, x1_p:x2_p]

                            alpha = canvas[:, :, 3]
                            mask = (alpha > 20).astype(np.uint8) * 255
                            gray = cv2.cvtColor(canvas[:, :, :3], cv2.COLOR_BGR2GRAY)

                            c_edge = cv2.Canny(mask, 100, 200)
                            i_edge = cv2.Canny(gray, 40, 120) & (mask > 0)
                            edges = cv2.bitwise_or(c_edge, i_edge)
                            dil_edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)

                            self._theme_templates[(pt, color, 'neo', s)] = (gray, mask, dil_edges)

        # 2. Lichess 'cburnett' vector SVG templates
        for color in [chess.WHITE, chess.BLACK]:
            for pt in piece_types:
                piece = chess.Piece(pt, color)
                for s in self._scales:
                    psize = max(18, int(round(tmpl_size * s)))
                    offset = (tmpl_size - psize) // 2
                    svg_data = chess.svg.piece(piece, size=psize)

                    renderer = QSvgRenderer(QByteArray(svg_data.encode('utf-8')))
                    qimg = QImage(tmpl_size, tmpl_size, QImage.Format.Format_ARGB32)
                    qimg.fill(0)
                    painter = QPainter(qimg)
                    renderer.render(painter, QRect(offset, offset, psize, psize))
                    painter.end()

                    ptr = qimg.bits()
                    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((tmpl_size, tmpl_size, 4))
                    gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
                    alpha = arr[:, :, 3]
                    mask = (alpha > 20).astype(np.uint8) * 255
                    if color == chess.BLACK:
                        gray[mask > 0] = np.maximum(gray[mask > 0], 35)

                    c_edge = cv2.Canny(mask, 100, 200)
                    i_edge = cv2.Canny(gray, 40, 120) & (mask > 0)
                    edges = cv2.bitwise_or(c_edge, i_edge)
                    dilated_edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)

                    self._multi_scale_templates[(pt, color, s)] = gray
                    self._multi_scale_masks[(pt, color, s)] = mask
                    self._multi_scale_edges[(pt, color, s)] = dilated_edges
                    self._theme_templates[(pt, color, 'cburnett', s)] = (gray, mask, dilated_edges)

                    if abs(s - 0.88) < 0.01:
                        self._templates[(pt, color)] = gray
                        self._masks[(pt, color)] = mask
                        self._edges[(pt, color)] = dilated_edges

    def is_highlighted(self, square_crop: np.ndarray) -> bool:
        """
        Detects if a square has a Chess.com or Lichess move highlight tint (yellow/green).
        """
        if square_crop is None or square_crop.size == 0 or len(square_crop.shape) < 3:
            return False
        b = float(np.mean(square_crop[:, :, 0]))
        g = float(np.mean(square_crop[:, :, 1]))
        r = float(np.mean(square_crop[:, :, 2]))
        return (r > 125 and g > 125 and (r - b) > 28 and (g - b) > 28)

    def is_square_occupied(self, square_crop: np.ndarray) -> Tuple[bool, float]:
        """
        Determines whether a square is occupied.
        Uses border perimeter subtraction and central edge contour area.
        """
        if square_crop is None or square_crop.size == 0:
            return False, 0.0

        h, w = square_crop.shape[:2]
        gray = cv2.cvtColor(square_crop, cv2.COLOR_BGR2GRAY) if len(square_crop.shape) == 3 else square_crop

        # 1. Sample perimeter border strips (top 12%, bottom 12%, left 12%, right 12%)
        b_h = max(2, int(h * 0.12))
        b_w = max(2, int(w * 0.12))

        top_strip = gray[:b_h, :]
        bottom_strip = gray[-b_h:, :]
        left_strip = gray[:, :b_w]
        right_strip = gray[:, -b_w:]

        border_pixels = np.concatenate([
            top_strip.ravel(), bottom_strip.ravel(),
            left_strip.ravel(), right_strip.ravel()
        ])
        bg_median = float(np.median(border_pixels))

        # 2. Sample inner central region - exclude outer 16% to avoid coordinate labels (a-h, 1-8)
        cy1, cy2 = int(h * 0.16), int(h * 0.84)
        cx1, cx2 = int(w * 0.16), int(w * 0.84)
        center_patch = gray[cy1:cy2, cx1:cx2]
        c_std = float(np.std(center_patch))

        # Difference from background
        diff = np.abs(center_patch.astype(np.float32) - bg_median)
        fg_mask = diff > 15.0
        fg_ratio = float(np.count_nonzero(fg_mask)) / float(center_patch.size)

        # 3. Edge energy in center
        blurred = cv2.GaussianBlur(center_patch, (3, 3), 0)
        edges = cv2.Canny(blurred, 30, 80)
        edge_ratio = float(np.count_nonzero(edges)) / float(center_patch.size)

        # Contrast & structure thresholds reject faint highlights and empty squares with grey legal-move hint dots
        if self.is_highlighted(square_crop):
            is_occupied = (c_std >= 22.0 and fg_ratio >= 0.12) or (edge_ratio >= 0.035 and c_std >= 18.0) or (c_std >= 30.0)
        else:
            is_occupied = (c_std >= 22.0 and fg_ratio >= 0.08) or (edge_ratio >= 0.030 and c_std >= 18.0) or (c_std >= 30.0)

        confidence = min(1.0, max(c_std / 30.0, edge_ratio * 4.0, fg_ratio))

        return is_occupied, confidence

    def detect_piece_color(self, square_crop: np.ndarray) -> chess.Color:
        """
        Determines piece color (White vs Black) based on classification or foreground luminance.
        """
        if square_crop is None or square_crop.size == 0:
            return chess.WHITE

        resized_bgr = cv2.resize(square_crop, (self.target_size, self.target_size))
        b_h = max(2, int(self.target_size * 0.12))
        b_w = max(2, int(self.target_size * 0.12))
        border_bgr = np.concatenate([
            resized_bgr[:b_h, :, :].reshape(-1, 3),
            resized_bgr[-b_h:, :, :].reshape(-1, 3),
            resized_bgr[:, :b_w, :].reshape(-1, 3),
            resized_bgr[:, -b_w:, :].reshape(-1, 3)
        ], axis=0)
        bg_color = np.median(border_bgr, axis=0)
        diff_color = np.linalg.norm(resized_bgr.astype(np.float32) - bg_color, axis=2)
        crop_fg = diff_color > 16.0
        gray = cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2GRAY)
        fg_px = gray[crop_fg] if np.any(crop_fg) else gray.ravel()
        p_mean = float(np.mean(fg_px))
        p80 = float(np.percentile(fg_px, 80))
        is_white = (p_mean >= 135.0) or (p80 >= 215.0 and p_mean >= 90.0)
        return chess.WHITE if is_white else chess.BLACK

    def classify_square_candidates(
        self,
        square_crop: np.ndarray
    ) -> List[Tuple[Optional[chess.Piece], float]]:
        """
        Classifies piece candidates on a square using 2D centroid-baseline alignment,
        centered bounding-box asymmetry, Staunton top/apex profiles, and dual-theme multi-scale template matching.
        Returns a sorted list of (piece, confidence) candidates in descending score order.
        """
        if square_crop is None or square_crop.size == 0:
            return [(None, 1.0)]

        is_occ, occ_conf = self.is_square_occupied(square_crop)
        if not is_occ:
            return [(None, 1.0 - occ_conf)]

        resized_bgr = cv2.resize(square_crop, (self.target_size, self.target_size))
        gray = cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2GRAY) if len(resized_bgr.shape) == 3 else resized_bgr

        # Sample border background color in BGR
        b_h = max(2, int(self.target_size * 0.12))
        b_w = max(2, int(self.target_size * 0.12))
        border_bgr = np.concatenate([
            resized_bgr[:b_h, :, :].reshape(-1, 3),
            resized_bgr[-b_h:, :, :].reshape(-1, 3),
            resized_bgr[:, :b_w, :].reshape(-1, 3),
            resized_bgr[:, -b_w:, :].reshape(-1, 3)
        ], axis=0)
        bg_color = np.median(border_bgr, axis=0)  # [B, G, R]

        # Robust color difference segmentation (handles cream, white, green, wood boards)
        diff_color = np.linalg.norm(resized_bgr.astype(np.float32) - bg_color, axis=2)
        crop_fg = (diff_color > 16.0).astype(np.uint8) * 255

        # Remove border seams and isolated coordinate ticks ('a'-'h', '1'-'8')
        crop_fg[:4, :] = 0
        crop_fg[-4:, :] = 0
        crop_fg[:, :4] = 0
        crop_fg[:, -4:] = 0

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(crop_fg)
        if num_labels > 2:
            cleaned_fg = np.zeros_like(crop_fg)
            for i in range(1, num_labels):
                cx, cy = centroids[i]
                area = stats[i, cv2.CC_STAT_AREA]
                if area >= 25 and 8 <= cx <= (self.target_size - 8) and 8 <= cy <= (self.target_size - 8):
                    cleaned_fg[labels == i] = 255
            if np.count_nonzero(cleaned_fg) > 0:
                crop_fg = cleaned_fg

        # 2D Centroid alignment for sub-pixel translation invariance
        center_x = (self.target_size - 1) / 2.0
        center_y = (self.target_size - 1) / 2.0

        ys, xs = np.where(crop_fg > 0)
        if len(ys) > 0 and len(xs) > 0:
            cx = (float(xs.min()) + float(xs.max())) / 2.0
            cy = (float(ys.min()) + float(ys.max())) / 2.0
            dx = int(round(center_x - cx))
            dy = int(round(center_y - cy))

            shift_x = dx if abs(dx) <= 4 else 0
            shift_y = dy if abs(dy) <= 4 else 0
            if shift_x != 0 or shift_y != 0:
                T = np.float32([[1, 0, shift_x], [0, 1, shift_y]])
                crop_fg = cv2.warpAffine(crop_fg, T, (self.target_size, self.target_size))
                gray = cv2.warpAffine(gray, T, (self.target_size, self.target_size), borderValue=int(np.mean(bg_color)))
                ys, xs = np.where(crop_fg > 0)

        fg_count = np.count_nonzero(crop_fg > 0)
        area_ratio = float(fg_count) / float(self.target_size * self.target_size)

        # Detect piece color from foreground luminance
        fg_pixels = gray[crop_fg > 0] if fg_count > 0 else gray.ravel()
        p_mean = float(np.mean(fg_pixels))
        p80 = float(np.percentile(fg_pixels, 80))
        is_detected_white = (p_mean >= 135.0) or (p80 >= 215.0 and p_mean >= 90.0)

        # Centered bounding box asymmetry and Staunton geometric profiles
        if len(ys) > 0 and len(xs) > 0:
            ymin, ymax = int(ys.min()), int(ys.max())
            xmin, xmax = int(xs.min()), int(xs.max())
            bbox = crop_fg[ymin:ymax+1, xmin:xmax+1]
            flipped_bbox = cv2.flip(bbox, 1)
            asym = float(np.count_nonzero((bbox > 0) != (flipped_bbox > 0))) / float(max(1, np.count_nonzero(bbox > 0)))

            bh = ymax - ymin + 1
            bw = xmax - xmin + 1
            aspect = bh / float(max(1, bw))
            y_top = min(ymax, int(ymin + bh * 0.15))
            y_bot = max(ymin, int(ymin + bh * 0.85))
            y_apex = min(ymax, int(ymin + bh * 0.05))
            w_top = np.count_nonzero(crop_fg[y_top, xmin:xmax+1] > 0)
            w_bot = np.count_nonzero(crop_fg[y_bot, xmin:xmax+1] > 0)
            w_apex = np.count_nonzero(crop_fg[y_apex, xmin:xmax+1] > 0)
            top_bot_ratio = float(w_top) / float(max(1, w_bot))
            apex_ratio = float(w_apex) / float(max(1, w_bot))
        else:
            asym = 0.0
            bh, bw, aspect = 0, 0, 1.0
            top_bot_ratio, apex_ratio = 0.5, 0.5

        # Edge contours of candidate crop
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        crop_edges = cv2.Canny(blurred, 40, 120)
        crop_edges_dilated = cv2.dilate(crop_edges, np.ones((2, 2), np.uint8), iterations=1)

        piece_types = [
            chess.PAWN, chess.KNIGHT, chess.BISHOP,
            chess.ROOK, chess.QUEEN, chess.KING
        ]
        candidates: List[Tuple[Optional[chess.Piece], float]] = []

        for color in [chess.WHITE, chess.BLACK]:
            color_matches = (color == chess.WHITE and is_detected_white) or (color == chess.BLACK and not is_detected_white)

            for pt in piece_types:
                best_pt_score = -1.0

                # Match across all available theme templates (Neo and Cburnett)
                for (t_pt, t_color, t_theme, t_scale), (tmpl_gray, tmpl_mask, tmpl_edge) in self._theme_templates.items():
                    if t_pt != pt or t_color != color:
                        continue

                    # 1. Mask IoU (silhouette overlap prevents small pieces matching large pieces)
                    intersection_mask = np.count_nonzero((crop_fg > 0) & (tmpl_mask > 0))
                    union_mask = np.count_nonzero((crop_fg > 0) | (tmpl_mask > 0))
                    iou_mask = float(intersection_mask) / float(max(1, union_mask))

                    # 2. Edge contour IoU
                    intersection_edge = np.count_nonzero((crop_edges_dilated > 0) & (tmpl_edge > 0))
                    total_edges = np.count_nonzero(tmpl_edge > 0)
                    edge_recall = float(intersection_edge) / float(max(1, total_edges)) if total_edges > 0 else 0.0

                    # 3. Normalized cross-correlation under mask
                    try:
                        res = cv2.matchTemplate(gray, tmpl_gray, cv2.TM_CCORR_NORMED, mask=tmpl_mask)
                        val = float(res.max())
                        corr_score = 0.0 if np.isnan(val) else val
                    except Exception:
                        corr_score = 0.0

                    # 4. Direct Interior Pixel Matching
                    interior = tmpl_mask > 20
                    if np.any(interior):
                        img_p = gray[interior].astype(np.float32)
                        tmpl_p = tmpl_gray[interior].astype(np.float32)
                        luma_sim = 1.0 - (float(np.mean(np.abs(img_p - tmpl_p))) / 255.0)
                    else:
                        luma_sim = 0.5

                    base_score = 0.35 * iou_mask + 0.25 * edge_recall + 0.15 * corr_score + 0.25 * luma_sim
                    if base_score > best_pt_score:
                        best_pt_score = base_score

                # Penalize opposite color
                if not color_matches:
                    best_pt_score -= 0.60

                # Staunton Topological Bonuses & Penalties
                # Knight: horse head gives high horizontal asymmetry (>= 0.22 vs < 0.12 for others)
                if pt == chess.KNIGHT:
                    if asym >= 0.22:
                        best_pt_score += 0.12
                    elif asym < 0.12:
                        best_pt_score -= 0.18
                else:
                    if asym >= 0.28:
                        best_pt_score -= 0.12

                # Pawn: smallest piece silhouette and narrow base
                if pt == chess.PAWN:
                    if area_ratio <= 0.26 and aspect >= 1.20:
                        best_pt_score += 0.10
                    elif area_ratio >= 0.38 or aspect < 1.05:
                        best_pt_score -= 0.15

                # Rook: flat horizontal crenellated castle top
                if pt == chess.ROOK:
                    if top_bot_ratio >= 0.70 and apex_ratio >= 0.45:
                        best_pt_score += 0.08
                    elif top_bot_ratio < 0.40:
                        best_pt_score -= 0.12

                # King: single vertical cross finial at apex
                if pt == chess.KING:
                    if apex_ratio <= 0.20 and top_bot_ratio <= 0.35:
                        best_pt_score += 0.08
                    elif apex_ratio > 0.50:
                        best_pt_score -= 0.10

                # Queen: wide coronet with high top ratio and area
                if pt == chess.QUEEN and top_bot_ratio >= 0.80 and area_ratio >= 0.35:
                    best_pt_score += 0.06

                conf = max(0.01, min(1.0, best_pt_score))
                candidates.append((chess.Piece(pt, color), conf))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates

    def classify_square(self, square_crop: np.ndarray) -> Tuple[Optional[chess.Piece], float]:
        """
        Classifies piece on a square. Returns top (Piece or None, confidence).
        """
        cands = self.classify_square_candidates(square_crop)
        return cands[0]
