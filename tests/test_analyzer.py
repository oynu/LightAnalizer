"""
Automated tests for ChessAnalyzer: tactical motifs, positional factors, and explanations.
"""
import pytest
import chess
from core.analyzer import ChessAnalyzer
from core.types import CandidateMove

def test_material_balance():
    analyzer = ChessAnalyzer()
    # Starting position
    b_start = chess.Board()
    w_mat, b_mat = analyzer._compute_material(b_start)
    assert w_mat == b_mat

    # Board with extra queen for White
    b_extra_q = chess.Board("rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    w_mat, b_mat = analyzer._compute_material(b_extra_q)
    assert w_mat - b_mat == 900  # Queen = 900 cp

def test_king_safety():
    analyzer = ChessAnalyzer()
    # Castled safe king
    b_safe = chess.Board("r1bq1rk1/pppp1ppp/2n2n2/4p3/1b2P3/2NP1N2/PPP1BPPP/R1BQK2R w KQkq - 4 6")
    ks_black = analyzer._evaluate_king_safety(b_safe, chess.BLACK)
    assert "Secure" in ks_black or "Safe" in ks_black

    # Exposed king with open files
    b_exposed = chess.Board("rnbqkbnr/pppp1p1p/8/6p1/4Pp2/5N2/PPPP2PP/RNBQKB1R w KQkq - 0 4")
    ks_white = analyzer._evaluate_king_safety(b_exposed, chess.WHITE)
    assert ks_white is not None

def test_hanging_pieces_detection():
    analyzer = ChessAnalyzer()
    # Undefended bishop on b4 attacked by a3 or pawn
    b_hanging = chess.Board("rnbqk1nr/pppp1ppp/8/4p3/1b2P3/3P4/PPP2PPP/RNBQKBNR w KQkq - 1 3")
    # b4 bishop is attacked? Not yet. Let's create an attacked undefended piece:
    b_att = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    # d5 is attacked by e4 (1 attacker vs 1 defender Q)
    threats = analyzer._find_hanging_and_threatened_pieces(b_att, chess.BLACK)
    assert isinstance(threats, list)

    # Completely hanging knight on e5 attacked by pawn on d4
    b_undef = chess.Board("4k3/8/8/4n3/3P4/8/8/4K3 w - - 0 1")
    threats_black = analyzer._find_hanging_and_threatened_pieces(b_undef, chess.BLACK)
    assert any("knight" in t.lower() for t in threats_black)

def test_fork_detection():
    analyzer = ChessAnalyzer()
    # Knight fork on King (e8) and Rook (a8) from c7
    b_fork_setup = chess.Board("r3k3/8/8/2N5/8/8/8/4K3 w - - 0 1")
    fork_move = chess.Move.from_uci("c5a6")  # wait, Nc5 to c7 or e6?
    # Move knight from d5 to c7: attacks e8 (king) and a8 (rook)
    b_setup2 = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1")
    motifs = analyzer._detect_move_tactics(b_setup2, chess.Move.from_uci("d5c7"))
    assert any("fork" in m.lower() for m in motifs)

def test_pin_detection():
    analyzer = ChessAnalyzer()
    # White bishop on b5 pins black knight on c6 to king on e8 (pawn on d5)
    b_pin = chess.Board("r1bqk2r/pp3ppp/2n5/1B1pp3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 6")
    assert b_pin.is_pinned(chess.BLACK, chess.C6)

def test_candidate_explanations_grounded():
    analyzer = ChessAnalyzer()
    b = chess.Board()
    cand1 = CandidateMove(
        move=chess.Move.from_uci("e2e4"),
        san="e4",
        rank=1,
        score_cp=25,
        eval_str="+0.25",
        is_best=True
    )
    cand2 = CandidateMove(
        move=chess.Move.from_uci("g1f3"),
        san="Nf3",
        rank=2,
        score_cp=15,
        eval_str="+0.15",
        eval_diff=-0.10,
        is_best=False
    )
    summary = analyzer.analyze_position(b, [cand1, cand2])
    assert summary.coach_takeaway != ""
    assert cand1.short_explanation != ""
    assert cand2.short_explanation != ""
    assert not cand1.tactical_motifs or isinstance(cand1.tactical_motifs, list)
