# In ML/scripts/fen_converter.py
from __future__ import annotations

from typing import Optional

import chess

# Map your class names to FEN characters
PIECE_TO_FEN_MAP = {
    'white-king': 'K',
    'white-queen': 'Q',
    'white-rook': 'R',
    'white-bishop': 'B',
    'white-knight': 'N',
    'white-pawn': 'P',
    'black-king': 'k',
    'black-queen': 'q',
    'black-rook': 'r',
    'black-bishop': 'b',
    'black-knight': 'n',
    'black-pawn': 'p',
    'empty': '1'  # Use '1' as a placeholder for an empty square
}

FILES = "abcdefgh"


def fen_to_piece_squares(fen: str) -> set[str]:
    """Return the set of occupied square names (e.g. {'a1', 'e2', ...}) from a FEN placement string."""
    squares: set[str] = set()
    ranks = fen.split("/")
    for rank_idx, row in enumerate(ranks):
        file_idx = 0
        for char in row:
            if char.isdigit():
                file_idx += int(char)
                continue
            if file_idx >= 8:
                break
            squares.add(f"{FILES[file_idx]}{8 - rank_idx}")
            file_idx += 1
    return squares


def convert_board_to_fen(board_state):
    """
    Converts your 8x8 board_state list into the piece-placement
    part of a FEN string.
    """
    fen_rows = []
    
    for row in board_state:
        fen_row = ""
        empty_count = 0
        
        for square in row:
            fen_char = PIECE_TO_FEN_MAP.get(square, '1')
            
            if fen_char == '1':
                empty_count += 1
            else:
                if empty_count > 0:
                    fen_row += str(empty_count)
                    empty_count = 0
                fen_row += fen_char
        
        # If the row ended with empty squares
        if empty_count > 0:
            fen_row += str(empty_count)
            
        fen_rows.append(fen_row)
        
    # Join all rows with a '/'
    return "/".join(fen_rows)


def infer_castling_rights(piece_fen: str) -> str:
    """Infer castling rights using only piece placement (king and rooks on home squares)."""
    board_fen = piece_fen.split()[0].strip()
    rows = board_fen.split("/")
    if len(rows) != 8:
        return "-"

    def piece_at(file_idx: int, rank_row: int) -> str | None:
        file_ptr = 0
        for ch in rows[rank_row]:
            if ch.isdigit():
                file_ptr += int(ch)
                continue
            if file_ptr == file_idx:
                return ch
            file_ptr += 1
        return None

    rights: list[str] = []
    if piece_at(4, 7) == "K":
        if piece_at(7, 7) == "R":
            rights.append("K")
        if piece_at(0, 7) == "R":
            rights.append("Q")
    if piece_at(4, 0) == "k":
        if piece_at(7, 0) == "r":
            rights.append("k")
        if piece_at(0, 0) == "r":
            rights.append("q")

    return "".join(rights) or "-"


def board_from_fen(fen: str, turn: chess.Color) -> Optional[chess.Board]:
    """Build a chess.Board from a piece-placement FEN and a turn, inferring castling rights."""
    try:
        castle = infer_castling_rights(fen)
        return chess.Board(f"{fen} {'w' if turn else 'b'} {castle} - 0 1")
    except ValueError:
        return None