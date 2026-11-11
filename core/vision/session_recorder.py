"""
Session Recorder and Incident Capture for LightAnalizer.
Maintains a rolling in-memory buffer of recent frames and detection decisions.
When an incident is flagged (via F9 hotkey or error threshold), dumps frames and
manifest to data/sessions/incident_<timestamp>/ for offline replay and debugging.
"""
from __future__ import annotations
import os
import time
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any
import threading
import cv2
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class FrameSnapshot:
    timestamp: float
    source: str  # "moves_tab" or "board"
    image: np.ndarray
    ocr_items: List[Any] = field(default_factory=list)
    board_fen_before: str = ""
    board_fen_after: str = ""
    detected_moves: List[str] = field(default_factory=list)
    verdict: str = ""
    notes: str = ""

class SessionRecorder:
    """
    Thread-safe rolling buffer of recent capture and inference frames.
    Buffers the last ~60 frames (~20 seconds of gameplay at 350ms cadence).
    """
    _instance: Optional[SessionRecorder] = None
    _lock = threading.Lock()

    def __init__(self, max_frames: int = 60, base_dir: Optional[Path] = None):
        self.max_frames = max_frames
        self.base_dir = base_dir or (Path(__file__).resolve().parent.parent.parent / "data" / "sessions")
        self._buffer: deque[FrameSnapshot] = deque(maxlen=max_frames)
        self._buf_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> SessionRecorder:
        with cls._lock:
            if cls._instance is None:
                cls._instance = SessionRecorder()
            return cls._instance

    def record_frame(
        self,
        source: str,
        image: np.ndarray,
        ocr_items: Optional[List[Any]] = None,
        board_fen_before: str = "",
        board_fen_after: str = "",
        detected_moves: Optional[List[str]] = None,
        verdict: str = "",
        notes: str = ""
    ) -> None:
        if image is None or image.size == 0:
            return
        snapshot = FrameSnapshot(
            timestamp=time.time(),
            source=source,
            image=image.copy(),
            ocr_items=ocr_items or [],
            board_fen_before=board_fen_before,
            board_fen_after=board_fen_after,
            detected_moves=detected_moves or [],
            verdict=verdict,
            notes=notes
        )
        with self._buf_lock:
            self._buffer.append(snapshot)

    def save_incident(self, reason: str = "User flagged wrong move (F9)") -> Optional[Path]:
        """
        Dumps the rolling buffer to data/sessions/incident_<timestamp>/
        Returns path to created incident directory.
        """
        with self._buf_lock:
            snapshots = list(self._buffer)

        if not snapshots:
            logger.warning("[SessionRecorder] Buffer empty; nothing to save.")
            return None

        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        incident_dir = self.base_dir / f"incident_{timestamp_str}"
        incident_dir.mkdir(parents=True, exist_ok=True)

        frames_meta = []
        for i, snap in enumerate(snapshots):
            img_filename = f"frame_{i:03d}_{snap.source}.png"
            img_path = incident_dir / img_filename
            try:
                cv2.imwrite(str(img_path), snap.image)
            except Exception as e:
                logger.error(f"[SessionRecorder] Failed saving {img_filename}: {e}")

            # Prepare serializable ocr_items (convert numpy arrays in box)
            serializable_ocr = []
            for item in snap.ocr_items:
                try:
                    box, text, score = item[0], str(item[1]), float(item[2]) if len(item) > 2 else 1.0
                    box_list = [[float(pt[0]), float(pt[1])] for pt in box]
                    serializable_ocr.append({"box": box_list, "text": text, "score": score})
                except Exception:
                    pass

            frames_meta.append({
                "index": i,
                "timestamp": snap.timestamp,
                "source": snap.source,
                "image_file": img_filename,
                "board_fen_before": snap.board_fen_before,
                "board_fen_after": snap.board_fen_after,
                "detected_moves": snap.detected_moves,
                "verdict": snap.verdict,
                "notes": snap.notes,
                "ocr_items": serializable_ocr
            })

        manifest = {
            "incident_timestamp": timestamp_str,
            "reason": reason,
            "total_frames": len(snapshots),
            "start_time": snapshots[0].timestamp,
            "end_time": snapshots[-1].timestamp,
            "duration_seconds": round(snapshots[-1].timestamp - snapshots[0].timestamp, 2),
            "frames": frames_meta
        }

        manifest_path = incident_dir / "manifest.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            logger.info(f"[SessionRecorder] Incident saved with {len(snapshots)} frames to {incident_dir}")
            return incident_dir
        except Exception as e:
            logger.error(f"[SessionRecorder] Failed saving manifest: {e}")
            return incident_dir
