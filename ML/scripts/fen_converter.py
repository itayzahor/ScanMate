# In ML/scripts/fen_converter.py

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