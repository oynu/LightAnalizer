# LightAnalizer — Premium AI Chess Analysis & Opponent Profiling

LightAnalizer is a modern desktop chess analysis assistant built with Python, PySide6, python-chess, OpenCV, and Stockfish. It automatically watches a chessboard on your screen, detects moves in real time using state-based occupancy bitmask inference, and delivers instant Stockfish candidate moves with tactical explanations, along with deep post-game review and empirical opponent profiling.

---

## 1. Key Features

- **Intuitive Screen Selection (Snipping-Tool Style)**:
  - **Select Moves Tab (Primary OCR Mode)**: Simply drag a rectangle over the moves / notation tab (e.g. on Chess.com or Lichess). LightAnalizer transcribes every move in real time using local ONNX neural OCR, automatically reconstructing the game state and showing the best engine moves.
  - **Auto-Detect & Select Board (Vision Mode)**: Scans the desktop across displays, detects 8×8 grid contrast, estimates boundaries, determines orientation, and locks onto the board automatically.
  - **Multi-Monitor & DPI Aware**: Fully aware of Windows Per-Monitor V2 DPI scaling (100%, 125%, 150%, 200%) and multi-screen coordinate offsets with zero capture drift.

- **High-Accuracy Real-Time OCR Move Transcription (`core/vision/`)**:
  - Neural text detection & recognition powered by `rapidocr-onnxruntime`.
  - Multi-column row grouping and reading order sorting (handles both table columns and inline text notation).
  - Robust chess notation parsing with automatic OCR typo correction (`Rel` -> `Re1`, `eS` -> `e5`, `0-0` -> `O-O`, figurine unicode symbols -> SAN letters).
  - Automatically filters out clock times (`2:59`), engine evaluations (`+0.4`), move numbers (`1.`, `24.`), and win probabilities (`98%`).
  - Automatically triggers Stockfish 3-line MultiPV analysis with tactical explanations whenever a new move is made.

- **Fast, Robust State-Based Board Vision Move Detection**:
  - Sub-millisecond change detection with 32×32 thumbnail difference hashing.
  - Multi-frame animation debouncing (80–120 ms) to let piece drags and sliding animations settle before evaluation.
  - Occupancy bitmask verification against authoritative legal chess rules (`chess.Board.legal_moves`).
  - Handles captures, kingside and queenside castling, en passant, and pawn promotions (defaulting to Queen) seamlessly without special-case hacks.
  - Multi-ply blitz catchup (2-ply sequences) and automatic turn resynchronization via null-move evaluation.

- **Truthful Game Synchronization ("Position Uncertain" Over Hallucinations)**:
  - When the screen is obscured, a piece is mid-drag, or board state is ambiguous, LightAnalizer reports `Position uncertain` rather than guessing or flashing random pieces.
  - Autonomous healing: only resynchronizes to positions reachable within $\le 3$ plies from the known board, exact starting position, exact opening book matches, or full board reconstruction after $\ge 4$ seconds of continuous uncertainty. Never jumps to stale or unrelated history boards.

- **Live Game vs. Variation Exploration**:
  - The authoritative `GameStateManager` keeps your live screen position separated from manual board analysis.
  - Step forward/backward through move history or try alternative candidate lines on the board; return instantly with the prominent *"Return to Live Game"* action.

- **Compact Floating HUD & Always-on-Top Floating Pin**:
  - Launches in a sleek, non-intrusive 350×520 HUD mode designed to sit neatly next to any chess board in your web browser without obscuring the screen.
  - One-click `📌 Pin` toggle (shortcut: `P`) keeps the assistant floating on top across windows and browsers.
  - One-click `🗗 Compact / ⛶ Expand` toggle (shortcut: `C`) to switch between minimal HUD (coach evaluation + top 3 moves) and full desktop view (full chessboard + eval bar + analysis).
  - Flexible window resizing down to 280×360 so you can place it anywhere on screen.

- **Stockfish MultiPV Engine Analysis with Version Tagging**:
  - Sub-400ms polling latency (capturing every 300–400 ms) with immediate candidate move updates.
  - Live top 3 candidate moves (#1 Best, #2 Alternative, #3 Candidate) evaluated via Stockfish UCI MultiPV.
  - Interactive turn badges: clearly differentiates whether it is **Your Turn** (`● YOUR TURN ➔ PLAY: <SAN> (<eval>)`) or the **Opponent's Turn** (`● OPPONENT'S TURN ➔ EXPECT: <SAN> (<eval>)`), with color-coded high-contrast styling (Sky Blue for White, Amber for Black).
  - One-click Player Side Toggle `[ ♔ White ]` / `[ ♚ Black ]` (shortcut: `F`) to seamlessly switch playing as White or against White / as Black, flipping the board orientation and re-orienting vision detection instantly.
  - Interactive Position & Starting Side Setup Modal (`Ctrl+P` / `"⚡ Position..."`): choose between starting as White, starting as Black (flipped board), common opening lines (1. e4, 1. d4), or pasting custom FEN positions from studies and puzzles.
  - Every engine search request is tagged with a monotonic position version ID. Outdated engine results arriving after a fast move are discarded immediately, preventing stale evaluations from overwriting live positions.

- **Post-Game Review & Blunder Classification**:
  - Automated game review calculates player accuracy percentage, detects critical turning points, and classifies every move (Best, Excellent, Good, Inaccuracy, Mistake, Blunder).

- **Persistent Opponent Profiling (SQLite)**:
  - Tracks opponents, opening repertoires, tactical weaknesses, blunder frequencies, and time-pressure tendencies in a local SQLite database (`data/lightanalizer.db`).

- **Developer Diagnostics Drawer**:
  - Collapsible side telemetry drawer showing capture latency, recognition latency, total pipeline latency, FPS, detected FEN vs. authoritative FEN, last confirmed SAN move, and rejection reasons.

---

## 2. How Move Detection Works

LightAnalizer uses a deterministic, state-based occupancy pipeline designed for speed and reliability:

1. **Change Detection**: Computes per-square mean pixel differences between the settled current frame and the baseline frame. Squares with a difference exceeding $\max(6.0, 2.5 \times \text{median\_diff})$ are tagged as *changed*.
2. **Obscuration Guard**: If $\ge 16$ squares change simultaneously, the board is considered obscured or navigated away, immediately returning `UNCERTAIN`.
3. **Targeted Classification**: *Only* the changed squares are classified as empty, white piece, or black piece using dual-theme template correlation and foreground luminance statistics. Unchanged squares preserve their ground-truth state from the known board.
4. **64-bit Occupancy Masks**: Builds 64-bit white and black occupancy bitmasks (`obs_white`, `obs_black`).
5. **No-Change Filtering**: If the observed occupancy mismatch against the known board is $\le 1$ square (and no piece was lifted), the frame is recognized as `NO_CHANGE` (cursor hover, highlight fading, or drawn arrows), re-baselining the frame without incrementing uncertainty.
6. **Legal Move Bitmask Matching**: Pushes every legal move on a scratch board and evaluates:
   $$\text{mismatch} = \operatorname{popcount}\bigl((\text{board.white} \oplus \text{obs\_white}) \mid (\text{board.black} \oplus \text{obs\_black})\bigr)$$
   Candidates are deduplicated by resulting mask pairs (preferring Queen on pawn promotions) and tie-broken by pixel delta on departure and arrival squares.
7. **Unambiguous Acceptance**: Accepts the move only if:
   - $\text{best\_mismatch} \le 1$
   - $\text{best\_mismatch} < \text{mismatch\_known}$
   - The runner-up candidate with a different mask is worse by $\ge 2$ squares.
8. **Blitz Catchup & Turn Healing**: If no 1-ply match exists, evaluates 2-ply sequences; if still none and not in check, attempts a 1-ply search after a null move to correct missed turn bookkeeping.
9. **Mid-Drag Protection**: When a piece is lifted from its origin square without arriving at a destination square, LightAnalizer identifies the frame as mid-drag and returns `UNCERTAIN` *without* updating baseline frames. Once the piece settles on its destination square, the full move is cleanly resolved.

---

## 3. Project Structure

```
LightAnalizer/
├── engines/
│   └── stockfish.exe           # Stockfish UCI chess engine binary
├── data/
│   ├── lightanalizer.db        # SQLite database for opponent profiles & game history
│   └── themes/
│       └── neo/                # Official Chess.com Neo piece assets (PNG)
├── core/
│   ├── types.py                # Core domain types, SyncStatus, DiagnosticsData, CandidateMove
│   ├── game_state_manager.py   # Single authoritative coordinator & engine versioning
│   ├── board_state.py          # Board state, PGN/FEN history, legal move navigation
│   ├── engine_manager.py       # Asynchronous UCI engine manager, MultiPV, cancellation
│   ├── analyzer.py             # Chess reasoning, tactical motifs, king safety, grounded takeaways
│   ├── modes.py                # Operating mode manager (Analysis, Training, Live, Review)
│   ├── review.py               # Post-game move classification, accuracy %, critical moments
│   ├── opponent/               # SQLite persistence, empirical profiling & tendency predictor
│   │   ├── models.py           # Opponent, GameRecord, MoveObservation dataclasses
│   │   ├── repository.py       # SQLite repository with automatic schema migration
│   │   ├── profiler.py         # Empirical statistical profiler & repertoire builder
│   │   └── predictor.py        # Tactical & move prediction engine
│   └── vision/
│       ├── capture.py          # Native Qt multi-monitor high-DPI screen grabber
│       ├── screen_overlay.py   # Full-screen interactive Snipping-Tool board selector
│       ├── board_detector.py   # 8×8 checkerboard scoring, auto-detection & grid refinement
│       ├── piece_classifier.py # Dual-theme (Neo + Cburnett) multi-scale piece classifier
│       ├── piece_icon_bank.py  # Staunton figurine icon presence detector for GUI moves tabs
│       ├── notation_parser.py  # Zero-hallucination OCR parser with figurine disambiguation
│       ├── moves_tab_observer.py # Multi-frame confirmation & divergence-protected OCR observer
│       ├── session_recorder.py # 60-frame rolling buffer & incident capture (F9)
│       ├── move_inference.py   # Base move inference engine & opening book trees
│       ├── state_inference.py  # RobustMoveInference: 64-bit occupancy + move highlight matching
│       └── observer.py         # 2-frame stability gate, screen worker, auto-heal & telemetry
├── ui/
│   ├── styles.py               # Dark theme design tokens & QSS stylesheet
│   ├── widgets/
│   │   ├── chessboard.py       # Vector chessboard with candidate arrows, legal hints, coords
│   │   ├── eval_bar.py         # Vertical evaluation bar with smooth animation
│   │   ├── candidate_card.py   # Candidate move cards with engine badges, PV expander
│   │   ├── diagnostics_panel.py # Real-time latency, FEN, and rejection telemetry
│   │   ├── position_dialog.py  # Starting position & side modal (White/Black, openings, custom FEN)
│   │   └── move_list.py        # Notation table with move navigation controls
│   ├── views/
│   │   ├── analysis_view.py    # Primary live workspace (Mini/Full Board + Analysis cards)
│   │   ├── review_view.py      # Post-game review & accuracy dashboard
│   │   ├── opponent_view.py    # Opponent profiles, repertoire trees, game importer
│   │   ├── games_view.py       # PGN library, search, export
│   │   └── settings_view.py    # Engine parameters, threads, hash, depth, privacy tools
│   └── main_window.py          # Focused shell, HUD mode, hotkeys, status pill, diagnostics
├── tools/
│   └── replay_session.py       # Offline session replay tool for flagged incidents
├── tests/
│   ├── test_end_to_end_workflow.py # Full workflow verification & blitz catchup
│   ├── test_game_state.py      # State transitions, versioning, variation exploration
│   ├── test_moves_tab_tracking.py # Figurine icons, compound tokens, typo correction, FEN setup
│   ├── test_vision.py          # Vision pipeline, 2-frame stability gate, highlight matching
│   ├── test_board_state.py     # Chess rules, moves, castling, en passant, promotion
│   ├── test_analyzer.py        # Material balance, king safety, tactical motifs
│   ├── test_engine.py          # Stockfish MultiPV 3, cancellation, UCI protocol
│   ├── test_opponent.py        # SQLite persistence, profiling thresholds, predictions
│   ├── test_review.py          # Game review accuracy scoring, blunder classification
│   └── test_ui_lifecycle.py    # UI lifecycle, F9 incident capture, Backspace undo, orientation
├── main.py                     # Application entry point
├── run_lightanalizer.bat       # Windows 11 launcher script
└── conftest.py                 # Pytest Qt fixture configuration
```

---

## 4. Requirements & Installation

### Prerequisites
- **Operating System**: Windows 11 / Windows 10 (macOS / Linux supported via PySide6).
- **Python**: Version 3.10 or higher (tested on Python 3.14 on Windows 11).
- **Stockfish**: A Stockfish executable placed at `engines/stockfish.exe` (or configured via Settings).

### Installation

1. **Clone or download the repository**:
   ```powershell
   git clone https://github.com/your-username/LightAnalizer.git
   cd LightAnalizer
   ```

2. **Create and activate a virtual environment (recommended)**:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install required dependencies**:
   ```powershell
   pip install PySide6 python-chess opencv-contrib-python Pillow mss pytest anyio platformdirs
   ```

4. **Verify Stockfish engine binary**:
   Ensure `engines/stockfish.exe` is present in the `engines/` directory.

---

## 5. How to Run

### Using the Batch Launcher (Windows)
Double-click `run_lightanalizer.bat` or run in terminal:
```powershell
.\run_lightanalizer.bat
```

### Direct Terminal Launch
```powershell
python main.py
```

---

## 6. How to Use Screen Selection

### Method A: Select Moves Tab (Recommended)
1. Open your chess game on Chess.com, Lichess, or any chess GUI.
2. Click the prominent **📝 Select Moves Tab** button in the top navigation bar (or press `Ctrl+S` / `S`).
3. Click and drag a rectangle over the moves / notation panel where moves appear.
4. Click **Confirm Selection** (or press `Enter`).
5. LightAnalizer transcribes the moves in real time using local neural OCR. Whenever a player makes a move, it updates the board and immediately suggests the top 3 best moves with tactical evaluations.

### Method B: Select Board (Vision Mode)
1. Click the **Select Board (Vision)** button (or press `B`).
2. Use **Auto-Detect Board** or drag a rectangle over the 8×8 board.
3. Click **Confirm Selection**.

### Keyboard Shortcuts Reference
| Shortcut | Action |
|---|---|
| `Ctrl+S` or `S` | Select Moves Tab (OCR mode) |
| `B` | Select Board (Vision mode) |
| `Ctrl+P` | Position & Starting Side Dialog (White/Black, openings, custom FEN) |
| `F` | Toggle Player Side (White at bottom ⟷ Black at bottom) |
| `P` | Toggle `📌 Pin` (Floating Always-on-Top) |
| `C` | Toggle `🗗 Compact HUD` ⟷ `⛶ Expand` Full Desktop View |
| `M` | Toggle mini visual chessboard in Compact HUD mode |
| `F9` | Flag misdetected move & dump rolling 60-frame incident to `data/sessions/` |
| `Backspace` | Safety net: Undo last confirmed move ply |
| `Left` / `Right` | Step backward / forward through game move history |
| `D` | Toggle collapsible Diagnostics telemetry drawer |

---

## 7. Diagnostics & Offline Session Replayer

When an unexpected move is detected during live gameplay, simply press **`F9`**. LightAnalizer automatically captures the last 60 frames (the preceding ~20 seconds of gameplay) along with OCR bounding boxes, text, confidence scores, and FEN transitions into a self-contained bundle at:
```
data/sessions/incident_<timestamp>/
├── manifest.json
└── frame_000_moves_tab.png, frame_001_moves_tab.png, ...
```

To replay and inspect any incident offline:
```powershell
python tools/replay_session.py
```
Or specify a specific incident directory:
```powershell
python tools/replay_session.py data/sessions/incident_20261107_120000
```

---

## 8. Running Automated Tests

Run the comprehensive test suite (91 automated tests across all modules):

```powershell
python -m pytest -v
```

To run only the moves tab OCR tracking tests:
```powershell
python -m pytest tests/test_moves_tab_tracking.py -v
```

To run only the vision and move detection tests:
```powershell
python -m pytest tests/test_vision.py -v
```

To run UI lifecycle and hotkey tests:
```powershell
python -m pytest tests/test_ui_lifecycle.py -v
```

---

## 9. Fair-Play Notice

> [!IMPORTANT]
> **Use Responsibly**: LightAnalizer is designed strictly for study, training, analysis, post-game review, and commentary assistance. Using live engine suggestions during rated competitive matches against human opponents without mutual consent violates the fair-play policies and terms of service of major chess platforms (such as Chess.com and Lichess) and can result in account termination. Always respect fair-play regulations and tournament rules.

---

## 10. Known Limitations

- **Board Themes**: Optimized for high-contrast digital board themes, primarily Chess.com (*Neo* piece set on Green or Blue boards) and Lichess (*Cburnett* piece set on standard boards). Highly decorative 3D pieces or low-contrast custom marble textures may require manual calibration or clear contrast.
- **Mid-Drag & Move Hints**: When dragging a piece with the mouse or when legal-move dots are shown, the status pill will temporarily show `Synchronizing...`. Once the piece is dropped and the frame settles, the move synchronizes cleanly.
- **Platform Focus**: The screen capture and display affinity exclusion (`SetWindowDisplayAffinity`) are tailored for Windows 10 and 11.
