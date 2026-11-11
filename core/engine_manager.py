"""
Chess engine UCI management and asynchronous MultiPV search.
"""
from __future__ import annotations
import os
import sys
import threading
import time
from typing import List, Optional, Callable, Dict, Any
import chess
import chess.engine
from core.types import CandidateMove

class EngineConfig:
    def __init__(
        self,
        engine_path: Optional[str] = None,
        threads: int = 2,
        hash_mb: int = 128,
        depth: int = 15,
        time_limit_sec: float = 1.5,
        multipv: int = 3
    ):
        if engine_path is None:
            # Auto-locate engines/stockfish.exe relative to project root
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            candidate = os.path.join(base_dir, "engines", "stockfish.exe")
            if os.path.exists(candidate):
                self.engine_path = candidate
            else:
                self.engine_path = "stockfish"
        else:
            self.engine_path = engine_path

        self.threads = max(1, threads)
        self.hash_mb = max(16, hash_mb)
        self.depth = max(1, depth)
        self.time_limit_sec = max(0.2, time_limit_sec)
        self.multipv = max(1, multipv)

class EngineManager:
    """
    Manages UCI engine lifecycle, asynchronous MultiPV analysis,
    cancellation tokens, and graceful fallback.
    """
    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or EngineConfig()
        self._engine: Optional[chess.engine.SimpleEngine] = None
        self._active_analysis: Optional[chess.engine.AnalysisResult] = None
        self._lock = threading.Lock()
        self._current_search_id = 0
        self._is_active = False
        self._on_result_callbacks: List[Callable[[str, List[CandidateMove]], None]] = []
        self._on_error_callbacks: List[Callable[[str], None]] = []
        # FEN of the last position whose search fully completed (used to know when
        # candidates are final / stable, e.g. before auto-playing a move).
        self.last_final_fen: Optional[str] = None
        # Optional provider returning extra root moves (e.g. sacrifices) that should be
        # probed after the main MultiPV search so they can be evaluated by the engine.
        self.probe_moves_provider: Optional[Callable[[chess.Board, List[chess.Move]], List[chess.Move]]] = None
        self.probe_time_limit_sec: float = 0.9

    def add_result_callback(self, cb: Callable[[str, List[CandidateMove]], None]) -> None:
        if cb not in self._on_result_callbacks:
            self._on_result_callbacks.append(cb)

    def add_error_callback(self, cb: Callable[[str], None]) -> None:
        if cb not in self._on_error_callbacks:
            self._on_error_callbacks.append(cb)

    def start_engine(self) -> bool:
        with self._lock:
            if self._engine is not None:
                return True
            try:
                if not os.path.exists(self.config.engine_path):
                    # Check if stockfish is in PATH
                    pass
                self._engine = chess.engine.SimpleEngine.popen_uci(self.config.engine_path)
                try:
                    self._engine.configure({
                        "Threads": self.config.threads,
                        "Hash": self.config.hash_mb
                    })
                except Exception:
                    pass
                self._is_active = True
                return True
            except Exception as e:
                err_msg = f"Failed to launch UCI engine '{self.config.engine_path}': {e}"
                print(f"[EngineManager] {err_msg}")
                for cb in self._on_error_callbacks:
                    cb(err_msg)
                return False

    def stop_engine(self) -> None:
        with self._lock:
            self._current_search_id += 1
            if self._active_analysis is not None:
                try:
                    self._active_analysis.stop()
                except Exception:
                    pass
                self._active_analysis = None
            if self._engine is not None:
                try:
                    self._engine.quit()
                except Exception:
                    pass
                self._engine = None
            self._is_active = False

    def is_running(self) -> bool:
        with self._lock:
            return self._engine is not None

    def request_analysis(self, board: chess.Board, on_complete: Optional[Callable[[List[CandidateMove]], None]] = None) -> int:
        """
        Asynchronously requests MultiPV analysis for the given position.
        Automatically supersedes any prior pending or running search.
        """
        with self._lock:
            self._current_search_id += 1
            search_id = self._current_search_id
            if self._active_analysis is not None:
                try:
                    self._active_analysis.stop()
                except Exception:
                    pass
                self._active_analysis = None

        # Make a copy of board to analyze safely across threads
        board_copy = board.copy()
        fen = board_copy.fen()

        thread = threading.Thread(
            target=self._search_worker,
            args=(board_copy, search_id, on_complete),
            daemon=True
        )
        thread.start()
        return search_id

    def cancel_analysis(self) -> None:
        with self._lock:
            self._current_search_id += 1
            if self._active_analysis is not None:
                try:
                    self._active_analysis.stop()
                except Exception:
                    pass
                self._active_analysis = None

    def _search_worker(
        self,
        board: chess.Board,
        search_id: int,
        on_complete: Optional[Callable[[List[CandidateMove]], None]]
    ) -> None:
        fen = board.fen()
        # Verify engine is ready
        if not self.is_running():
            if not self.start_engine():
                # Fallback to heuristic candidate evaluation if engine not available
                candidates = self._fallback_evaluate(board)
                self.last_final_fen = fen
                self._dispatch_result(fen, candidates, search_id, on_complete)
                return

        with self._lock:
            if search_id != self._current_search_id or self._engine is None:
                return
            engine = self._engine

        try:
            multipv_count = min(self.config.multipv, len(list(board.legal_moves)))
            if multipv_count == 0:
                # Game over or no legal moves
                self._dispatch_result(fen, [], search_id, on_complete)
                return

            limit = chess.engine.Limit(
                depth=self.config.depth,
                time=self.config.time_limit_sec
            )

            multipv_dict: Dict[int, Dict[str, Any]] = {}
            last_dispatch_time = time.time()
            last_dispatch_depth = 0

            # Progressive streaming analysis: candidate moves appear in <10ms
            with engine.analysis(board, limit, multipv=multipv_count) as analysis:
                with self._lock:
                    if search_id != self._current_search_id:
                        analysis.stop()
                        return
                    self._active_analysis = analysis

                for info in analysis:
                    with self._lock:
                        if search_id != self._current_search_id:
                            analysis.stop()
                            break

                    mpv_idx = info.get("multipv", 1) or 1
                    if "pv" in info:
                        multipv_dict[mpv_idx] = info

                    curr_depth = info.get("depth", 0) or 0
                    now = time.time()
                    if len(multipv_dict) >= multipv_count and (curr_depth > last_dispatch_depth or (now - last_dispatch_time) >= 0.08):
                        sorted_infos = [multipv_dict[k] for k in sorted(multipv_dict.keys())]
                        intermediate_candidates = self._parse_engine_results(board, sorted_infos)
                        self._dispatch_result(fen, intermediate_candidates, search_id, None)
                        last_dispatch_depth = curr_depth
                        last_dispatch_time = now

                with self._lock:
                    if self._active_analysis == analysis:
                        self._active_analysis = None

            # Final dispatch when search completes
            with self._lock:
                if search_id != self._current_search_id:
                    return

            if multipv_dict:
                sorted_infos = [multipv_dict[k] for k in sorted(multipv_dict.keys())]
                candidates = self._parse_engine_results(board, sorted_infos)
                candidates = self._probe_extra_moves(engine, board, search_id, candidates)
                with self._lock:
                    if search_id != self._current_search_id:
                        return
                    self.last_final_fen = fen
                self._dispatch_result(fen, candidates, search_id, on_complete)

        except chess.engine.EngineTerminatedError:
            print("[EngineManager] Engine terminated unexpectedly. Reopening...")
            with self._lock:
                self._engine = None
                self._active_analysis = None
        except Exception as e:
            print(f"[EngineManager] Search error: {e}")
            candidates = self._fallback_evaluate(board)
            self.last_final_fen = fen
            self._dispatch_result(fen, candidates, search_id, on_complete)

    def _probe_extra_moves(
        self,
        engine: chess.engine.SimpleEngine,
        board: chess.Board,
        search_id: int,
        candidates: List[CandidateMove]
    ) -> List[CandidateMove]:
        """
        Evaluates extra root moves (e.g. sacrifices) that fell outside the top MultiPV lines
        and appends them to the candidate list so the Brilliant Farmer can consider them.
        """
        provider = self.probe_moves_provider
        if provider is None or not candidates:
            return candidates
        try:
            known = [c.move for c in candidates]
            extra = [m for m in provider(board, known) if m not in known and m in board.legal_moves]
            if not extra:
                return candidates

            limit = chess.engine.Limit(
                depth=self.config.depth,
                time=self.probe_time_limit_sec
            )
            probe_dict: Dict[int, Dict[str, Any]] = {}
            with engine.analysis(board, limit, multipv=len(extra), root_moves=extra) as analysis:
                with self._lock:
                    if search_id != self._current_search_id:
                        analysis.stop()
                        return candidates
                    self._active_analysis = analysis
                for info in analysis:
                    with self._lock:
                        if search_id != self._current_search_id:
                            analysis.stop()
                            break
                    if "pv" in info:
                        probe_dict[info.get("multipv", 1) or 1] = info
                with self._lock:
                    if self._active_analysis == analysis:
                        self._active_analysis = None

            if not probe_dict:
                return candidates

            best_eval = self._eval_value(candidates[0])
            probe_infos = [probe_dict[k] for k in sorted(probe_dict.keys())]
            probed = self._parse_engine_results(
                board, probe_infos, rank_offset=len(candidates), best_eval_ref=best_eval
            )
            for p in probed:
                p.is_best = False
            return list(candidates) + probed
        except chess.engine.EngineTerminatedError:
            raise
        except Exception as e:
            print(f"[EngineManager] Probe error: {e}")
            return candidates

    @staticmethod
    def _eval_value(cand: CandidateMove) -> float:
        if cand.score_cp is not None:
            return cand.score_cp / 100.0
        if cand.mate_in is not None:
            return 100.0 if cand.mate_in > 0 else -100.0
        return 0.0

    def _parse_engine_results(
        self,
        board: chess.Board,
        results: List[Dict[str, Any]],
        rank_offset: int = 0,
        best_eval_ref: Optional[float] = None
    ) -> List[CandidateMove]:
        candidates: List[CandidateMove] = []
        turn = board.turn
        best_score_cp: Optional[float] = best_eval_ref

        for idx, entry in enumerate(results):
            pv = entry.get("pv", [])
            if not pv:
                continue

            first_move = pv[0]
            san = board.san(first_move)

            # Convert PV to SAN list
            pv_san: List[str] = []
            temp_board = board.copy()
            for m in pv[:8]:  # show up to 8 moves of PV
                try:
                    pv_san.append(temp_board.san(m))
                    temp_board.push(m)
                except Exception:
                    break

            # Score extraction (PovScore from current player's perspective)
            score = entry.get("score")
            score_cp: Optional[int] = None
            mate_in: Optional[int] = None
            eval_str = "0.0"

            if score is not None:
                pov_score = score.pov(turn)
                if pov_score.is_mate():
                    mate_val = pov_score.mate()
                    mate_in = mate_val
                    eval_str = f"#{mate_val}" if mate_val > 0 else f"-#{-mate_val}"
                else:
                    score_cp = pov_score.score()
                    if score_cp is not None:
                        float_eval = score_cp / 100.0
                        eval_str = f"{float_eval:+.2f}"

            # Calculate eval difference relative to best move
            current_eval_val = (score_cp / 100.0) if score_cp is not None else (100.0 if (mate_in and mate_in > 0) else -100.0)
            if idx == 0 and best_score_cp is None:
                best_score_cp = current_eval_val
                eval_diff = 0.0
            else:
                eval_diff = round(current_eval_val - (best_score_cp or 0.0), 2)

            cand = CandidateMove(
                move=first_move,
                san=san,
                rank=idx + 1 + rank_offset,
                score_cp=score_cp,
                mate_in=mate_in,
                eval_str=eval_str,
                eval_diff=eval_diff,
                pv=pv,
                pv_san=pv_san,
                is_best=(idx == 0 and rank_offset == 0)
            )
            candidates.append(cand)

        return candidates

    def _fallback_evaluate(self, board: chess.Board) -> List[CandidateMove]:
        """Simple rule-based fallback if Stockfish is unavailable."""
        candidates = []
        piece_values = {
            chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
            chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0
        }
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return []

        scored_moves = []
        for m in legal_moves:
            score = 0
            if board.is_capture(m):
                captured = board.piece_at(m.to_square)
                if captured:
                    score += piece_values.get(captured.piece_type, 0)
            if board.gives_check(m):
                score += 50
            if m.to_square in [chess.E4, chess.D4, chess.E5, chess.D5]:
                score += 30
            scored_moves.append((score, m))

        scored_moves.sort(key=lambda x: x[0], reverse=True)
        for idx, (sc, m) in enumerate(scored_moves[:3]):
            san = board.san(m)
            cand = CandidateMove(
                move=m,
                san=san,
                rank=idx + 1,
                score_cp=sc,
                eval_str=f"{sc/100.0:+.2f}",
                eval_diff=0.0 if idx == 0 else round((sc - scored_moves[0][0]) / 100.0, 2),
                pv=[m],
                pv_san=[san],
                is_best=(idx == 0)
            )
            candidates.append(cand)
        return candidates

    def _dispatch_result(
        self,
        fen: str,
        candidates: List[CandidateMove],
        search_id: int,
        on_complete: Optional[Callable[[List[CandidateMove]], None]]
    ) -> None:
        with self._lock:
            if search_id != self._current_search_id:
                return

        for cb in self._on_result_callbacks:
            try:
                cb(fen, candidates)
            except Exception as e:
                print(f"[EngineManager] Callback error: {e}")

        if on_complete:
            try:
                on_complete(candidates)
            except Exception as e:
                print(f"[EngineManager] Completion callback error: {e}")
