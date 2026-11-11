"""
Robust chess notation parser for OCR-extracted text and tokens.
Parses SAN moves, handles OCR misrecognitions, figurine notation,
row/column table layouts, and filters noise (evals, clocks, move numbers).
"""
from __future__ import annotations
import re
import logging
from typing import List, Tuple, Optional, Any
import chess

logger = logging.getLogger(__name__)

# Figurine Unicode mappings to standard SAN piece letters
FIGURINE_MAP = {
    '♔': 'K', '♕': 'Q', '♖': 'R', '♗': 'B', '♘': 'N', '♙': '',
    '♚': 'K', '♛': 'Q', '♜': 'R', '♝': 'B', '♞': 'N', '♟': '',
}

# Regex to detect move numbers (e.g., '1.', '24.', '1...', '1', '24')
MOVE_NUMBER_RE = re.compile(r'^[0-9Il]{1,3}[\.:]{0,3}$')

# Regex to detect clocks (e.g., '3:00', '0:45', '10:00', '1.5s', '0.8s')
CLOCK_RE = re.compile(r'^\d+:\d{2}$|^\d+(\.\d+)?s$')

# Regex to detect evaluation scores (e.g., '+0.3', '-1.5', '+M3', '-M2', '#1')
EVAL_RE = re.compile(r'^[+-]?(\d+(\.\d+)?|M\d+)$|^#\d+$')

# Regex to detect percentages or win probabilities (e.g., '98.5%', '50%')
PERCENT_RE = re.compile(r'^\d+(\.\d+)?%$')

# Ignored GUI header labels and non-move words
IGNORED_WORDS = {
    'MOVES', 'ANALYSIS', 'GAME', 'WHITE', 'BLACK', 'BLUNDER', 'MISTAKE',
    'INACCURACY', 'BEST', 'EXCELLENT', 'GREAT', 'BRILLIANT', 'BOOK',
    'FORCED', 'MISSED', 'TIME', 'CLOCK', 'DEPTH', 'EVAL', 'RESULT',
    '1-0', '0-1', '1/2-1/2', '½-½', 'DRAW', 'RESIGN', 'ABANDONED',
    'PLAY', 'ENGINE', 'STOCKFISH', 'LIVE'
}

def group_boxes_into_rows(ocr_items: List[Any], y_thresh: Optional[float] = None) -> List[List[Any]]:
    """
    Groups OCR items into horizontal lines/rows based on their Y center coordinates,
    then sorts items within each row from left to right (by X center).
    
    Each item is expected to be a tuple: (box, text, score).
    box is [[x1, y1], [x2, y1], [x2, y2], [x1, y2]].
    """
    if not ocr_items:
        return []

    # Calculate dynamic line threshold based on median/average box height
    if y_thresh is None:
        heights = []
        for item in ocr_items:
            try:
                box = item[0]
                h = max(p[1] for p in box) - min(p[1] for p in box)
                if h > 3:
                    heights.append(h)
            except Exception:
                pass
        if heights:
            avg_h = sum(heights) / len(heights)
            actual_y_thresh = max(11.0, avg_h * 0.55)
        else:
            actual_y_thresh = 14.0
    else:
        actual_y_thresh = y_thresh

    parsed = []
    for item in ocr_items:
        box = item[0]
        text = str(item[1]).strip()
        score = float(item[2]) if len(item) > 2 else 1.0
        if not text:
            continue
        try:
            cy = sum(p[1] for p in box) / 4.0
            cx = sum(p[0] for p in box) / 4.0
        except Exception:
            cy, cx = 0.0, 0.0
        parsed.append((cx, cy, text, score, item))

    # Sort primarily by vertical position (cy)
    parsed.sort(key=lambda x: x[1])

    rows: List[List[Tuple[float, float, str, float, Any]]] = []
    for item in parsed:
        cx, cy = item[0], item[1]
        placed = False
        for row in rows:
            row_avg_cy = sum(r[1] for r in row) / len(row)
            if abs(cy - row_avg_cy) <= actual_y_thresh:
                row.append(item)
                placed = True
                break
        if not placed:
            rows.append([item])

    # Sort each row horizontally (cx: left to right)
    sorted_rows: List[List[Any]] = []
    for row in rows:
        row.sort(key=lambda x: x[0])
        sorted_rows.append([r[4] for r in row])

    return sorted_rows


def is_ignorable_token(token: str) -> bool:
    """Checks if a string token is noise (clock, eval, move number, GUI label)."""
    t = token.strip()
    if not t:
        return True
    upper = t.upper().rstrip('.:;,')
    if upper in IGNORED_WORDS:
        return True
    if MOVE_NUMBER_RE.match(t):
        return True
    if CLOCK_RE.match(t):
        return True
    if EVAL_RE.match(t):
        return True
    if PERCENT_RE.match(t):
        return True
    return False


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Computes Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def clean_ocr_token(raw_token: str) -> str:
    """
    Cleans raw OCR token and corrects common OCR letter/digit confusions
    in chess notation.
    """
    t = raw_token.strip().rstrip('.,;:')
    if not t:
        return ""

    # Strip parenthesized annotations, clocks, or evaluations e.g. (2:58), [+0.3]
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()

    # Replace unicode figurine pieces with standard SAN letters
    for fig, letter in FIGURINE_MAP.items():
        t = t.replace(fig, letter)

    # Normalize capture symbols (*, ×, :, X -> x)
    t = re.sub(r'[*×:]', 'x', t)

    # Strip move annotations like !, ?, !!, ??, !?, ?!, +, #
    t = re.sub(r'[!?+#]+$', '', t)

    # Strip leading move numbers like '1.', '2.', 'I.', 'l.', '10.'
    t = re.sub(r'^[0-9Il]{1,3}\.{1,3}', '', t).strip()

    # Strip unseparated leading move numbers like '1e4', '2Nf3', '14Rxd4', '1.e4', '12...Rxd4'
    t = re.sub(r'^[0-9Il]{1,3}\.*(?=[a-zA-Z])', '', t).strip()

    # Normalize castling (0-0, o-o, O-O, 00, OO -> O-O)
    if re.match(r'^[0oO]{3}$|^[0oO]-[0oO]-[0oO]$', t, re.IGNORECASE):
        return 'O-O-O'
    if re.match(r'^[0oO]{2}$|^[0oO]-[0oO]$', t, re.IGNORECASE):
        return 'O-O'

    # Normalize promotions (e8-Q, e8(Q), e8=q, e8q -> e8=Q)
    t = re.sub(r'[\(=-]([QRBNqrbn])\)?$', lambda m: '=' + m.group(1).upper(), t)

    # OCR typo: 'l', 'I', '|', 'i' after file letter -> '1' (e.g., 'Rel' -> 'Re1', 'Relb5' -> 'Re1b5', 'el' -> 'e1')
    t = re.sub(r'([a-hA-H])[lI|i!](?=[^a-zA-Z0-9]|$|[a-hA-HKQRBN0-9])', r'\g<1>1', t)
    if len(t) >= 2 and t[-2].lower() in 'abcdefgh' and t[-1] in ('l', 'I', '|', 'i', '!'):
        t = t[:-1] + '1'

    # OCR typo: 'S' or 's' at the end of a square name -> '5' (e.g., 'eS' -> 'e5', 'NcS' -> 'Nc5')
    if len(t) >= 2 and t[-2].lower() in 'abcdefgh' and t[-1] in ('S', 's'):
        t = t[:-1] + '5'

    # OCR typo: 'b' or 'G' at the end of a square name -> '6'
    if len(t) >= 2 and t[-2].lower() in 'abcdefgh' and t[-1] in ('b', 'G'):
        t = t[:-1] + '6'

    # OCR typo: 'Z' or 'z' at the end of a square name -> '2'
    if len(t) >= 2 and t[-2].lower() in 'abcdefgh' and t[-1] in ('Z', 'z'):
        t = t[:-1] + '2'

    # OCR typo: 'B' at the end of a square name -> '8'
    if len(t) >= 2 and t[-2].lower() in 'abcdefgh' and t[-1] in ('B',):
        t = t[:-1] + '8'

    # OCR typo: 'NE' or 'Nt' followed by square -> 'Nf' (e.g. 'NE3' -> 'Nf3', 'Nt3' -> 'Nf3')
    if re.match(r'^N[Et][1-8a-h]', t):
        t = 'Nf' + t[2:]

    # OCR typo: 'NO' or 'No' followed by square -> 'Nc' or 'Nf'
    if re.match(r'^N[Oo][1-8a-h]', t):
        t = 'Nc' + t[2:]

    # OCR typo: Knight icon read as 'H', 'M', 'W', '4', '&' followed by square or x+square
    if re.match(r'^[HMW4&]([a-h][1-8]|x[a-h][1-8])', t):
        t = 'N' + t[1:]

    # OCR typo: Bishop prefix read as '8' followed by square or x+square
    if re.match(r'^8([a-h][1-8]|x[a-h][1-8])', t):
        t = 'B' + t[1:]

    return t


def resolve_move_from_token(
    board: chess.Board,
    raw_token: str,
    has_piece_icon: bool = False,
    piece_icon_symbol: Optional[str] = None
) -> Optional[chess.Move]:
    """
    Attempts to resolve a raw string token to a legal chess.Move on the given board.
    Tolerant to OCR glitches, figurine omittance, capture omission, check marks, etc.
    Strictly avoids ambiguous guessing: if multiple legal moves are equally valid,
    returns None to avoid committing to a hallucinated move.
    """
    cleaned = clean_ocr_token(raw_token)
    if not cleaned or is_ignorable_token(cleaned):
        return None

    # If an external piece icon was recognized (e.g. 'N'), prepend it if missing
    if piece_icon_symbol in ('K', 'Q', 'R', 'B', 'N'):
        if not cleaned[0].upper() in ('K', 'Q', 'R', 'B', 'N'):
            cleaned = piece_icon_symbol + cleaned

    # 1. Direct SAN parse
    try:
        return board.parse_san(cleaned)
    except Exception:
        pass

    # 2. Try stripping trailing check / checkmate symbols (+, #)
    stripped = cleaned.rstrip('+#')
    if stripped != cleaned:
        try:
            return board.parse_san(stripped)
        except Exception:
            pass

    # 3. Normalized case-insensitive matching against legal moves SAN
    # Example: 'nc6' -> 'Nc6', 'kxf7' -> 'Kxf7', 'exd4' without 'x' -> 'ed4'
    norm_token = re.sub(r'[^a-zA-Z0-9]', '', cleaned).upper()
    matching_sans = [
        m for m in board.legal_moves
        if re.sub(r'[^a-zA-Z0-9]', '', board.san(m)).upper() == norm_token
    ]
    if len(matching_sans) == 1:
        return matching_sans[0]

    # 4. Try matching without capture 'x' or with capture 'x'
    matching_no_x = [
        m for m in board.legal_moves
        if re.sub(r'[^a-zA-Z0-9]', '', board.san(m).replace('x', '')).upper() == norm_token
    ]
    if len(matching_no_x) == 1:
        return matching_no_x[0]

    # 5. Abbreviated pawn captures: e.g. 'ed', 'cd', 'de', 'fe', 'exd', 'cxd'
    # Cannot be pawn capture if a piece icon was explicitly detected
    if not has_piece_icon:
        pawn_cap_match = re.match(r'^([a-h])x?([a-h])$', cleaned.lower())
        if pawn_cap_match:
            from_file = ord(pawn_cap_match.group(1)) - ord('a')
            to_file = ord(pawn_cap_match.group(2)) - ord('a')
            matching_caps = [
                m for m in board.legal_moves
                if board.piece_at(m.from_square) and board.piece_at(m.from_square).piece_type == chess.PAWN
                and chess.square_file(m.from_square) == from_file
                and chess.square_file(m.to_square) == to_file
            ]
            if len(matching_caps) == 1:
                return matching_caps[0]

    # 6. Check destination square matching (e.g. 'f3', 'c6', 'b5', 'Nf3', 'Hf3')
    # Only use for short tokens (<= 4 chars) without multiple rank digits
    if len(cleaned) <= 4 and sum(c.isdigit() for c in cleaned) <= 1:
        dest_match = re.search(r'([a-h][1-8])$', cleaned.lower())
        if dest_match:
            dest_sq_name = dest_match.group(1)
            dest_sq = chess.parse_square(dest_sq_name)
            matching_moves = [m for m in board.legal_moves if m.to_square == dest_sq]

            if len(matching_moves) == 1:
                # If an icon was detected, verify the single move is not a pawn push
                p = board.piece_at(matching_moves[0].from_square)
                if has_piece_icon and p and p.piece_type == chess.PAWN:
                    pass
                else:
                    return matching_moves[0]
            elif len(matching_moves) > 1:
                # If token has >= 3 chars, it carries a piece hint prefix (e.g. 'Nf3', 'Bf3', '4f3')
                # Check piece letter hints first
                for piece_char in ('K', 'Q', 'R', 'B', 'N'):
                    if piece_char in cleaned.upper():
                        piece_type = chess.Piece.from_symbol(piece_char.lower()).piece_type
                        cand = [m for m in matching_moves if board.piece_at(m.from_square) and board.piece_at(m.from_square).piece_type == piece_type]
                        if len(cand) == 1:
                            return cand[0]

                # If an icon was detected to the left
                if has_piece_icon:
                    piece_moves = [m for m in matching_moves if board.piece_at(m.from_square) and board.piece_at(m.from_square).piece_type != chess.PAWN]
                    if len(piece_moves) == 1:
                        return piece_moves[0]

                # If token has a non-file leading character (not a-h), prefer Knight/Bishop piece move
                leading_char = cleaned[0].lower()
                if leading_char not in 'abcdefgh':
                    piece_moves = [m for m in matching_moves if board.piece_at(m.from_square) and board.piece_at(m.from_square).piece_type != chess.PAWN]
                    if len(piece_moves) == 1:
                        return piece_moves[0]

                # If token does NOT have a piece prefix (length 2 e.g. 'e4', 'f3'), and NO piece icon was detected:
                # Standard pawn push notation e4 is 'e4' where token file matches destination file
                if not has_piece_icon and len(cleaned) == 2 and cleaned[0] == dest_sq_name[0]:
                    pawn_moves = [m for m in matching_moves if board.piece_at(m.from_square) and board.piece_at(m.from_square).piece_type == chess.PAWN]
                    if len(pawn_moves) == 1:
                        return pawn_moves[0]

    # 7. Levenshtein edit-distance fuzzy match against all legal moves
    # Only accept if EXACTLY ONE legal move achieves the minimum edit distance
    c_upper = cleaned.upper().replace('X', '')
    candidates_at_dist: Dict[int, List[chess.Move]] = {}
    for m in board.legal_moves:
        san = board.san(m)
        san_clean = san.upper().rstrip('+#').replace('X', '')
        dist = _levenshtein_distance(c_upper, san_clean)
        if abs(len(c_upper) - len(san_clean)) <= 1:
            candidates_at_dist.setdefault(dist, []).append(m)

    if candidates_at_dist:
        min_dist = min(candidates_at_dist.keys())
        # Only accept if distance <= 1 AND unambiguously unique
        if min_dist <= 1 and len(candidates_at_dist[min_dist]) == 1:
            return candidates_at_dist[min_dist][0]

    return None


def extract_moves_from_chunk(board: chess.Board, chunk: str) -> List[chess.Move]:
    """
    Unpacks compound or unspaced OCR strings (e.g. 'I.e4e5', 'Nf3Nc6', 'Bb5a6', '0-0Be7', 'Relb5').
    Resolves sequential legal chess moves.
    """
    s = clean_ocr_token(chunk)
    if not s:
        return []

    # 1. Direct legal move check first (exact SAN)
    try:
        m = board.parse_san(s)
        return [m]
    except Exception:
        pass

    # 2. Try splitting compound token into two legal moves
    if len(s) >= 4 and not s.startswith(('O-O-O', '0-0-0')):
        for i in range(2, min(5, len(s))):
            part1 = s[:i].strip()
            part2 = s[i:].strip()
            if part1 and part2 and part1[-1] in '12345678oO0qrbnQRBN' and part2[0].lower() in 'abcdefghkqrbno0':
                m1 = resolve_move_from_token(board, part1)
                if m1:
                    b_copy = board.copy(stack=False)
                    b_copy.push(m1)
                    m2 = resolve_move_from_token(b_copy, part2)
                    if m2:
                        return [m1, m2]

    # 3. Fall back to single tolerant move resolution
    m = resolve_move_from_token(board, s)
    if m:
        return [m]

    return []


def parse_moves_from_tokens(
    tokens: List[str],
    base_board: Optional[chess.Board] = None
) -> Tuple[List[chess.Move], chess.Board]:
    """
    Processes a list of raw string tokens in chronological sequence,
    resolving legal moves on the board.
    
    Returns (valid_moves, final_board).
    """
    board = base_board.copy() if base_board else chess.Board()
    valid_moves: List[chess.Move] = []

    for raw in tokens:
        for chunk in str(raw).split():
            if is_ignorable_token(chunk):
                continue
            
            # Try direct or compound extraction
            extracted = extract_moves_from_chunk(board, chunk)
            for move in extracted:
                valid_moves.append(move)
                board.push(move)

    return valid_moves, board


def parse_ocr_to_game(
    ocr_items: List[Any],
    base_board: Optional[chess.Board] = None,
    image: Optional[np.ndarray] = None,
    icon_bank: Optional[Any] = None
) -> Tuple[List[chess.Move], chess.Board]:
    """
    Robust row-by-row chess notation parser:
    1. Group OCR bounding boxes into structured rows.
    2. In each row, moves are ordered horizontally: White move first, then Black move.
    3. If an image and icon_bank are provided, detects figurine icons to the left of boxes.
    4. Apply White's move on White's turn, Black's move on Black's turn.
    5. Halts immediately if a ply cannot be cleanly resolved, preventing out-of-phase cascade errors.
    """
    if not ocr_items:
        return [], base_board.copy() if base_board else chess.Board()

    rows = group_boxes_into_rows(ocr_items)
    board = base_board.copy() if base_board else chess.Board()
    valid_moves: List[chess.Move] = []

    for row in rows:
        row_tokens: List[Tuple[str, bool, Optional[str]]] = []
        for item in row:
            box = item[0]
            text = str(item[1]).strip()
            score = float(item[2]) if len(item) > 2 else 1.0

            has_icon = False
            icon_sym = None
            if image is not None and icon_bank is not None:
                has_icon, icon_crop = icon_bank.has_icon(image, box)
                if has_icon and icon_crop is not None:
                    icon_sym = icon_bank.classify_icon(icon_crop)

            # Check if token is compound or has move number embedded (e.g. '1.e4' or '1. e4 e5')
            parts = text.split()
            for part in parts:
                if not is_ignorable_token(part):
                    row_tokens.append((part, has_icon, icon_sym))

        if not row_tokens:
            continue

        row_halted = False
        for tok, has_icon, icon_sym in row_tokens:
            extracted = extract_moves_from_chunk(board, tok)
            if extracted:
                for m in extracted:
                    valid_moves.append(m)
                    board.push(m)
            else:
                m = resolve_move_from_token(
                    board,
                    tok,
                    has_piece_icon=has_icon,
                    piece_icon_symbol=icon_sym
                )
                if m:
                    valid_moves.append(m)
                    board.push(m)
                    # If this move was an unambiguous piece move and icon is present, learn template
                    if image is not None and icon_bank is not None and has_icon:
                        piece = board.piece_at(m.to_square)
                        if piece and piece.piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING):
                            sym = PIECE_SYMBOLS.get(piece.piece_type)
                            if sym:
                                _, crop_to_learn = icon_bank.has_icon(image, item[0])
                                if crop_to_learn is not None:
                                    icon_bank.learn_icon(sym, crop_to_learn)
                else:
                    # Token was not resolved to a legal move for the current turn.
                    # Halt this row to prevent desyncing turn order.
                    row_halted = True
                    break

        if row_halted:
            break

    return valid_moves, board
