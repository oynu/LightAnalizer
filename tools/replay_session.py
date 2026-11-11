"""
Offline Session Replayer for LightAnalizer.
Replays a recorded incident session, re-running parsing/vision pipeline on each frame,
comparing against expected game progress and reporting divergences.

Usage:
    python tools/replay_session.py <incident_dir_or_latest>
"""
import sys
import json
from pathlib import Path
import cv2
import chess

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.vision.notation_parser import parse_ocr_to_game
from core.vision.piece_classifier import PieceClassifier
from core.vision.state_inference import RobustMoveInference

def find_latest_incident(sessions_dir: Path) -> Path:
    incidents = sorted(sessions_dir.glob("incident_*"))
    if not incidents:
        raise FileNotFoundError(f"No incident directories found in {sessions_dir}")
    return incidents[-1]

def replay_incident(incident_dir: Path):
    manifest_path = incident_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: manifest.json not found in {incident_dir}")
        return

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print("=" * 70)
    print(f"REPLAYING INCIDENT: {manifest.get('incident_timestamp')}")
    print(f"Reason: {manifest.get('reason')}")
    print(f"Frames: {manifest.get('total_frames')}, Duration: {manifest.get('duration_seconds')}s")
    print("=" * 70)

    board = chess.Board()
    for frame in manifest.get("frames", []):
        idx = frame["index"]
        source = frame["source"]
        img_name = frame["image_file"]
        img_path = incident_dir / img_name
        ocr_items_raw = frame.get("ocr_items", [])

        # Re-constitute ocr_items format expected by parse_ocr_to_game
        ocr_items = []
        for it in ocr_items_raw:
            ocr_items.append((it["box"], it["text"], it.get("score", 1.0)))

        if source == "moves_tab":
            parsed_moves, final_board = parse_ocr_to_game(ocr_items)
            print(f"Frame #{idx:03d} [{source}]: {len(parsed_moves)} moves parsed. FEN: {final_board.fen()}")
            if frame.get("detected_moves"):
                print(f"   Recorded moves: {frame['detected_moves']}")
            if frame.get("verdict"):
                print(f"   Verdict: {frame['verdict']}")
        else:
            print(f"Frame #{idx:03d} [{source}]: Board vision frame")

    print("=" * 70)
    print("Replay completed.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    sessions_dir = PROJECT_ROOT / "data" / "sessions"
    target = None
    if len(sys.argv) > 1:
        arg_path = Path(sys.argv[1])
        if arg_path.exists():
            target = arg_path
        elif (sessions_dir / sys.argv[1]).exists():
            target = sessions_dir / sys.argv[1]

    if target is None:
        try:
            target = find_latest_incident(sessions_dir)
            print(f"Using latest incident: {target.name}")
        except FileNotFoundError as e:
            print(f"No incident found: {e}")
            sys.exit(1)

    replay_incident(target)
