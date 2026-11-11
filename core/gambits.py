"""
Gambits and Tactical Traps Engine:
Curated database of high-impact gambits, opening traps, and sacrifice lines that yield
Brilliant Moves (!!) on Chess.com and Lichess.
Matches current board positions to promote exciting, sacrificial, and aggressive tactical play.
"""
from __future__ import annotations
from typing import Optional, Tuple, Dict, List
import chess

class GambitTrapEntry:
    def __init__(
        self,
        name: str,
        fen_pattern: str,
        move_uci: str,
        move_san: str,
        sacrifice_type: str,
        tactical_idea: str,
        side: chess.Color
    ):
        self.name = name
        self.fen_pattern = fen_pattern
        self.move_uci = move_uci
        self.move_san = move_san
        self.sacrifice_type = sacrifice_type
        self.tactical_idea = tactical_idea
        self.side = side

class GambitsAndTraps:
    """
    Curated repository of opening gambits and tactical traps known to farm Brilliant (!!) moves.
    """

    def __init__(self):
        self._entries: List[GambitTrapEntry] = []
        self._build_database()

    def _add(
        self,
        name: str,
        fen_or_moves: str,
        move_uci: str,
        move_san: str,
        sacrifice_type: str,
        tactical_idea: str,
        side: chess.Color
    ) -> None:
        """Registers a gambit/trap line either by exact FEN or SAN move sequence."""
        if "/" in fen_or_moves:
            # Direct FEN string
            fen = fen_or_moves.split(" ")[0]
        else:
            # Move sequence from starting position
            b = chess.Board()
            for san in fen_or_moves.split():
                b.push_san(san)
            fen = b.board_fen()

        self._entries.append(
            GambitTrapEntry(
                name=name,
                fen_pattern=fen,
                move_uci=move_uci,
                move_san=move_san,
                sacrifice_type=sacrifice_type,
                tactical_idea=tactical_idea,
                side=side
            )
        )

    def find_gambit_or_trap(self, board: chess.Board) -> Optional[Tuple[chess.Move, str, str, str]]:
        """
        Checks if the current position matches a known high-yield gambit or trap.
        Returns (move, name, sacrifice_type, tactical_idea) or None.
        """
        curr_fen = board.board_fen()
        turn = board.turn

        for entry in self._entries:
            if entry.side == turn and entry.fen_pattern == curr_fen:
                move = chess.Move.from_uci(entry.move_uci)
                if move in board.legal_moves:
                    return (move, entry.name, entry.sacrifice_type, entry.tactical_idea)

        return None

    def _build_database(self) -> None:
        # =========================================================================
        # 1. WHITE GAMBITS & TRAPS (1. e4 & 1. d4)
        # =========================================================================

        # Evans Gambit: 1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 -> 4. b4!!
        self._add(
            name="Evans Gambit",
            fen_or_moves="e4 e5 Nf3 Nc6 Bc4 Bc5",
            move_uci="b2b4",
            move_san="b4",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Sacrifices b4 pawn to deflect black bishop, seizing total center control with c3 and d4",
            side=chess.WHITE
        )

        # Evans Gambit Followup: after 4. b4 Bxb4 5. c3 Ba5 -> 6. d4!
        self._add(
            name="Evans Gambit Center Breakthrough",
            fen_or_moves="e4 e5 Nf3 Nc6 Bc4 Bc5 b4 Bxb4 c3 Ba5",
            move_uci="d2d4",
            move_san="d4",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Blows open the center with d4, unleashing dynamic king-side attacking diagonal",
            side=chess.WHITE
        )

        # King's Gambit: 1. e4 e5 -> 2. f4!!
        self._add(
            name="King's Gambit",
            fen_or_moves="e4 e5",
            move_uci="f2f4",
            move_san="f4",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Sacrifices f-pawn to deflect Black e-pawn and open the devastating f-file for the rook",
            side=chess.WHITE
        )

        # Danish Gambit: 1. e4 e5 2. d4 exd4 -> 3. c3!!
        self._add(
            name="Danish Gambit",
            fen_or_moves="e4 e5 d4 exd4",
            move_uci="c2c3",
            move_san="c3",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Offers c-pawn to accelerate rapid development and aim monstrous bishop battery at f7 and g7",
            side=chess.WHITE
        )

        # Danish Double Gambit: after 3. c3 dxc3 -> 4. Bc4!!
        self._add(
            name="Danish Double Bishop Sacrifice",
            fen_or_moves="e4 e5 d4 exd4 c3 dxc3",
            move_uci="f1c4",
            move_san="Bc4",
            sacrifice_type="Piece/Pawn Sacrifice",
            tactical_idea="Sacrifices second pawn on b2 to station twin bishops cutting down Black king's fortress",
            side=chess.WHITE
        )

        # Smith-Morra Gambit against Sicilian: 1. e4 c5 2. d4 cxd4 -> 3. c3!!
        self._add(
            name="Smith-Morra Gambit",
            fen_or_moves="e4 c5 d4 cxd4",
            move_uci="c2c3",
            move_san="c3",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Sacrifices c-pawn against the Sicilian to open c & d files for rapid rook attacks against Black queen",
            side=chess.WHITE
        )

        # Smith-Morra Acceptance: after 3. c3 dxc3 -> 4. Nxc3
        self._add(
            name="Smith-Morra Development",
            fen_or_moves="e4 c5 d4 cxd4 c3 dxc3",
            move_uci="b1c3",
            move_san="Nxc3",
            sacrifice_type="Gambit Momentum",
            tactical_idea="Recaptures with active knight controlling d5 and preparing devastating Nd5 tactical jumps",
            side=chess.WHITE
        )

        # Scotch Gambit: 1. e4 e5 2. Nf3 Nc6 3. d4 exd4 -> 4. Bc4!!
        self._add(
            name="Scotch Gambit",
            fen_or_moves="e4 e5 Nf3 Nc6 d4 exd4",
            move_uci="f1c4",
            move_san="Bc4",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Ignores pawn recovery to immediately mobilize bishop targeting vulnerable f7 square",
            side=chess.WHITE
        )

        # Fried Liver Attack: 1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 -> 6. Nxf7!!
        self._add(
            name="Fried Liver Attack (Knight Sacrifice)",
            fen_or_moves="e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5",
            move_uci="g5f7",
            move_san="Nxf7",
            sacrifice_type="Knight Sacrifice",
            tactical_idea="Sacrifices knight on f7 dragging Black king into the center for a lethal mating net",
            side=chess.WHITE
        )

        # Legal's Mate Trap: 1. e4 e5 2. Nf3 Nc6 3. Bc4 d6 4. Nc3 Bg4 5. h3 Bh5 -> 6. Nxe5!!
        self._add(
            name="Legal's Mate Trap (Queen Sacrifice)",
            fen_or_moves="e4 e5 Nf3 Nc6 Bc4 d6 Nc3 Bg4 h3 Bh5",
            move_uci="f3e5",
            move_san="Nxe5",
            sacrifice_type="Queen Sacrifice",
            tactical_idea="Sacrifices queen on d1! If Black takes Bxd1, White plays 7. Bxf7+ Ke7 8. Nd5# checkmate!",
            side=chess.WHITE
        )

        # Vienna Gambit: 1. e4 e5 2. Nc3 Nc6 -> 3. f4!!
        self._add(
            name="Vienna Gambit",
            fen_or_moves="e4 e5 Nc3 Nc6",
            move_uci="f2f4",
            move_san="f4",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Strikes at e5 with f4 pawn sacrifice, controlling d4 and accelerating king-side attack",
            side=chess.WHITE
        )

        # Vienna Gambit vs 2... Nf6: 1. e4 e5 2. Nc3 Nf6 -> 3. f4!!
        self._add(
            name="Vienna Gambit",
            fen_or_moves="e4 e5 Nc3 Nf6",
            move_uci="f2f4",
            move_san="f4",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Aggressive f4 sacrifice challenging central control and preparing e5 push",
            side=chess.WHITE
        )

        # Halloween Gambit: 1. e4 e5 2. Nf3 Nc6 3. Nc3 Nf6 -> 4. Nxe5!!
        self._add(
            name="Halloween Gambit",
            fen_or_moves="e4 e5 Nf3 Nc6 Nc3 Nf6",
            move_uci="f3e5",
            move_san="Nxe5",
            sacrifice_type="Knight Sacrifice",
            tactical_idea="Sacrifices knight on e5 to roll center pawns forward with d4 and e5, suffocating black pieces",
            side=chess.WHITE
        )

        # Cochrane Gambit against Petroff: 1. e4 e5 2. Nf3 Nf6 3. Nxe5 d6 -> 4. Nxf7!!
        self._add(
            name="Cochrane Gambit",
            fen_or_moves="e4 e5 Nf3 Nf6 Nxe5 d6",
            move_uci="e5f7",
            move_san="Nxf7",
            sacrifice_type="Knight Sacrifice",
            tactical_idea="Sacrifices knight on f7 stripping king shelter and forcing king to wander into open crossfire",
            side=chess.WHITE
        )

        # Wing Gambit vs Sicilian: 1. e4 c5 -> 2. b4!!
        self._add(
            name="Wing Gambit",
            fen_or_moves="e4 c5",
            move_uci="b2b4",
            move_san="b4",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Deflects c5 pawn to seize full center domination with d4",
            side=chess.WHITE
        )

        # French Defense Milner-Barry Gambit: 1. e4 e6 2. d4 d5 3. e5 c5 4. c3 Nc6 5. Nf3 Qb6 6. Bd3 cxd4 7. cxd4 Bd7 -> 8. O-O!!
        self._add(
            name="Milner-Barry Gambit",
            fen_or_moves="e4 e6 d4 d5 e5 c5 c3 Nc6 Nf3 Qb6 Bd3 cxd4 cxd4 Bd7",
            move_uci="e1g1",
            move_san="O-O",
            sacrifice_type="En Prise Pawn Sacrifice",
            tactical_idea="Sacrifices d4 pawn to rapidly develop knights and rooks for an irresistible king-side assault",
            side=chess.WHITE
        )

        # Blackmar-Diemer Gambit: 1. d4 d5 2. e4 dxe4 -> 3. Nc3 Nf6 4. f3!!
        self._add(
            name="Blackmar-Diemer Gambit",
            fen_or_moves="d4 d5 e4 dxe4 Nc3 Nf6",
            move_uci="f2f3",
            move_san="f3",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Sacrifices f3 pawn to achieve massive lead in development and open f-file battery",
            side=chess.WHITE
        )

        # =========================================================================
        # 2. BLACK GAMBITS & TRAPS (1... e5, 1... c5, 1... Nf6)
        # =========================================================================

        # Traxler Counter-Attack: 1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 -> 4... Bc5!!
        self._add(
            name="Traxler Counter-Attack",
            fen_or_moves="e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5",
            move_uci="f8c5",
            move_san="Bc5",
            sacrifice_type="Piece Sacrifice",
            tactical_idea="Ignores f7 attack to sacrifice bishop/rook, preparing ...Bxf2+ and lethal king counter-strike",
            side=chess.BLACK
        )

        # Traxler Bishop Blow: 1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 Bc5 5. Nxf7 -> 5... Bxf2+!!
        self._add(
            name="Traxler Bishop Sacrifice",
            fen_or_moves="e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 Bc5 Nxf7",
            move_uci="c5f2",
            move_san="Bxf2+",
            sacrifice_type="Bishop Sacrifice",
            tactical_idea="Shatters White's king position with check, opening devastating queen and rook lines",
            side=chess.BLACK
        )

        # Stafford Gambit: 1. e4 e5 2. Nf3 Nf6 3. Nxe5 -> 3... Nc6!!
        self._add(
            name="Stafford Gambit",
            fen_or_moves="e4 e5 Nf3 Nf6 Nxe5",
            move_uci="b8c6",
            move_san="Nc6",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Offers pawn sacrifice on e5 to open diagonals for both bishops and queen against White king",
            side=chess.BLACK
        )

        # Budapest Gambit: 1. d4 Nf6 2. c4 -> 2... e5!!
        self._add(
            name="Budapest Gambit",
            fen_or_moves="d4 Nf6 c4",
            move_uci="e7e5",
            move_san="e5",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Sacrifices e-pawn to disrupt White's pawn center and activate dynamic piece pressure on e5 and c4",
            side=chess.BLACK
        )

        # Benko Gambit: 1. d4 Nf6 2. c4 c5 3. d5 -> 3... b5!!
        self._add(
            name="Benko Gambit",
            fen_or_moves="d4 Nf6 c4 c5 d5",
            move_uci="b7b5",
            move_san="b5",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Sacrifices b-pawn to open a and b files for permanent positional pressure on White queenside",
            side=chess.BLACK
        )

        # Albin Counter-Gambit: 1. d4 d5 2. c4 -> 2... e5!!
        self._add(
            name="Albin Counter-Gambit",
            fen_or_moves="d4 d5 c4",
            move_uci="e7e5",
            move_san="e5",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Counter-sacrifices e-pawn to lodge a thorn pawn on d3, setting up underpromotion traps",
            side=chess.BLACK
        )

        # Englund Gambit: 1. d4 -> 1... e5!!
        self._add(
            name="Englund Gambit",
            fen_or_moves="d4",
            move_uci="e7e5",
            move_san="e5",
            sacrifice_type="Pawn Sacrifice",
            tactical_idea="Immediately sacrifices e-pawn setting up quick queen tricks and back-rank mating traps",
            side=chess.BLACK
        )

        # Fishing Pole Trap: after 1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6 4. O-O Ng4 5. h3 -> 5... h5!!
        self._add(
            name="Fishing Pole Trap",
            fen_or_moves="e4 e5 Nf3 Nc6 Bb5 Nf6 O-O Ng4 h3",
            move_uci="h7h5",
            move_san="h5",
            sacrifice_type="Knight Sacrifice Trap",
            tactical_idea="Leaves knight on g4 en prise! If White plays hxg4, Black recaptures hxg4 opening the h-file with mate",
            side=chess.BLACK
        )

        # Blackburne Shilling Gambit: 1. e4 e5 2. Nf3 Nc6 3. Bc4 -> 3... Nd4!?
        self._add(
            name="Blackburne Shilling Gambit",
            fen_or_moves="e4 e5 Nf3 Nc6 Bc4",
            move_uci="c6d4",
            move_san="Nd4",
            sacrifice_type="Pawn Sacrifice Trap",
            tactical_idea="Baits White into 4. Nxe5? where Black unleashes 4... Qg5! winning queen or checkmating",
            side=chess.BLACK
        )
