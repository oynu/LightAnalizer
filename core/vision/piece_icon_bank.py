"""
Figurine Piece Icon Classifier & Template Bank for Chess Notation.
Detects and classifies piece icons (K, Q, R, B, N) that appear to the left
of square coordinates in GUI moves tabs (e.g. Chess.com, Lichess).
Supports both pre-rendered Staunton vector glyphs and continuous self-learning
from confirmed unambiguous in-game moves.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional, Tuple
import cv2
import numpy as np
import chess
import chess.svg
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray, QRect

logger = logging.getLogger(__name__)

PIECE_SYMBOLS = {
    chess.KING: 'K',
    chess.QUEEN: 'Q',
    chess.ROOK: 'R',
    chess.BISHOP: 'B',
    chess.KNIGHT: 'N'
}

class PieceIconBank:
    """
    Template bank and classifier for small notation figurine icons.
    """
    def __init__(self, icon_size: int = 24):
        self.icon_size = icon_size
        self._templates: Dict[str, np.ndarray] = {}
        self._learned_templates: Dict[str, np.ndarray] = {}
        self._init_default_templates()

    def _init_default_templates(self) -> None:
        """Initializes standard Staunton glyph templates for K, Q, R, B, N."""
        try:
            for pt, sym in PIECE_SYMBOLS.items():
                p = chess.Piece(pt, chess.WHITE)
                svg_data = chess.svg.piece(p, size=self.icon_size)
                renderer = QSvgRenderer(QByteArray(svg_data.encode('utf-8')))
                qimg = QImage(self.icon_size, self.icon_size, QImage.Format.Format_ARGB32)
                qimg.fill(0)
                painter = QPainter(qimg)
                renderer.render(painter, QRect(0, 0, self.icon_size, self.icon_size))
                painter.end()

                ptr = qimg.bits()
                arr = np.frombuffer(ptr, dtype=np.uint8).reshape((self.icon_size, self.icon_size, 4))
                alpha = arr[:, :, 3]
                mask = (alpha > 40).astype(np.uint8) * 255
                self._templates[sym] = mask
        except Exception as e:
            logger.warning(f"Could not render SVG piece icons: {e}")

    def has_icon(self, image: np.ndarray, text_box: list) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Examines the region immediately to the left of the OCR text bounding box.
        Returns (has_icon: bool, icon_crop: Optional[np.ndarray]).
        """
        if image is None or image.size == 0 or not text_box:
            return False, None

        try:
            h_img, w_img = image.shape[:2]
            xs = [p[0] for p in text_box]
            ys = [p[1] for p in text_box]
            x_min = int(round(min(xs)))
            y_min = int(round(min(ys)))
            y_max = int(round(max(ys)))
            box_h = max(10, y_max - y_min)

            # Icon is situated immediately left of x_min
            # Width is approximately box_h * 1.1
            icon_w = int(round(box_h * 1.15))
            x_left = max(0, x_min - icon_w)
            x_right = max(0, x_min - int(round(box_h * 0.08)))

            if (x_right - x_left) < 6:
                return False, None

            y_top = max(0, y_min - 2)
            y_bottom = min(h_img, y_max + 2)

            crop = image[y_top:y_bottom, x_left:x_right]
            if crop.size == 0:
                return False, None

            # Detect if region contains non-background artwork
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
            # Estimate background from borders
            border_px = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
            bg_val = float(np.median(border_px))
            diff = np.abs(gray.astype(np.float32) - bg_val)
            fg_ratio = float(np.count_nonzero(diff > 20.0)) / float(gray.size)

            # Edge count
            edges = cv2.Canny(gray, 40, 120)
            edge_ratio = float(np.count_nonzero(edges)) / float(gray.size)

            # An icon has strong foreground and significant edge energy
            if fg_ratio >= 0.12 and edge_ratio >= 0.04:
                resized = cv2.resize(gray, (self.icon_size, self.icon_size))
                return True, resized

            return False, None
        except Exception:
            return False, None

    def classify_icon(self, icon_crop: np.ndarray) -> Optional[str]:
        """
        Matches icon_crop against learned and default piece templates.
        Returns 'K', 'Q', 'R', 'B', 'N' or None.
        """
        if icon_crop is None or icon_crop.size == 0:
            return None

        resized = cv2.resize(icon_crop, (self.icon_size, self.icon_size))
        # Binarize
        _, bin_crop = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        best_sym = None
        best_score = -1.0

        # Prioritize learned templates
        templates_to_check = {**self._templates, **self._learned_templates}

        for sym, tmpl in templates_to_check.items():
            if tmpl is None or tmpl.shape != (self.icon_size, self.icon_size):
                continue
            # IoU of mask
            inter = np.count_nonzero((bin_crop > 0) & (tmpl > 0))
            union = np.count_nonzero((bin_crop > 0) | (tmpl > 0))
            iou = float(inter) / float(max(1, union))

            if iou > best_score:
                best_score = iou
                best_sym = sym

        if best_score >= 0.35:
            return best_sym

        return None

    def learn_icon(self, piece_symbol: str, icon_crop: np.ndarray) -> None:
        """Stores a high-confidence icon crop learned during an unambiguous move."""
        if piece_symbol in ('K', 'Q', 'R', 'B', 'N') and icon_crop is not None and icon_crop.size > 0:
            resized = cv2.resize(icon_crop, (self.icon_size, self.icon_size))
            _, bin_crop = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            self._learned_templates[piece_symbol] = bin_crop
            logger.debug(f"[PieceIconBank] Learned icon template for {piece_symbol}")
