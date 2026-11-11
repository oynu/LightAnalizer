"""
Automated tests for OpponentRepository, OpponentProfiler, and OpponentPredictor.
"""
import os
import tempfile
import pytest
import chess
from core.types import ConfidenceLevel, CandidateMove
from core.opponent.models import Opponent, GameRecord, MoveObservation
from core.opponent.repository import OpponentRepository
from core.opponent.profiling import OpponentProfiler
from core.opponent.predictor import OpponentPredictor

@pytest.fixture
def temp_repo():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    repo = OpponentRepository(db_path=path)
    yield repo
    if os.path.exists(path):
        os.remove(path)

def test_opponent_creation_and_retrieval(temp_repo):
    opp = temp_repo.get_or_create_opponent("Kasparov [Fixture]", rating=2800)
    assert opp.id is not None
    assert opp.name == "Kasparov [Fixture]"
    assert opp.rating == 2800

    retrieved = temp_repo.get_opponent_by_id(opp.id)
    assert retrieved is not None
    assert retrieved.name == "Kasparov [Fixture]"

def test_profile_with_insufficient_data(temp_repo):
    opp = temp_repo.get_or_create_opponent("New Player", rating=1500)
    profiler = OpponentProfiler(temp_repo)
    insights = profiler.generate_profile_insights(opp.id)
    assert len(insights) >= 1
    assert insights[0].confidence == ConfidenceLevel.HYPOTHESIS
    assert insights[0].sample_size == 0

def test_pattern_extraction_and_confidence_levels(temp_repo):
    opp = temp_repo.get_or_create_opponent("Sicilian Specialist [Fixture]", rating=2200)
    
    # Record 6 games where opponent plays 1...c5 against 1.e4
    for i in range(6):
        g = GameRecord(
            opponent_id=opp.id,
            white="User",
            black=opp.name,
            result="0-1",
            date="2026.01.01",
            eco="B20",
            opening_name="Sicilian Defense",
            pgn="1. e4 c5 0-1"
        )
        moves = [
            MoveObservation(move_ply=1, fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", move_san="e4"),
            MoveObservation(move_ply=2, fen_before="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1", move_san="c5"),
        ]
        # In 4 of the games, add a blunder under pin
        if i < 4:
            moves.append(MoveObservation(
                move_ply=10,
                fen_before="r1bqk2r/pp1ppppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 2 5",
                move_san="d6",
                is_blunder=True,
                blunder_category="absolute pin",
                eval_loss=250
            ))
        temp_repo.record_game(g, moves)

    profiler = OpponentProfiler(temp_repo)
    insights = profiler.generate_profile_insights(opp.id)

    # Check opening tendency insight
    opening_ins = next((i for i in insights if i.category == "Opening" and "1.e4" in i.title), None)
    assert opening_ins is not None
    assert opening_ins.confidence == ConfidenceLevel.CONFIRMED
    assert opening_ins.sample_size == 6

    # Check tactical vulnerability insight
    tactical_ins = next((i for i in insights if i.category == "Tactical"), None)
    assert tactical_ins is not None
    assert "pin" in tactical_ins.title.lower()

def test_practical_prediction_system(temp_repo):
    opp = temp_repo.get_or_create_opponent("Predictable Opponent [Fixture]")
    fen_start = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"

    # Record 3 games playing c5 from this FEN
    for _ in range(3):
        g = GameRecord(opponent_id=opp.id, white="User", black=opp.name, result="*", pgn="1. e4 c5")
        moves = [
            MoveObservation(move_ply=1, fen_before="start", move_san="e4"),
            MoveObservation(move_ply=2, fen_before=fen_start, move_san="c5")
        ]
        temp_repo.record_game(g, moves)

    predictor = OpponentPredictor(temp_repo)
    board = chess.Board()
    board.push_san("e4")

    engine_cands = [
        CandidateMove(move=chess.Move.from_uci("e7e5"), san="e5", rank=1, eval_str="+0.3", pv=[chess.Move.from_uci("e7e5"), chess.Move.from_uci("g1f3")])
    ]

    result = predictor.predict_tendency(board, opp.id, engine_cands)
    # The opponent's historically preferred move is c5 even though engine evaluated e5
    assert result.predicted_opponent_move == "c5"
    assert result.sample_size == 3
    assert result.predicted_move_confidence in [ConfidenceLevel.EMERGING, ConfidenceLevel.CONFIRMED]
    assert "c5" in result.predicted_evidence

def test_persistence_across_reopen(temp_repo):
    db_path = temp_repo.db_path
    opp = temp_repo.get_or_create_opponent("Persistent Player", rating=1950)
    opp_id = opp.id

    # Reopen database with new instance
    repo2 = OpponentRepository(db_path=db_path)
    loaded = repo2.get_opponent_by_id(opp_id)
    assert loaded is not None
    assert loaded.name == "Persistent Player"
    assert loaded.rating == 1950
