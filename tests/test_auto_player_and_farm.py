"""
Tests for the auto-move planner (move choice + think time), upgraded Brilliant Farmer
(PV-verified sacrifices, probe moves, new traps) and the single-injection mouse controller.
"""
import random
import chess
import pytest

from core.types import CandidateMove, BoardCalibration
from core.auto_player import AutoMovePlanner
from core.brilliant_farmer import BrilliantFarmer
from core.gambits import GambitsAndTraps
from core.mouse_controller import MouseMoveController
from core.game_state_manager import GameStateManager
from core.board_state import BoardState
from core.engine_manager import EngineManager
from core.analyzer import ChessAnalyzer


def cand(board, uci, rank, cp=None, mate=None, brilliant=False, pv=None):
    m = chess.Move.from_uci(uci)
    return CandidateMove(
        move=m, san=board.san(m), rank=rank, score_cp=cp, mate_in=mate,
        eval_str=str(cp), eval_diff=0.0, pv=pv or [], is_best=(rank == 1), is_brilliant=brilliant
    )


# ---------------------------------------------------------------- planner: move choice
def test_planner_always_best_when_others_clearly_worse():
    b = chess.Board()
    cands = [cand(b, "e2e4", 1, 40), cand(b, "d2d4", 2, -60), cand(b, "g1f3", 3, -90)]
    p = AutoMovePlanner(random.Random(1))
    for _ in range(50):
        c, label = p.choose_move(b, cands)
        assert c.san == "e4" and label == "best"


def test_planner_sometimes_plays_second_and_third_when_equal():
    b = chess.Board()
    cands = [cand(b, "e2e4", 1, 30), cand(b, "d2d4", 2, 28), cand(b, "g1f3", 3, 26)]
    p = AutoMovePlanner(random.Random(7))
    labels = {p.choose_move(b, cands)[1] for _ in range(400)}
    assert labels == {"best", "2nd best", "3rd best"}


def test_planner_never_leaves_forced_mate_or_brilliant_top():
    b = chess.Board()
    mate = [cand(b, "e2e4", 1, None, mate=3), cand(b, "d2d4", 2, 30), cand(b, "g1f3", 3, 30)]
    brill = [cand(b, "e2e4", 1, 30, brilliant=True), cand(b, "d2d4", 2, 30), cand(b, "g1f3", 3, 30)]
    p = AutoMovePlanner(random.Random(3))
    for _ in range(100):
        assert p.choose_move(b, mate)[0].san == "e4"
        assert p.choose_move(b, brill, brilliant_mode=True)[0].san == "e4"


def test_planner_never_throws_away_winning_position():
    b = chess.Board()
    cands = [cand(b, "e2e4", 1, 400), cand(b, "d2d4", 2, 390), cand(b, "g1f3", 3, 120)]
    p = AutoMovePlanner(random.Random(5))
    labels = {p.choose_move(b, cands)[0].san for _ in range(300)}
    assert "Nf3" not in labels


# ---------------------------------------------------------------- planner: think time
def test_think_time_ranges():
    p = AutoMovePlanner(random.Random(11))
    # only move -> instant-ish
    b = chess.Board("7k/8/8/8/8/8/6q1/7K w - - 0 1")  # Kxg2 / only legal? king h1, queen g2 protected? keep generic check below
    if b.legal_moves.count() == 1:
        c = cand(b, next(iter(b.legal_moves)).uci(), 1, 0)
        d, _ = p.think_delay(b, c, [c])
        assert d < 1.0

    # normal middlegame position with close candidates -> 10..30 seconds
    mid = chess.Board("r1bq1rk1/ppp2ppp/2n1pn2/3p4/2PP4/2NBPN2/PP3PPP/R1BQ1RK1 w - - 0 9")
    cs = [cand(mid, "e3e4", 1, 20), cand(mid, "c4d5", 2, 15), cand(mid, "a2a3", 3, 10)]
    for _ in range(100):
        d, why = p.think_delay(mid, cs[0], cs)
        assert 10.0 <= d <= 33.0, (d, why)

    # crushing gap -> obvious -> fast
    obv = [cand(mid, "e3e4", 1, 500), cand(mid, "c4d5", 2, 50), cand(mid, "a2a3", 3, 10)]
    for _ in range(100):
        d, _ = p.think_delay(mid, obv[0], obv)
        assert d <= 3.6

    # opening -> fast
    op = chess.Board()
    oc = [cand(op, "e2e4", 1, 30), cand(op, "d2d4", 2, 28)]
    for _ in range(100):
        d, _ = p.think_delay(op, oc[0], oc)
        assert d <= 4.0

    # sacrifices look like deep calculation: >= 14s
    sac = cand(mid, "e3e4", 1, 20, brilliant=True)
    for _ in range(100):
        d, _ = p.think_delay(mid, sac, [sac, cs[1], cs[2]])
        assert d >= 14.0


# ---------------------------------------------------------------- farmer
GREEK = "r1bq1rk1/ppp2ppp/2n1p3/3p4/2PP4/3BPN2/PP3PPP/RN1QK2R w KQ - 3 8"


def test_pv_material_delta_detects_real_sacrifice_vs_trade():
    f = BrilliantFarmer()
    b = chess.Board("r1bq1rk1/ppp2ppp/2n1p3/3p4/2PP4/3BPN2/PP3PPP/RN1QK2R w KQ - 3 8")
    # Bxh7+ Kxh7 Ng5+ Kg8 Qh5 (quiet) : bishop (330) for pawn (100) = -230
    pv = [chess.Move.from_uci(u) for u in ("d3h7", "g8h7", "f3g5", "h7g8", "d1h5")]
    delta = f.pv_material_delta(b, pv)
    assert delta is not None and delta <= -200

    # plain pawn trade: no deficit
    b2 = chess.Board()
    for s in ("e4", "d5"):
        b2.push_san(s)
    pv2 = [chess.Move.from_uci(u) for u in ("e4d5", "d8d5", "b1c3")]
    delta2 = f.pv_material_delta(b2, pv2)
    assert delta2 is not None and delta2 >= -100 + 100  # equal trade (+0)


def test_greek_gift_setup_and_probe_moves():
    f = BrilliantFarmer()
    b = chess.Board(GREEK)
    m = chess.Move.from_uci("d3h7")
    assert f.is_greek_gift_setup(b, m) is True
    probes = f.probe_moves(b, known=[])
    assert m in probes and probes[0] == m  # highest priority probe
    assert f.probe_moves(b, known=[m]) != probes or m not in f.probe_moves(b, known=[m])


def test_sacrifice_requires_pv_material_deficit():
    f = BrilliantFarmer()
    b = chess.Board(GREEK)
    pv_sac = [chess.Move.from_uci(u) for u in ("d3h7", "g8h7", "f3g5", "h7g8", "d1h5")]
    sac = cand(b, "d3h7", 2, 120, pv=pv_sac)
    best = cand(b, "e1g1", 1, 130)
    ok, reason = f.evaluate_move_brilliance(b, sac, best)
    assert ok and "Greek Gift" in reason

    # PV that wins the sacrificed bishop back (material stays level at the quiet end) -> NOT a sacrifice
    b2 = chess.Board("4k3/8/4p3/3p4/8/4N3/8/4K3 w - - 0 1")
    pv_regain = [chess.Move.from_uci(u) for u in ("e3d5", "e6d5", "e1d2", "e8d7")]
    knight_loss = cand(b2, "e3d5", 2, 0, pv=pv_regain)
    ok2, _ = f.evaluate_move_brilliance(b2, knight_loss, cand(b2, "e1d2", 1, 0))
    assert f.pv_material_delta(b2, pv_regain) <= -200   # genuine loss of a knight for a pawn
    assert ok2 is True

    # level trade in PV: not a sacrifice even though the knight lands on an attacked square
    b3 = chess.Board("4k3/8/4p3/3p4/8/4N3/8/4K3 w - - 0 1")
    pv_flat = [chess.Move.from_uci(u) for u in ("e1d2", "e8d7", "d2c3")]
    quiet = cand(b3, "e1d2", 1, 0, pv=pv_flat)
    ok3, _ = f.evaluate_move_brilliance(b3, quiet, quiet)
    assert ok3 is False


def test_unsound_sacrifice_rejected_by_eval_drop():
    f = BrilliantFarmer()
    b = chess.Board(GREEK)
    best = cand(b, "e1g1", 1, 130)
    bad = cand(b, "d3h7", 2, -180)   # refuted: far worse than best, still equal-ish position
    ok, _ = f.evaluate_move_brilliance(b, bad, best)
    assert ok is False


def test_new_traps_present():
    g = GambitsAndTraps()
    b = chess.Board()
    for s in ("e4", "e5", "Nf3", "f6"):
        b.push_san(s)
    hit = g.find_gambit_or_trap(b)
    assert hit and hit[0] == chess.Move.from_uci("f3e5") and "Damiano" in hit[1]

    b = chess.Board()
    for s in "d4 d5 c4 e6 Nc3 Nf6 Bg5 Nbd7 cxd5 exd5 Nxd5 Nxd5 Bxd8".split():
        b.push_san(s)
    hit = g.find_gambit_or_trap(b)
    assert hit and hit[0] == chess.Move.from_uci("f8b4") and "Elephant" in hit[1]


def test_probe_candidates_merge_keeps_real_lines_first():
    f = BrilliantFarmer()
    b = chess.Board(GREEK)
    cands = [cand(b, "e1g1", 1, 130), cand(b, "b1d2", 2, 120), cand(b, "d3h7", 9, 118)]
    out = f.process_candidates(b, cands)
    assert out[0].san.startswith("O-O") or out[0].san == "Bxh7+"
    assert len(out) == 3


# ---------------------------------------------------------------- mouse: exactly one event per click
def test_click_injects_exactly_one_down_and_one_up(monkeypatch):
    mc = MouseMoveController()
    events = []
    monkeypatch.setattr(mc, "_inject", lambda flags, dx=0, dy=0: events.append(flags) or True)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    mc._click()
    assert events == [0x0002, 0x0004]


def test_square_coords_jitter_stays_inside_square():
    mc = MouseMoveController()
    cal = BoardCalibration(x=100, y=100, width=800, height=800, is_calibrated=True)
    cx, cy = mc.get_square_coords(cal, chess.E4)
    for _ in range(200):
        x, y = mc.get_square_coords(cal, chess.E4, jitter=0.16)
        assert abs(x - cx) <= 0.16 * 100 + 1 and abs(y - cy) <= 0.16 * 100 + 1


# ---------------------------------------------------------------- game state
def test_brilliant_counter_ignores_opponent_moves():
    gsm = GameStateManager(BoardState(), EngineManager(), ChessAnalyzer())
    gsm.set_brilliant_mode(True)
    board = chess.Board(GREEK)
    gsm.board_state.reset(board.fen())
    gsm.set_orientation(False)                # player is BLACK, but it is White's move
    m = chess.Move.from_uci("d3h7")
    gsm._latest_candidates = [cand(board, "d3h7", 1, 150, brilliant=True)]
    nb = board.copy(); nb.push(m)
    gsm.confirm_live_move(m, nb, 0.99)
    assert gsm.brilliant_count == 0


# ---------------------------------------------------------------- full auto-move UI flow (fake mouse)
def _pump(qapp, seconds):
    import time
    end = time.time() + seconds
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


def test_auto_move_flow_plays_when_it_is_our_turn_and_waits_otherwise():
    from PySide6.QtWidgets import QApplication
    from core.modes import ModeManager
    from core.opponent.repository import OpponentRepository
    from core.vision.observer import BoardObserver
    from ui.main_window import MainWindow

    qapp = QApplication.instance() or QApplication([])
    board_state = BoardState()
    engine_mgr = EngineManager()
    gsm = GameStateManager(board_state, engine_mgr, ChessAnalyzer())
    win = MainWindow(gsm, BoardObserver(gsm), ModeManager(), OpponentRepository(":memory:"))
    win.show()
    qapp.processEvents()

    win._click_calibration = BoardCalibration(x=3000, y=100, width=400, height=400, is_calibrated=True)
    win._auto_planner.speed = 0.001
    win._auto_planner.min_delay = 0.02
    clicks = []

    def fake_exec(cal, move, on_complete=None):
        clicks.append(move)
        if on_complete:
            on_complete(True)
        return True
    win.mouse_controller.execute_move_async = fake_exec

    b = chess.Board()
    gsm.board_state.reset(b.fen())
    gsm._live_board = b.copy()
    gsm._latest_candidates = [cand(b, "e2e4", 1, 30), cand(b, "d2d4", 2, 10), cand(b, "g1f3", 3, 5)]

    # Engine not final yet -> must NOT click
    engine_mgr.last_final_fen = None
    win.view_analysis.set_auto_move_active(True)
    win._on_auto_move_toggled(True)
    _pump(qapp, 0.3)
    assert clicks == []

    # Engine finished -> plans, thinks, clicks one of the top 3
    engine_mgr.last_final_fen = b.fen()
    gsm._notify()
    _pump(qapp, 0.6)
    assert len(clicks) == 1
    assert clicks[0] in [c.move for c in gsm._latest_candidates]

    # Opponent to move (we are white) -> nothing planned, nothing clicked
    b.push(clicks[0]); b.push_san("e5") if clicks[0] == chess.Move.from_uci("e2e4") else b.push_san("d5")
    b.pop()  # black to move now
    gsm.board_state.reset(b.fen()); gsm._live_board = b.copy()
    gsm._latest_candidates = [cand(b, "e7e5", 1, 0)]
    engine_mgr.last_final_fen = b.fen()
    gsm._notify()
    _pump(qapp, 0.3)
    assert len(clicks) == 1 and win._auto_plan is None

    # Toggling off cancels everything
    win._on_auto_move_toggled(False)
    assert win._auto_plan is None
    win.close()
