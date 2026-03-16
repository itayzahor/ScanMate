"""Interactive video viewer for debugging chess move detection.

This script plays back a recorded chess video with real-time visual overlays showing:
- Board corners (red dots)
- Detected moves (from square in red, to square in green)
- Current FEN and move information
- Piece detection confidence

Controls:
- SPACE: Pause/Resume
- Q or ESC: Quit
- S: Save current frame as debug image

terminal:
python tests/video_viewer.py --video data/chessgame2.mp4 --frame-step 12
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure the ML root is on sys.path so `scripts.*` imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
import chess

from scripts.detectors import get_board_corners, get_piece_predictions, PIECE_CLASS_NAMES
from scripts.board_orientation import get_perspective_transform, orient_board_state_for_white
from scripts.piece_mapping import map_pieces_to_board
from scripts.gatekeeper import validate_frame
from scripts.session_state import DEFAULT_STARTING_FEN, SessionState
from scripts.board_mapper import warp_board_to_grid
from scripts.change_tracker import resolve_move_from_changes


FILES = "abcdefgh"
CHESS_BOARD_SIZE = 400  # Size of the visual chess board display


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive chess video viewer with move annotations")
    parser.add_argument(
        "--video",
        type=Path,
        default=Path("data/chessgame.mp4"),
        help="Path to input video file.",
    )
    parser.add_argument(
        "--starting-fen",
        type=str,
        default=DEFAULT_STARTING_FEN,
        help="Initial FEN to seed the session.",
    )
    parser.add_argument(
        "--frame-step",
        type=int,
        default=1,
        help="Process every Nth frame (default: 1 = every frame; use 25 for ~1 FPS at 25 FPS video).",
    )
    parser.add_argument(
        "--start-frame",
        type=int,
        default=0,
        help="Start from this frame index.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/video_viewer"),
        help="Directory to save debug snapshots.",
    )
    return parser.parse_args()


def square_to_board_coords(square_name: str) -> tuple[int, int]:
    """Convert square name (e.g. 'e2') to board grid indices (row, col).
    
    Returns:
        (row, col) where row 0 = rank 1, col 0 = file h (inverted for warped orientation)
    """
    file_char = square_name[0]
    rank_char = square_name[1]
    
    rank = int(rank_char)  # 1-8
    file_idx = ord(file_char) - ord('a')  # 0-7
    
    row = rank - 1  # 0-7, row 0 is rank 1
    col = 7 - file_idx  # 0-7, col 0 is file h (rightmost)
    
    return (row, col)


def draw_square_on_original_frame(frame: np.ndarray, square_name: str, h_matrix: np.ndarray, color: tuple[int, int, int], alpha: float = 0.4) -> np.ndarray:
    """Draw a semi-transparent square overlay on the original frame.
    
    Args:
        frame: Original video frame (640x640)
        square_name: Square to highlight (e.g., 'e2')
        h_matrix: Homography matrix for perspective transform
        color: BGR color tuple
        alpha: Transparency (0=invisible, 1=opaque)
    
    Returns:
        Frame with overlay
    """
    overlay = frame.copy()
    
    # Convert square name to warped board coordinates
    row, col = square_to_board_coords(square_name)
    
    # Define the square corners in warped space (640x640 to match perspective transform)
    square_size = 640 // 8  # IMAGE_SIZE = 640
    warped_corners = np.array([
        [col * square_size, row * square_size],
        [(col + 1) * square_size, row * square_size],
        [(col + 1) * square_size, (row + 1) * square_size],
        [col * square_size, (row + 1) * square_size]
    ], dtype=np.float32)
    
    # Transform back to original frame coordinates using inverse homography
    h_inv = np.linalg.inv(h_matrix)
    original_corners = cv2.perspectiveTransform(warped_corners.reshape(-1, 1, 2), h_inv)
    original_corners = original_corners.reshape(-1, 2).astype(np.int32)
    
    # Draw filled polygon
    cv2.fillPoly(overlay, [original_corners], color)
    
    # Blend with original
    result = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
    
    return result


def draw_moves_on_original_frame(frame: np.ndarray, from_square: Optional[str], to_square: Optional[str], h_matrix: np.ndarray) -> np.ndarray:
    """Draw colored square overlays on the original video frame.
    
    Args:
        frame: Original video frame
        from_square: Source square (drawn in red)
        to_square: Destination square (drawn in green)
        h_matrix: Homography matrix
    
    Returns:
        Annotated frame
    """
    result = frame.copy()
    
    if from_square:
        result = draw_square_on_original_frame(result, from_square, h_matrix, (0, 0, 255), alpha=0.35)  # Light red
    if to_square:
        result = draw_square_on_original_frame(result, to_square, h_matrix, (0, 255, 0), alpha=0.35)  # Light green
    
    return result


def draw_corners_and_grid(frame: np.ndarray, corners: np.ndarray, h_matrix: np.ndarray) -> np.ndarray:
    """Draw corner points and chess board grid on the frame.
    
    Args:
        frame: Original video frame (640x640)
        corners: Detected corner points (4x2 array)
        h_matrix: Homography matrix for perspective transform
    
    Returns:
        Frame with corners and grid overlay
    """
    result = frame.copy()
    
    # Draw corner points as red circles
    for x, y in corners:
        cv2.circle(result, (int(x), int(y)), 8, (0, 0, 255), -1)  # Red dots
        cv2.circle(result, (int(x), int(y)), 10, (255, 255, 255), 2)  # White outline
    
    # Draw grid lines using inverse perspective transform
    # The perspective transform maps corners to (0,0), (640,0), (640,640), (0,640)
    h_inv = np.linalg.inv(h_matrix)
    grid_size = 640  # IMAGE_SIZE from detectors.py
    
    # Draw vertical lines (files)
    for i in range(9):
        x_warped = (i * grid_size) / 8
        # Top and bottom points of this vertical line in warped space
        warped_points = np.array([
            [[x_warped, 0]],
            [[x_warped, grid_size]]
        ], dtype=np.float32)
        
        # Transform back to original frame coordinates
        original_points = cv2.perspectiveTransform(warped_points, h_inv)
        pt1 = tuple(original_points[0][0].astype(int))
        pt2 = tuple(original_points[1][0].astype(int))
        
        cv2.line(result, pt1, pt2, (0, 255, 0), 2)  # Green lines
    
    # Draw horizontal lines (ranks)
    for i in range(9):
        y_warped = (i * grid_size) / 8
        # Left and right points of this horizontal line in warped space
        warped_points = np.array([
            [[0, y_warped]],
            [[grid_size, y_warped]]
        ], dtype=np.float32)
        
        # Transform back to original frame coordinates
        original_points = cv2.perspectiveTransform(warped_points, h_inv)
        pt1 = tuple(original_points[0][0].astype(int))
        pt2 = tuple(original_points[1][0].astype(int))
        
        cv2.line(result, pt1, pt2, (0, 255, 0), 2)  # Green lines
    
    return result


def draw_info_panel(frame: np.ndarray, info_lines: list[str]) -> np.ndarray:
    """Draw text information panel on the frame.
    
    Args:
        frame: Input frame
        info_lines: Lines of text to display
    
    Returns:
        Frame with info panel
    """
    panel_height = 150
    panel_width = frame.shape[1]
    panel = np.zeros((panel_height, panel_width, 3), dtype=np.uint8)
    
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    thickness = 1
    color = (255, 255, 255)
    y_offset = 20
    
    for i, line in enumerate(info_lines):
        y = y_offset + i * 25
        cv2.putText(panel, line, (10, y), font, font_scale, color, thickness, cv2.LINE_AA)
    
    return np.vstack([frame, panel])


def draw_chess_board(fen: str, size: int = 400) -> np.ndarray:
    """Draw a visual chess board from FEN position.
    
    Args:
        fen: FEN string (board position only)
        size: Size of the board in pixels (default 400)
    
    Returns:
        Image of the chess board
    """
    board_img = np.zeros((size, size, 3), dtype=np.uint8)
    square_size = size // 8
    
    # Draw checkerboard pattern
    for row in range(8):
        for col in range(8):
            # Light squares are white, dark squares are gray
            if (row + col) % 2 == 0:
                color = (240, 217, 181)  # Light square (BGR)
            else:
                color = (181, 136, 99)   # Dark square (BGR)
            
            x1 = col * square_size
            y1 = row * square_size
            x2 = x1 + square_size
            y2 = y1 + square_size
            cv2.rectangle(board_img, (x1, y1), (x2, y2), color, -1)
    
    # Parse FEN and draw pieces
    # Use ASCII representation for better compatibility
    piece_symbols = {
        'P': 'P', 'N': 'N', 'B': 'B', 'R': 'R', 'Q': 'Q', 'K': 'K',
        'p': 'p', 'n': 'n', 'b': 'b', 'r': 'r', 'q': 'q', 'k': 'k',
    }
    
    try:
        ranks = fen.split()[0].split('/')
        for rank_idx, rank_str in enumerate(ranks):
            file_idx = 0
            for char in rank_str:
                if char.isdigit():
                    file_idx += int(char)
                elif char in piece_symbols:
                    # Calculate position (row 0 = rank 8)
                    row = rank_idx
                    col = file_idx
                    
                    x = col * square_size + square_size // 2
                    y = row * square_size + square_size // 2
                    
                    # Draw piece symbol
                    symbol = piece_symbols[char]
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = 1.2
                    thickness = 3
                    
                    # White pieces are white with black outline, black pieces are black with white outline
                    if char.isupper():
                        # White piece - draw black outline first, then white text
                        (text_width, text_height), _ = cv2.getTextSize(symbol, font, font_scale, thickness + 2)
                        text_x = x - text_width // 2
                        text_y = y + text_height // 2
                        cv2.putText(board_img, symbol, (text_x, text_y), font, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
                        cv2.putText(board_img, symbol, (text_x, text_y), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
                    else:
                        # Black piece - draw white outline first, then black text
                        (text_width, text_height), _ = cv2.getTextSize(symbol, font, font_scale, thickness + 2)
                        text_x = x - text_width // 2
                        text_y = y + text_height // 2
                        cv2.putText(board_img, symbol, (text_x, text_y), font, font_scale, (255, 255, 255), thickness + 2, cv2.LINE_AA)
                        cv2.putText(board_img, symbol, (text_x, text_y), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
                    
                    file_idx += 1
    except Exception:
        # If FEN parsing fails, just show empty board
        pass
    
    # Draw file labels (a-h) at bottom
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.4
    thickness = 1
    for i, file_char in enumerate(FILES):
        x = i * square_size + square_size // 2 - 5
        y = size - 5
        cv2.putText(board_img, file_char, (x, y), font, font_scale, (100, 100, 100), thickness, cv2.LINE_AA)
    
    # Draw rank labels (1-8) on left
    for i in range(8):
        rank = str(8 - i)
        x = 5
        y = i * square_size + square_size // 2 + 5
        cv2.putText(board_img, rank, (x, y), font, font_scale, (100, 100, 100), thickness, cv2.LINE_AA)
    
    return board_img


def draw_status_banner(frame: np.ndarray, flag: str, flag_color: tuple[int, int, int], last_move: str) -> np.ndarray:
    """Draw a two-part status banner at the top of the frame.

    Left side shows the current flag (SUCCESS / HAND / NO BOARD / etc.)
    Right side shows the last detected move.

    Args:
        frame: Input frame
        flag: Short status label (e.g. "SUCCESS", "HAND BLOCK", "NO BOARD")
        flag_color: BGR colour for the flag section
        last_move: The last recognised move string (e.g. "Nf3")

    Returns:
        Frame with the two-part banner drawn on top.
    """
    result = frame.copy()
    banner_height = 40
    width = result.shape[1]
    mid_x = width // 2

    overlay = result.copy()
    # Left half – flag colour
    cv2.rectangle(overlay, (0, 0), (mid_x, banner_height), flag_color, -1)
    # Right half – dark background for move
    cv2.rectangle(overlay, (mid_x, 0), (width, banner_height), (40, 40, 40), -1)
    result = cv2.addWeighted(overlay, 0.7, result, 0.3, 0)

    font = cv2.FONT_HERSHEY_SIMPLEX
    text_color = (255, 255, 255)

    # Flag label (left)
    flag_scale = 0.7
    flag_thick = 2
    (_, fh), _ = cv2.getTextSize(flag, font, flag_scale, flag_thick)
    cv2.putText(result, f"Flag: {flag}", (10, (banner_height + fh) // 2),
                font, flag_scale, text_color, flag_thick, cv2.LINE_AA)

    # Last move label (right)
    move_text = f"Last Move: {last_move}"
    move_scale = 0.7
    move_thick = 2
    (_, mh), _ = cv2.getTextSize(move_text, font, move_scale, move_thick)
    cv2.putText(result, move_text, (mid_x + 10, (banner_height + mh) // 2),
                font, move_scale, text_color, move_thick, cv2.LINE_AA)

    return result


def main() -> None:
    args = parse_args()
    video_path = args.video
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    session = SessionState(starting_fen=args.starting_fen)
    
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    
    if args.start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, args.start_frame)
    
    print("=== Chess Video Viewer ===")
    print(f"Video: {video_path}")
    print(f"Controls: SPACE=pause, S=snapshot, Q=quit\\n")
    
    paused = False
    frame_index = args.start_frame - 1  # Align sampling with replay: first processed frame is start_frame
    
    last_move_from: Optional[str] = None
    last_move_to: Optional[str] = None
    current_fen = args.starting_fen
    expected_turn: Optional[chess.Color] = None  # None = try both sides (unknown)

    # Pending move confirmation: hold a candidate for 1 extra frame before committing.
    # This filters YOLO flicker — real moves persist across frames, flicker doesn't.
    pending_move_uci: Optional[str] = None
    pending_san: Optional[str] = None
    pending_idle_frames: int = 0  # detection frames with no move since pending was set
    PENDING_IDLE_LIMIT = 3  # discard pending after this many idle detection frames

    banner_flag: str = "SUCCESS"
    banner_flag_color: tuple[int, int, int] = (0, 180, 0)  # green
    last_move_display: str = "—"

    last_h_matrix: Optional[np.ndarray] = None
    last_corners: Optional[np.ndarray] = None
    last_processing_ms = 0.0
    last_move_uci: Optional[str] = None
    last_change_ready: Optional[bool] = None
    last_change_triggered: Optional[int] = None
    last_piece_count: int = 0
    
    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                break
            frame_index += 1
        else:
            # Paused - just redraw the last frame
            ret, frame = cap.retrieve()
        
        # Process frame
        try:
            h_matrix: Optional[np.ndarray] = None
            start_time = time.perf_counter()
            
            # Resize to 640x640
            img_resized = cv2.resize(frame, (640, 640))

            # Only run heavy detection on every Nth frame
            process_now = (
                args.frame_step <= 1 or (frame_index - args.start_frame) % args.frame_step == 0
            )

            if not process_now:
                # Non-detection frame: just show video with cached overlays
                annotated_frame = img_resized.copy()
                if last_h_matrix is not None and last_corners is not None:
                    annotated_frame = draw_corners_and_grid(annotated_frame, last_corners, last_h_matrix)
                    annotated_frame = draw_moves_on_original_frame(
                        annotated_frame, last_move_from, last_move_to, last_h_matrix
                    )
                chess_board_vis = draw_chess_board(current_fen, CHESS_BOARD_SIZE)
                info_lines = [
                    f"Frame {frame_index} | {last_processing_ms:.1f}ms",
                    f"Move: {last_move_uci or 'None'},",
                    f"FEN: {current_fen[:50]}...",
                    f"Diff: ready={last_change_ready}, triggered={last_change_triggered}",
                    f"Pieces: {last_piece_count} detected",
                ]
                display_frame = draw_info_panel(annotated_frame, info_lines)
                display_frame = draw_status_banner(display_frame, banner_flag, banner_flag_color, last_move_display)

                cv2.imshow("Chess Video Viewer", display_frame)
                cv2.imshow("Chess Board", chess_board_vis)

                wait_time = max(1, int(1000 / fps)) if not paused else 0
                key = cv2.waitKey(wait_time)
                if key == ord('q') or key == 27:
                    break
                elif key == ord(' '):
                    paused = not paused
                continue
            
            # === Detection frame: run the full pipeline ===

            # Gatekeeper check - show video always; only skip processing if frame is invalid
            gatekeeper_result = validate_frame(img_resized)
            gatekeeper_valid = gatekeeper_result.is_valid
            issues_list = gatekeeper_result.issues or []

            if not gatekeeper_valid:
                label = ', '.join(issues_list).upper() if issues_list else "BLOCKED"
                banner_flag = "HAND" if "hand" in label.lower() else label
                banner_flag_color = (0, 0, 255)  # red

                display_frame = draw_status_banner(img_resized, banner_flag, banner_flag_color, last_move_display)
                info_lines = [
                    f"Frame {frame_index}",
                    f"Status: {banner_flag}",
                    f"FEN: {current_fen[:40]}...",
                ]
                display_frame = draw_info_panel(display_frame, info_lines)
                cv2.imshow("Chess Video Viewer", display_frame)
                chess_board_vis = draw_chess_board(current_fen, CHESS_BOARD_SIZE)
                cv2.imshow("Chess Board", chess_board_vis)

                key = cv2.waitKey(1 if not paused else 0)
                if key == ord('q') or key == 27:
                    break
                elif key == ord(' '):
                    paused = not paused
                continue

            # Passing gatekeeper clears any prior block banner
            banner_flag = "SUCCESS"
            banner_flag_color = (0, 180, 0)  # green
            
            # Detect corners
            corners = get_board_corners(img_resized)
            if corners is None or len(corners) != 4:
                banner_flag = "NO BOARD"
                banner_flag_color = (0, 165, 255)  # orange
                display_frame = draw_status_banner(img_resized, banner_flag, banner_flag_color, last_move_display)
                
                info_lines = [
                    f"Frame {frame_index}",
                    "Status: Waiting for board in view...",
                    f"FEN: {current_fen[:40]}...",
                ]
                display_frame = draw_info_panel(display_frame, info_lines)
                cv2.imshow("Chess Video Viewer", display_frame)
                
                key = cv2.waitKey(1 if not paused else 0)
                if key == ord('q') or key == 27:
                    break
                elif key == ord(' '):
                    paused = not paused
                continue
            
            change_detection = None
            move_uci: Optional[str] = None
            current_piece_squares: set[str] = set()

            # Compute perspective transform and warp (warp only for diff tracking)
            h_matrix = get_perspective_transform(corners, img_resized)
            last_h_matrix = h_matrix
            last_corners = corners
            warped_board = warp_board_to_grid(img_resized, h_matrix, 640)  # Keep 640 like replay
            
            # Detect pieces on the original resized frame (parity with video_replay)
            piece_predictions = get_piece_predictions(img_resized)
            board_state = map_pieces_to_board(piece_predictions, PIECE_CLASS_NAMES, h_matrix)
            board_state_oriented_raw = orient_board_state_for_white(board_state)
            
            # Change detection uses the warped board
            change_detection = session.detect_square_changes(warped_board)
            
            # Extract current piece squares from RAW board (before smoothing)
            if board_state_oriented_raw:
                for rank_idx, rank in enumerate(board_state_oriented_raw):
                    for file_idx, piece in enumerate(rank):
                        if piece:
                            square = chr(ord('a') + file_idx) + str(8 - rank_idx)
                            current_piece_squares.add(square)
            
            # Try to resolve a move - ONLY if we processed and have previous FEN and diff detection
            previous_fen = session.get_last_fen()
            if previous_fen and change_detection:
                
                if not change_detection.ready:
                    pass  # warming up
                elif change_detection.triggered_count == 0 and pending_move_uci is None:
                    pass  # no changes
                elif change_detection.triggered_count == 0 and pending_move_uci is not None:
                    # No diff activity but we have a pending move to confirm.
                    # Re-run resolver: authoritative FEN hasn't changed, so YOLO
                    # should still see the same missing/new pattern → same move → confirm.
                    move_resolution = resolve_move_from_changes(
                        previous_fen=previous_fen,
                        detection=change_detection,
                        current_piece_squares=current_piece_squares,
                        expected_turn=expected_turn,
                    )
                    if move_resolution and move_resolution.uci == pending_move_uci:
                        # YOLO still agrees → CONFIRM
                        current_fen = move_resolution.fen
                        last_move_from = pending_move_uci[:2]
                        last_move_to = pending_move_uci[2:4]
                        last_move_display = pending_san or pending_move_uci or "—"
                        banner_flag = "MOVE DETECTED"
                        banner_flag_color = (0, 180, 0)
                        expected_turn = chess.BLACK if move_resolution.turn == chess.WHITE else chess.WHITE
                        print(f"Frame {frame_index}: {last_move_display}")
                        move_uci = pending_move_uci
                        session.set_piece_squares(current_piece_squares)
                        pending_move_uci = None
                        pending_san = None
                        pending_idle_frames = 0
                    else:
                        # YOLO disagrees or no move found → count as idle
                        pending_idle_frames += 1
                        if pending_idle_frames >= PENDING_IDLE_LIMIT:
                            pending_move_uci = None
                            pending_san = None
                            pending_idle_frames = 0
                else:
                    if frame_index < 100:
                        print(f"  [DEBUG Frame {frame_index}] ready={change_detection.ready}, triggered={change_detection.triggered_count}")
                    move_resolution = resolve_move_from_changes(
                        previous_fen=previous_fen,
                        detection=change_detection,
                        current_piece_squares=current_piece_squares,
                        expected_turn=expected_turn,
                    )
                    if move_resolution:
                        move_uci = move_resolution.uci
                        # Compute SAN for display
                        try:
                            turn_char = 'w' if move_resolution.turn == chess.WHITE else 'b'
                            board = chess.Board(f"{previous_fen} {turn_char} - - 0 1")
                            candidate_san = board.san(move_resolution.move)
                        except:
                            candidate_san = move_uci

                        # --- Pending move confirmation ---
                        if pending_move_uci and move_uci == pending_move_uci:
                            # Same move seen again → CONFIRM
                            session.set_piece_squares(current_piece_squares)
                            current_fen = move_resolution.fen
                            last_move_from = move_uci[:2] if move_uci else None
                            last_move_to = move_uci[2:4] if move_uci else None
                            last_move_display = candidate_san or move_uci or "—"
                            banner_flag = "MOVE DETECTED"
                            banner_flag_color = (0, 180, 0)  # green
                            expected_turn = chess.BLACK if move_resolution.turn == chess.WHITE else chess.WHITE
                            print(f"Frame {frame_index}: {last_move_display}")
                            pending_move_uci = None
                            pending_san = None
                            pending_idle_frames = 0
                        else:
                            # New or different move → store as pending
                            pending_move_uci = move_uci
                            pending_san = candidate_san
                            pending_idle_frames = 0
                            banner_flag = "PENDING"
                            banner_flag_color = (0, 200, 255)  # yellow/orange
                            last_move_display = f"{candidate_san}?"
                            move_uci = None  # don't commit yet
                    else:
                        # No move detected this frame — track idle for pending
                        if pending_move_uci is not None:
                            pending_idle_frames += 1
                            if pending_idle_frames >= PENDING_IDLE_LIMIT:
                                pending_move_uci = None
                                pending_san = None
                                pending_idle_frames = 0

            if current_fen:
                session.update_last_fen(current_fen)

            # Cache latest info for rendering skipped frames
            last_processing_ms = (time.perf_counter() - start_time) * 1000
            last_move_uci = move_uci or last_move_uci
            last_change_ready = change_detection.ready if change_detection else None
            last_change_triggered = change_detection.triggered_count if change_detection else None
            last_piece_count = len(current_piece_squares)
            
            # Draw annotations when processing this frame
            annotated_frame = img_resized.copy()
            if h_matrix is not None and corners is not None:
                annotated_frame = draw_corners_and_grid(annotated_frame, corners, h_matrix)
                annotated_frame = draw_moves_on_original_frame(annotated_frame, last_move_from, last_move_to, h_matrix)
            chess_board_vis = draw_chess_board(current_fen, CHESS_BOARD_SIZE)

            info_lines = [
                f"Frame {frame_index} | {last_processing_ms:.1f}ms",
                f"Move: {move_uci or 'None'},",
                f"FEN: {current_fen[:50]}...",
                f"Diff: ready={change_detection.ready if change_detection else None}, triggered={change_detection.triggered_count if change_detection else None}",
                f"Pieces: {len(current_piece_squares)} detected",
            ]

            display_frame = draw_info_panel(annotated_frame, info_lines)

        except Exception as e:
            print(f"Error processing frame {frame_index}: {e}")
            info_lines = [
                f"Frame {frame_index}",
                f"ERROR: {str(e)[:60]}",
                f"FEN: {current_fen[:40]}...",
            ]
            display_frame = draw_info_panel(img_resized, info_lines)
            cv2.imshow("Chess Video Viewer", display_frame)
            chess_board_vis = draw_chess_board(current_fen, CHESS_BOARD_SIZE)
        
        # Always draw the two-part banner (flag + last move)
        display_frame = draw_status_banner(display_frame, banner_flag, banner_flag_color, last_move_display)

        # Show main display and chess board
        cv2.imshow("Chess Video Viewer", display_frame)
        cv2.imshow("Chess Board", chess_board_vis)

        # Handle keyboard input
        wait_time = max(1, int(1000 / fps)) if not paused else 0
        key = cv2.waitKey(wait_time)
        
        if key == ord('q') or key == 27:
            break
        elif key == ord(' '):
            paused = not paused
        elif key == ord('s') or key == ord('S'):
            snapshot_path = output_dir / f"snapshot_frame_{frame_index:06d}.jpg"
            cv2.imwrite(str(snapshot_path), display_frame)
    
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
