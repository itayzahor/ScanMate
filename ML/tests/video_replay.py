"""Offline video replay harness for the recognition pipeline.

This script iterates through a recorded chess video, feeds each sampled frame into
our recognition pipeline, and logs the resulting FEN (or encountered errors)
per frame. Use it to debug accuracy regressions or to benchmark preprocessing
changes without needing the mobile client.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Optional
from string import Template
import html
import os
import shutil

import cv2
import numpy as np
import chess
from PIL import Image, ImageDraw, ImageFont

from scripts.detectors import (
    IMAGE_SIZE,
    PIECE_CLASS_NAMES,
    get_board_corners,
    get_piece_predictions,
)
from scripts.board_orientation import (
    compute_horizontal_skew,
    get_perspective_transform,
    orient_board_state_for_white,
)
from scripts.piece_mapping import map_pieces_to_board
from scripts.fen_converter import convert_board_to_fen, board_from_fen
from scripts.gatekeeper import GatekeeperResult, validate_frame
from scripts.logic_filter import LogicFilterDecision, apply_logic_filter
from scripts.session_state import DEFAULT_STARTING_FEN, SessionState
from scripts.board_mapper import warp_board_to_grid
from scripts.change_tracker import (
    ChangeDetectionResult,
    resolve_move_from_changes,
)


PIECE_PERSISTENCE_FRAMES = 3


@dataclass
class FrameResult:
    frame_index: int
    timestamp_seconds: Optional[float]
    processing_ms: float
    status: str
    fen: Optional[str]
    error: Optional[str]
    piece_count: int
    move: Optional[str] = None
    candidate_fen: Optional[str] = None
    detection_mode: Optional[str] = None
    diff_ready: Optional[bool] = None
    diff_threshold: Optional[float] = None
    diff_triggered: Optional[int] = None
    diff_max_z: Optional[float] = None
    move_uci: Optional[str] = None
    move_san: Optional[str] = None
    diff_squares: Optional[list[dict[str, float | str]]] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class PipelineCandidate:
    fen: str
    detection_mode: str
    diff: Optional[ChangeDetectionResult]
    piece_count: int
    move_uci: Optional[str] = None
    move_san: Optional[str] = None
    triggered_squares: Optional[list[dict[str, float | str]]] = None
    corners: Optional[np.ndarray] = None
    img_resized: Optional[np.ndarray] = None
    warped_board: Optional[np.ndarray] = None
    diff_delta: Optional[np.ndarray] = None


FILES = "abcdefgh"


def _san_from_move(previous_fen: Optional[str], move: chess.Move, turn: chess.Color) -> Optional[str]:
    if not previous_fen:
        return None
    board = board_from_fen(previous_fen, turn)
    if board is None:
        return None
    try:
        return board.san(move)
    except ValueError:
        return None


def _san_from_uci(previous_fen: Optional[str], move_uci: Optional[str]) -> Optional[str]:
    if not previous_fen or not move_uci:
        return None
    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        return None
    for turn in (chess.WHITE, chess.BLACK):
        board = board_from_fen(previous_fen, turn)
        if board is None or move not in board.legal_moves:
            continue
        try:
            return board.san(move)
        except ValueError:
            continue
    return None


def summarize_triggered_squares(
    detection: Optional[ChangeDetectionResult],
    limit: int = 8,
) -> Optional[list[dict[str, float | str]]]:
    if detection is None:
        return None
    squares: list[dict[str, float | str]] = []
    for change in detection.triggered[:limit]:
        squares.append(
            {
                "square": change.square,
                "z_score": float(change.z_score),
                "delta": float(change.delta),
                "intensity": float(change.intensity),
            }
        )
    return squares or None


def save_diff_debug_images(
    frame_index: int,
    warped: Optional[np.ndarray],
    delta: Optional[np.ndarray],
    target_dir: Path,
) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    if warped is not None:
        cv2.imwrite(str(target_dir / f"frame_{frame_index:06d}_warp.png"), warped)
    if delta is not None:
        norm = cv2.normalize(delta, None, 0, 255, cv2.NORM_MINMAX)
        norm_u8 = norm.astype(np.uint8)
        heatmap = cv2.applyColorMap(norm_u8, cv2.COLORMAP_INFERNO)
        cv2.imwrite(str(target_dir / f"frame_{frame_index:06d}_diff.png"), heatmap)


def create_debug_visualization(
    warped: np.ndarray,
    delta: Optional[np.ndarray],
    diff_squares: Optional[list[dict[str, float | str]]],
    move_info: str,
    original_resized: Optional[np.ndarray] = None,
    corners: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Create a 3-panel visualization: original with corners, warped board, and diff heatmap."""
    files = "abcdefgh"
    board_size = warped.shape[0]
    square_size = board_size // 8
    
    # Create heatmap from delta
    if delta is not None:
        norm = cv2.normalize(delta, None, 0, 255, cv2.NORM_MINMAX)
        norm_u8 = norm.astype(np.uint8)
        heatmap = cv2.applyColorMap(norm_u8, cv2.COLORMAP_INFERNO)
    else:
        heatmap = np.zeros_like(warped)
    
    # Prepare original frame with corners (resized to match warped board height)
    if original_resized is not None and corners is not None:
        orig_with_corners = original_resized.copy()
        for x, y in corners:
            cv2.circle(orig_with_corners, (int(x), int(y)), 8, (0, 0, 255), -1)
        # Resize to match warped board height
        h_ratio = board_size / orig_with_corners.shape[0]
        new_w = int(orig_with_corners.shape[1] * h_ratio)
        orig_panel = cv2.resize(orig_with_corners, (new_w, board_size))
    else:
        orig_panel = None
    
    # Draw grid and labels on warped
    warped_labeled = warped.copy()
    for i in range(9):
        x = i * square_size
        cv2.line(warped_labeled, (x, 0), (x, board_size), (0, 255, 0), 1)
        y = i * square_size
        cv2.line(warped_labeled, (0, y), (board_size, y), (0, 255, 0), 1)
    
    # Add square labels (a1-h8) with files right→left (a on the right, h on the left) and ranks top→bottom (1…8)
    for rank in range(1, 9):
        for file_idx, file_char in enumerate(files):
            square_name = f"{file_char}{rank}"
            col = 7 - file_idx          # files go right to left (a on the right)
            row = rank - 1              # ranks go top to bottom (1 at the top)
            x = col * square_size + square_size // 2 - 10
            y = row * square_size + square_size // 2 + 5
            cv2.putText(
                warped_labeled,
                square_name,
                (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (255, 255, 255),
                1,
            )
    
    # Draw grid on heatmap
    heatmap_labeled = heatmap.copy()
    for i in range(9):
        x = i * square_size
        cv2.line(heatmap_labeled, (x, 0), (x, board_size), (255, 255, 255), 1)
        y = i * square_size
        cv2.line(heatmap_labeled, (0, y), (board_size, y), (255, 255, 255), 1)
    
    # Highlight triggered squares
    if diff_squares:
        for sq_info in diff_squares:
            square_name = sq_info["square"]
            z_score = sq_info["z_score"]
            
            # Parse square name
            file_char = square_name[0]
            rank = int(square_name[1])

            col = 7 - files.index(file_char)  # files right to left
            row = rank - 1                    # ranks top to bottom
            
            x1 = col * square_size
            y1 = row * square_size
            x2 = x1 + square_size
            y2 = y1 + square_size
            
            # Draw rectangle on both images
            color = (0, 255, 255)  # Yellow
            cv2.rectangle(warped_labeled, (x1, y1), (x2, y2), color, 3)
            cv2.rectangle(heatmap_labeled, (x1, y1), (x2, y2), color, 3)
            
            # Draw square name and z-score on heatmap
            text = f"{square_name} ({z_score:.1f})"
            cv2.putText(
                heatmap_labeled,
                text,
                (x1 + 5, y1 + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
            )
    
    # Combine panels side by side
    if orig_panel is not None:
        combined = np.hstack([orig_panel, warped_labeled, heatmap_labeled])
    else:
        combined = np.hstack([warped_labeled, heatmap_labeled])
    
    # Add title
    title_height = 60
    canvas = np.zeros((combined.shape[0] + title_height, combined.shape[1], 3), dtype=np.uint8)
    canvas[title_height:, :] = combined
    
    cv2.putText(
        canvas,
        f"Move: {move_info}",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
    )
    cv2.putText(
        canvas,
        f"Triggered: {len(diff_squares or [])} squares",
        (10, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 255),
        1,
    )
    
    return canvas


class GatekeeperRejectedError(RuntimeError):
    def __init__(self, result: GatekeeperResult) -> None:
        super().__init__("Gatekeeper rejected frame")
        self.result = result


def fen_to_board_map(fen: str) -> dict[str, str]:
    board: dict[str, str] = {}
    ranks = fen.split("/")
    if len(ranks) != 8:
        return board
    for rank_idx, row in enumerate(ranks):
        file_idx = 0
        for char in row:
            if char.isdigit():
                file_idx += int(char)
                continue
            if file_idx >= 8:
                break
            square = f"{FILES[file_idx]}{8 - rank_idx}"
            board[square] = char
            file_idx += 1
    return board


def describe_move(prev_fen: Optional[str], curr_fen: Optional[str]) -> Optional[str]:
    if not prev_fen or not curr_fen or prev_fen == curr_fen:
        return None

    prev_board = fen_to_board_map(prev_fen)
    curr_board = fen_to_board_map(curr_fen)
    squares = set(prev_board.keys()) | set(curr_board.keys())
    removed: list[tuple[str, str]] = []
    added: list[tuple[str, str]] = []

    for sq in sorted(squares):
        prev_piece = prev_board.get(sq)
        curr_piece = curr_board.get(sq)
        if prev_piece == curr_piece:
            continue
        if prev_piece:
            removed.append((sq, prev_piece))
        if curr_piece:
            added.append((sq, curr_piece))

    for from_sq, piece in removed:
        match = next((sq for sq, p in added if p == piece), None)
        if match:
            capture_piece = next((p for sq, p in removed if sq == match and sq != from_sq), None)
            if capture_piece:
                return f"{piece}@{from_sq} captures {capture_piece}@{match}"
            return f"{piece}@{from_sq}->{match}"

    details: list[str] = []
    if added:
        details.append("Added: " + ", ".join(f"{piece}@{sq}" for sq, piece in added))
    if removed:
        details.append("Removed: " + ", ".join(f"{piece}@{sq}" for sq, piece in removed))
    return "; ".join(details) if details else None


def run_pipeline_on_frame(
    frame: np.ndarray,
    session: SessionState | None = None,
    *,
    gatekeeper_enabled: bool = True,
) -> PipelineCandidate:
    """Run the same recognition stages used by the FastAPI server on a single frame."""
    if frame is None or frame.size == 0:
        raise ValueError("Received empty frame from video stream")

    img_resized = cv2.resize(frame, (IMAGE_SIZE, IMAGE_SIZE))

    if gatekeeper_enabled:
        gatekeeper_result = validate_frame(img_resized)
        if not gatekeeper_result.is_valid:
            raise GatekeeperRejectedError(gatekeeper_result)

    corners = get_board_corners(img_resized)
    if corners is None:
        raise RuntimeError("Board corners not detected")

    homography = get_perspective_transform(corners, img_resized)
    skew = compute_horizontal_skew(corners)
    
    # Get pieces first for both orientation and detection
    piece_boxes = get_piece_predictions(img_resized)
    piece_count = int(len(piece_boxes)) if piece_boxes is not None else 0
    
    board_state = map_pieces_to_board(
        piece_boxes,
        PIECE_CLASS_NAMES,
        homography,
    )
    board_state_oriented = orient_board_state_for_white(board_state)
    
    diff_result: Optional[ChangeDetectionResult] = None
    previous_fen = session.get_last_fen() if session else None
    warped_board: Optional[np.ndarray] = None
    diff_delta: Optional[np.ndarray] = None
    
    # Extract current piece squares from board_state_oriented
    current_piece_squares = set()
    if board_state_oriented:
        for rank_idx, rank in enumerate(board_state_oriented):
            for file_idx, piece in enumerate(rank):
                if piece:  # Non-empty square
                    square = chr(ord('a') + file_idx) + str(8 - rank_idx)
                    current_piece_squares.add(square)
    
    if session:
        # Match the debug server: warp once with the same inputs/size and no extra rotation
        warped_board = warp_board_to_grid(img_resized, homography, size=IMAGE_SIZE)
        diff_result = session.detect_square_changes(warped_board)
        diff_delta = session.last_delta()

    if previous_fen and diff_result:
        move_resolution = resolve_move_from_changes(
            previous_fen, 
            diff_result, 
            current_piece_squares=current_piece_squares,
        )
        if move_resolution:
            # Update piece squares for next frame
            if session:
                session.set_piece_squares(current_piece_squares)
            move_uci = move_resolution.move.uci()
            move_san = _san_from_move(previous_fen, move_resolution.move, move_resolution.turn)
            return PipelineCandidate(
                fen=move_resolution.fen,
                detection_mode="diff_tracking",
                diff=diff_result,
                piece_count=piece_count,
                move_uci=move_uci,
                move_san=move_san,
                triggered_squares=summarize_triggered_squares(diff_result),
                corners=corners,
                img_resized=img_resized,
                warped_board=warped_board,
                diff_delta=diff_delta,
            )
        # Removed auto-reset - let statistics adapt naturally
        # if diff_result.ready and diff_result.triggered_count >= 12 and session:
        #     session.reset_change_tracker()

    # Use already computed oriented board state
    if session:
        board_state_oriented = session.blend_board(board_state_oriented, persistence_frames=PIECE_PERSISTENCE_FRAMES)

    fen = convert_board_to_fen(board_state_oriented)

    # NEW: Validate YOLO FEN changes against Diff Tracking
    # If Diff Tracking says the board is quiet, we should not accept arbitrary changes from YOLO.
    # This filters out "phantom" moves like Kf1 when no squares actually changed.
    if previous_fen and fen != previous_fen and diff_result and diff_result.ready:
        prev_map = fen_to_board_map(previous_fen)
        curr_map = fen_to_board_map(fen)
        all_squares = set(prev_map.keys()) | set(curr_map.keys())
        changed_squares = {sq for sq in all_squares if prev_map.get(sq) != curr_map.get(sq)}
        change_lookup = {ch.square: ch for ch in diff_result.triggered}
        change_scores = [change_lookup[sq].magnitude for sq in changed_squares if sq in change_lookup]
        has_support = True

        # Validate additions (occupancy) strictly
        # If we claim a piece appeared at a square, there MUST be diff evidence
        # This blocks "teleporting" pieces or YOLO noise
        added_squares = {sq for sq in changed_squares if not prev_map.get(sq) and curr_map.get(sq)}
        if added_squares:
            supported_additions = 0
            for sq in added_squares:
                if sq in change_lookup:
                    mag = change_lookup[sq].magnitude
                    # Arrival threshold: 1.1 (Rejects 0.98 phantom, allows ~1.3 real)
                    if mag >= 1.1:
                        supported_additions += 1
            
            # If we have additions but NONE are supported, revert
            if supported_additions == 0:
                 has_support = False
        else:
            # Just removals/slides? Check general support
            if changed_squares and not any(sq in change_lookup and change_lookup[sq].magnitude >= 1.5 for sq in changed_squares):
                 has_support = False

        # If we found changed squares but NONE had support, revert to previous FEN
        if changed_squares and not has_support:
            print(f"  [Safety] Reverting YOLO FEN {fen} -> {previous_fen}")
            print(f"  Reason: No diff support for changes {sorted(changed_squares)} (max_mag={max(change_scores) if change_scores else 0.0:.2f})")
            fen = previous_fen

    return PipelineCandidate(
        fen=fen,
        detection_mode="piece_detection",
        diff=diff_result,
        piece_count=piece_count,
        triggered_squares=summarize_triggered_squares(diff_result),
        corners=corners,
        img_resized=img_resized,
        warped_board=warped_board,
        diff_delta=diff_delta,
    )


def iter_sampled_frames(
    capture: cv2.VideoCapture,
    frame_step: int,
    start_frame: int,
) -> Iterator[tuple[int, Optional[float], np.ndarray]]:
    """Yield sampled frames, skipping until start_frame and applying frame_step."""
    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    index = -1
    while True:
        success, frame = capture.read()
        if not success:
            break
        index += 1
        if index < start_frame:
            continue
        if frame_step > 1 and (index - start_frame) % frame_step != 0:
            continue
        timestamp = (index / fps) if fps > 0 else None
        yield index, timestamp, frame


def resolve_path(base_dir: Path, raw: Path) -> Path:
    return raw if raw.is_absolute() else (base_dir / raw).resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a recorded chess video through the pipeline.")
    parser.add_argument(
        "--video",
        type=Path,
        default=Path("data/chessgame.mp4"),
        help="Path to the input video relative to ML/ or as an absolute path.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/video_replay"),
        help="Directory for logs and optional frame dumps (relative to ML/ by default).",
    )
    parser.add_argument(
        "--log-name",
        type=str,
        default=None,
        help="Optional custom log filename. Defaults to <video_stem>_log.jsonl.",
    )
    parser.add_argument(
        "--frame-step",
        type=int,
        default=1,
        help="Only process every Nth frame (>=1).",
    )
    parser.add_argument(
        "--start-frame",
        type=int,
        default=0,
        help="Frame index to start processing from.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Stop after processing this many sampled frames.",
    )
    parser.add_argument(
        "--save-failures",
        action="store_true",
        help="Dump frames that failed recognition into output-dir/failures.",
    )
    parser.add_argument(
        "--save-successes",
        action="store_true",
        help="Dump frames that produced a FEN into output-dir/successes (can be large).",
    )
    parser.add_argument(
        "--save-diff-debug",
        action="store_true",
        help="When diff tracking is ready, store warped board and diff heatmaps for inspection.",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete existing log/frame folders inside --output-dir before running.",
    )
    parser.add_argument(
        "--report-html",
        type=Path,
        default=None,
        help="Optional HTML report (relative to output-dir unless absolute).",
    )
    parser.add_argument(
        "--report-title",
        type=str,
        default="Video Replay Report",
        help="Title for the optional HTML report.",
    )
    parser.add_argument(
        "--starting-fen",
        type=str,
        default=DEFAULT_STARTING_FEN,
        help="Seed the session with a specific FEN (piece placement only).",
    )
    parser.add_argument(
        "--logic-policy",
        choices=["strict", "permissive", "off"],
        default="strict",
        help="strict = require single legal moves (server parity), permissive = allow jumps when illegal, off = raw detections.",
    )
    parser.add_argument(
        "--skip-gatekeeper",
        action="store_true",
        help="Bypass blur/hand checks (faster but less accurate).",
    )
    parser.add_argument(
        "--build-slides",
        action="store_true",
        help="Emit a static replay_slides.html next to outputs with toggles for failures/moves-only.",
    )
    return parser.parse_args()


def draw_corners_on_frame(frame: np.ndarray, corners: Optional[np.ndarray]) -> np.ndarray:
    """Draw red dots on board corners.
    
    Args:
        frame: Frame at 640x640 resolution (same as corner detection)
        corners: Corner coordinates detected on this frame
    """
    if corners is None:
        return frame
    
    frame_with_corners = frame.copy()
    
    for x, y in corners:
        cv2.circle(frame_with_corners, (int(x), int(y)), 8, (0, 0, 255), -1)  # Red dots
    
    return frame_with_corners


def build_slides_view(
        entries: list[dict[str, object]],
        *,
        output_dir: Path,
        frames_dir: Path,
        success_dir: Path,
        failure_dir: Path,
    starting_fen: str,
) -> Path:
        """Emit a static HTML slide viewer (no server) with toggles for failures and moves-only."""

        slides_path = output_dir / "replay_slides.html"
        minimal_entries: list[dict[str, object]] = []
        for entry in entries:
                minimal_entries.append(
                        {
                                "frame_index": entry.get("frame_index"),
                                "status": entry.get("status"),
                                "fen": entry.get("fen"),
                                "error": entry.get("error"),
                                "move": entry.get("move"),
                                "move_uci": entry.get("move_uci"),
                                "move_san": entry.get("move_san"),
                                "detection_mode": entry.get("detection_mode"),
                                "candidate_fen": entry.get("candidate_fen"),
                                "piece_count": entry.get("piece_count"),
                                "timestamp_seconds": entry.get("timestamp_seconds"),
                                "processing_ms": entry.get("processing_ms"),
                        }
                )

        data_json = json.dumps(minimal_entries, ensure_ascii=False)

        html_template = Template("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>Replay Slides</title>
    <style>
        :root { font-family: Arial, sans-serif; background: #0f172a; color: #e2e8f0; }
        body { margin: 0; padding: 0; display: flex; flex-direction: column; min-height: 100vh; }
        header { padding: 1rem 1.5rem; background: #1e293b; display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
        main { padding: 1rem 1.5rem; flex: 1; display: grid; grid-template-columns: 2fr 1fr; gap: 1rem; }
        .frame { background: #0b1224; border: 1px solid #1e3a8a; border-radius: 8px; padding: 0.75rem; display: flex; flex-direction: column; gap: 0.75rem; }
        .media { display: flex; flex-direction: column; gap: 0.5rem; }
        img { max-width: 100%; border-radius: 6px; border: 1px solid #1e3a8a; }
        .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; font-weight: 700; font-size: 0.85rem; }
        .ok { background: #0f766e; color: #e2e8f0; }
        .err { background: #b91c1c; color: #f8fafc; }
        .meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 0.35rem; font-size: 0.9rem; }
        .board { display: grid; grid-template-columns: repeat(8, 1fr); width: 100%; max-width: 380px; aspect-ratio: 1; border: 1px solid #1e3a8a; border-radius: 6px; overflow: hidden; }
        .sq { display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1.4rem; color: #0b1224; }
        .dark { background: #c3d6f3; }
        .light { background: #e6eefb; }
        .hl { outline: 3px solid #facc15; outline-offset: -3px; }
        .controls { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
        button { background: #38bdf8; color: #0b1224; border: none; border-radius: 6px; padding: 0.5rem 0.9rem; cursor: pointer; font-weight: 700; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        label { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.95rem; }
        code { background: #0b1224; border: 1px solid #1e3a8a; padding: 0.1rem 0.25rem; border-radius: 4px; }
        .moves { max-height: 420px; overflow-y: auto; display: flex; flex-direction: column; gap: 0.35rem; }
        .move-item { display: flex; gap: 0.5rem; align-items: center; padding: 0.25rem 0.4rem; border-radius: 6px; border: 1px solid #1e3a8a; cursor: pointer; }
        .move-item:hover { background: #1e293b; }
        .move-idx { font-weight: 700; color: #38bdf8; }
        .start-fen { font-size: 0.95rem; }
        @media (max-width: 960px) { main { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <header>
        <div class="controls">
            <button id="prev">Prev</button>
            <button id="next">Next</button>
            <label><input type="checkbox" id="show-failures" /> Show failures</label>
            <label><input type="checkbox" id="moves-only" /> Moves only</label>
            <label><input type="checkbox" id="show-debug" /> Show debug image</label>
            <span id="pos"></span>
        </div>
    </header>
    <main>
        <div class="frame">
            <div class="media">
                <img id="frame-img" alt="frame" />
                <img id="debug-img" alt="debug" style="display:none;" />
                <div><span id="status" class="badge"></span> <span id="error"></span></div>
            </div>
            <div class="meta">
                <div>Frame: <span id="frame-id"></span></div>
                <div>Timestamp: <span id="ts"></span></div>
                <div>Proc: <span id="proc"></span> ms</div>
                <div>Pieces: <span id="pieces"></span></div>
                <div>Mode: <span id="mode"></span></div>
                <div>Move: <span id="move"></span></div>
            </div>
            <div>FEN: <code id="fen"></code></div>
        </div>
        <div class="frame" style="gap:1rem;">
            <div class="start-fen"><strong>Starting FEN:</strong> <code id="start-fen"></code></div>
            <div class="board" id="board"></div>
            <div>
                <strong>Moves</strong>
                <div class="moves" id="moves-list"></div>
            </div>
        </div>
    </main>
    <script>
        const ENTRIES = $DATA_JSON;
        const framesDir = "$FRAMES_DIR";
        const successDir = "$SUCCESS_DIR";
        const failureDir = "$FAILURE_DIR";
        const START_FEN = "$START_FEN";

        let filtered = [];
        let idx = 0;
        let moves = [];

        const PIECES = {"K":"♔","Q":"♕","R":"♖","B":"♗","N":"♘","P":"♙","k":"♚","q":"♛","r":"♜","b":"♝","n":"♞","p":"♟"};

        function squareListFromFen(fen) {
            if (!fen) return Array(64).fill(null);
            const placement = fen.split(' ')[0];
            const rows = placement.split('/');
            const squares = [];
            for (const row of rows) {
                for (const ch of row) {
                    if (/\d/.test(ch)) {
                        const n = parseInt(ch, 10);
                        for (let i = 0; i < n; i++) squares.push(null);
                    } else {
                        squares.push(ch);
                    }
                }
            }
            return squares.slice(0, 64);
        }

        function renderBoard(fen, moveUci) {
            const boardEl = document.getElementById('board');
            boardEl.innerHTML = '';
            const squares = squareListFromFen(fen);
            const fromSq = moveUci ? moveUci.slice(0, 2) : null;
            const toSq = moveUci ? moveUci.slice(2, 4) : null;
            const files = 'abcdefgh';
            for (let rank = 7; rank >= 0; rank--) {
                for (let file = 0; file < 8; file++) {
                    const i = rank * 8 + file;
                    const piece = squares[i];
                    const isDark = (rank + file) % 2 === 1;
                    const div = document.createElement('div');
                    div.className = `sq ${isDark ? 'dark' : 'light'}`;
                    const fileChar = files[file];
                    const sqName = `${fileChar}${rank + 1}`;
                    if (sqName === fromSq || sqName === toSq) div.classList.add('hl');
                    if (piece) {
                        div.textContent = PIECES[piece] || piece;
                        // Black pieces get dark text, white pieces stay dark text for contrast
                        if (piece === piece.toLowerCase()) {
                            div.style.color = '#0b1224';
                        } else {
                            div.style.color = '#0b1224';
                        }
                    }
                    boardEl.appendChild(div);
                }
            }
        }

        function buildMoves() {
            moves = ENTRIES.filter(e => e.move_uci || e.move_san || (e.move && e.move !== 'No change')).map(e => ({
                frame_index: e.frame_index,
                label: e.move_san || e.move_uci || e.move,
            }));
            const list = document.getElementById('moves-list');
            list.innerHTML = '';
            moves.forEach((m, i) => {
                const row = document.createElement('div');
                row.className = 'move-item';
                const idxSpan = document.createElement('span');
                idxSpan.className = 'move-idx';
                idxSpan.textContent = i + 1;
                const label = document.createElement('span');
                label.textContent = m.label || 'Move';
                row.append(idxSpan, label);
                row.onclick = () => jumpToFrame(m.frame_index);
                list.appendChild(row);
            });
        }

        function jumpToFrame(frameIndex) {
            const target = filtered.findIndex(e => e.frame_index === frameIndex);
            if (target >= 0) {
                idx = target;
                render();
            }
        }

        function imgPath(frameIndex, status) {
            const name = `frame_${String(frameIndex).padStart(6, '0')}.jpg`;
            if (status === 'success') return `${framesDir}/${name}`;
            return `${failureDir}/${name}`;
        }

        function debugPath(frameIndex) {
            const name = `frame_${String(frameIndex).padStart(6, '0')}_debug.jpg`;
            return `${framesDir}/debug/${name}`;
        }

        function applyFilters() {
            const showFailures = document.getElementById('show-failures').checked;
            const movesOnly = document.getElementById('moves-only').checked;
            filtered = ENTRIES.filter(e => {
                if (!showFailures && e.status !== 'success') return false;
                if (movesOnly && !e.move_uci && !e.move_san && (!e.move || e.move === 'No change')) return false;
                return true;
            });
            if (idx >= filtered.length) idx = filtered.length ? filtered.length - 1 : 0;
            render();
        }

        function render() {
            const posEl = document.getElementById('pos');
            if (!filtered.length) {
                posEl.textContent = 'No frames';
                return;
            }
            const e = filtered[idx];
            posEl.textContent = `${idx + 1} / ${filtered.length}`;
            document.getElementById('frame-id').textContent = e.frame_index ?? 'n/a';
            document.getElementById('ts').textContent = e.timestamp_seconds ?? 'n/a';
            document.getElementById('proc').textContent = e.processing_ms ?? 'n/a';
            document.getElementById('pieces').textContent = e.piece_count ?? 'n/a';
            document.getElementById('mode').textContent = e.detection_mode || 'n/a';
            document.getElementById('move').textContent = e.move_san || e.move_uci || e.move || '—';
            document.getElementById('fen').textContent = e.fen || '—';
            const statusEl = document.getElementById('status');
            statusEl.textContent = e.status;
            statusEl.className = `badge ${e.status === 'success' ? 'ok' : 'err'}`;
            document.getElementById('error').textContent = e.error || '';
            const imgEl = document.getElementById('frame-img');
            imgEl.src = imgPath(e.frame_index, e.status);
            const showDebug = document.getElementById('show-debug').checked;
            const dbgEl = document.getElementById('debug-img');
            dbgEl.style.display = 'none';
            if (showDebug && e.status === 'success') {
                dbgEl.src = debugPath(e.frame_index);
                dbgEl.style.display = 'block';
            }
            renderBoard(e.fen, e.move_uci);
        }

        document.getElementById('prev').onclick = () => { if (idx > 0) { idx--; render(); } };
        document.getElementById('next').onclick = () => { if (idx < filtered.length - 1) { idx++; render(); } };
        document.getElementById('show-failures').onchange = applyFilters;
        document.getElementById('moves-only').onchange = applyFilters;
        document.getElementById('show-debug').onchange = render;
        document.addEventListener('keydown', (ev) => {
            if (ev.key === 'ArrowLeft') { if (idx > 0) { idx--; render(); } }
            if (ev.key === 'ArrowRight') { if (idx < filtered.length - 1) { idx++; render(); } }
        });

        document.getElementById('start-fen').textContent = START_FEN;
        buildMoves();
        applyFilters();
    </script>
</body>
</html>
""")

        html_doc = html_template.safe_substitute(
                DATA_JSON=data_json,
                FRAMES_DIR=frames_dir.relative_to(output_dir).as_posix(),
                SUCCESS_DIR=success_dir.relative_to(output_dir).as_posix(),
                FAILURE_DIR=failure_dir.relative_to(output_dir).as_posix(),
                START_FEN=starting_fen,
        )

        slides_path.write_text(html_doc, encoding="utf-8")
        return slides_path


def maybe_save_frame(frame: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), frame)


def remove_path(path: Optional[Path]) -> None:
    if path is None:
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.is_file():
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def clean_previous_outputs(
    log_path: Path,
    success_dir: Path,
    failure_dir: Path,
    report_frames_dir: Optional[Path],
    extra_dirs: Optional[list[Path]] = None,
) -> None:
    remove_path(log_path)
    remove_path(success_dir)
    remove_path(failure_dir)
    remove_path(report_frames_dir)
    if extra_dirs:
        for path in extra_dirs:
            remove_path(path)


def build_report(entries: list[tuple[FrameResult, Optional[str]]], report_path: Path, title: str) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    for result, image_rel in entries:
        timestamp = f"{result.timestamp_seconds:.2f}s" if result.timestamp_seconds is not None else "n/a"
        move_san = html.escape(result.move_san) if result.move_san else None
        move_uci = html.escape(result.move_uci) if result.move_uci else None
        move_primary = move_san or move_uci or (html.escape(result.move) if result.move else "-")
        move_uci_display = move_uci or "-"
        fen = html.escape(result.fen) if result.fen else "-"
        error = html.escape(result.error) if result.error else "-"
        img_html = (
            f'<img src="{html.escape(image_rel)}" alt="frame {result.frame_index}" />'
            if image_rel else "<em>No image</em>"
        )
        rows.append(
            f"""
            <article class=\"frame\">
                <div class=\"frame__media\">{img_html}</div>
                <div class=\"frame__body\">
                    <h3>Frame {result.frame_index}</h3>
                    <p><strong>Timestamp:</strong> {timestamp} &middot; <strong>Status:</strong> {html.escape(result.status)}</p>
                    <p><strong>Processing:</strong> {result.processing_ms:.2f} ms &middot; <strong>Pieces:</strong> {result.piece_count}</p>
                    <p><strong>Move (SAN/desc):</strong> {move_primary}</p>
                    <p><strong>Move (UCI):</strong> {move_uci_display}</p>
                    <p><strong>FEN:</strong> <code>{fen}</code></p>
                    <p><strong>Error:</strong> {error}</p>
                </div>
            </article>
            """
        )

    html_content = f"""<!DOCTYPE html>
    <html lang=\"en\">
    <head>
        <meta charset=\"utf-8\" />
        <title>{html.escape(title)}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 2rem; background: #f6f8fa; }}
            h1 {{ margin-bottom: 1rem; }}
            .frame {{ display: flex; gap: 1.5rem; background: #fff; padding: 1rem; margin-bottom: 1rem; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            .frame__media img {{ max-width: 240px; border-radius: 4px; border: 1px solid #d0d7de; }}
            .frame__body code {{ background: #eaeef2; padding: 0.1rem 0.2rem; border-radius: 4px; }}
            @media (max-width: 768px) {{ .frame {{ flex-direction: column; }} .frame__media img {{ width: 100%; height: auto; }} }}
        </style>
    </head>
    <body>
        <h1>{html.escape(title)}</h1>
        <section>
            {''.join(rows)}
        </section>
    </body>
    </html>"""

    report_path.write_text(html_content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    video_path = resolve_path(base_dir, args.video)
    output_dir = resolve_path(base_dir, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if args.frame_step < 1:
        raise ValueError("--frame-step must be >= 1")
    if args.start_frame < 0:
        raise ValueError("--start-frame must be >= 0")

    log_name = args.log_name or f"{video_path.stem}_log.jsonl"
    log_path = output_dir / log_name
    success_dir = output_dir / "successes"
    failure_dir = output_dir / "failures"
    default_report_frames_dir = output_dir / "report_frames"

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")

    processed = 0
    successes = 0
    failures = 0
    last_success_fen: Optional[str] = None
    report_entries: list[tuple[FrameResult, Optional[str]]] = []
    report_path: Optional[Path] = None
    report_frames_dir: Optional[Path] = None
    diff_debug_dir: Optional[Path] = None
    output_lines: list[str] = []
    if args.report_html is not None:
        report_path = args.report_html if args.report_html.is_absolute() else output_dir / args.report_html
        report_frames_dir = report_path.parent / "report_frames"

    if args.clean_output:
        extra_dirs: list[Path] = []
        if report_frames_dir is not None and report_frames_dir != default_report_frames_dir:
            extra_dirs.append(default_report_frames_dir)
        # Always clean diff_debug directory when cleaning output
        diff_debug_dir_path = output_dir / "diff_debug"
        extra_dirs.append(diff_debug_dir_path)
        clean_previous_outputs(
            log_path=log_path,
            success_dir=success_dir,
            failure_dir=failure_dir,
            report_frames_dir=report_frames_dir or default_report_frames_dir,
            extra_dirs=extra_dirs or None,
        )

    if report_frames_dir is not None:
        report_frames_dir.mkdir(parents=True, exist_ok=True)

    if args.save_diff_debug:
        diff_debug_dir = output_dir / "diff_debug"
        diff_debug_dir.mkdir(parents=True, exist_ok=True)

    starting_fen = args.starting_fen.strip() if args.starting_fen else DEFAULT_STARTING_FEN
    logic_policy = args.logic_policy
    gatekeeper_enabled = not args.skip_gatekeeper

    session = SessionState(starting_fen=starting_fen)

    with log_path.open("w", encoding="utf-8") as log_file:
        for frame_index, timestamp, frame in iter_sampled_frames(
            capture, args.frame_step, args.start_frame
        ):
            start = time.perf_counter()
            fen: Optional[str] = None
            error: Optional[str] = None
            status = "success"
            piece_count = 0
            move_desc: Optional[str] = None
            report_image_rel: Optional[str] = None
            candidate_fen: Optional[str] = None
            detection_mode: Optional[str] = None
            diff_info: Optional[ChangeDetectionResult] = None
            matched_move: Optional[str] = None
            matched_san: Optional[str] = None
            diff_squares: Optional[list[dict[str, float | str]]] = None
            corners_detected: Optional[np.ndarray] = None
            img_resized: Optional[np.ndarray] = None
            try:
                candidate = run_pipeline_on_frame(
                    frame,
                    session=session,
                    gatekeeper_enabled=gatekeeper_enabled,
                )
                candidate_fen = candidate.fen
                fen = candidate_fen
                piece_count = candidate.piece_count
                detection_mode = candidate.detection_mode
                diff_info = candidate.diff
                matched_move = candidate.move_uci
                matched_san = candidate.move_san
                diff_squares = candidate.triggered_squares
                corners_detected = candidate.corners
                # Use the SAME resized image that was used in the pipeline
                img_resized = candidate.img_resized
                logic_decision: Optional[LogicFilterDecision] = None
                logic_note: Optional[str] = None

                previous_fen = session.get_last_fen() if session else None
                if logic_policy != "off":
                    logic_decision = apply_logic_filter(candidate_fen, previous_fen)
                    fen = logic_decision.fen
                    if not logic_decision.accepted_candidate:
                        logic_note = f"Logic rejected ({logic_decision.fallback_reason or 'unknown'})"
                        if logic_policy == "permissive":
                            fen = candidate_fen
                            logic_note = None
                            logic_decision = LogicFilterDecision(
                                fen=candidate_fen,
                                accepted_candidate=True,
                                matched_move=logic_decision.matched_move,
                                fallback_reason="permissive_override",
                            )
                    if logic_decision and logic_decision.matched_move and not matched_move:
                        matched_move = logic_decision.matched_move
                        matched_san = _san_from_uci(previous_fen, matched_move)

                if session:
                    session.update_last_fen(fen)

                if (
                    args.save_diff_debug
                    and diff_debug_dir is not None
                    and diff_info is not None
                    and diff_info.ready
                ):
                    warped_dbg = candidate.warped_board
                    delta_dbg = candidate.diff_delta
                    if warped_dbg is not None or delta_dbg is not None:
                        save_diff_debug_images(frame_index, warped_dbg, delta_dbg, diff_debug_dir)
                        
                        # Create combined debug visualization for viewer
                        if report_frames_dir is not None and img_resized is not None:
                            move_san = matched_san or matched_move or "Unknown"
                            detection_mode = candidate.detection_mode or "unknown"
                            move_info_text = f"{move_san} ({detection_mode})"
                            debug_vis = create_debug_visualization(
                                warped_dbg,
                                delta_dbg,
                                diff_squares,
                                move_info_text,
                                original_resized=img_resized,
                                corners=corners_detected,
                            )
                            debug_frames_dir = report_frames_dir / "debug"
                            debug_frames_dir.mkdir(parents=True, exist_ok=True)
                            debug_filename = f"frame_{frame_index:06d}_debug.jpg"
                            cv2.imwrite(str(debug_frames_dir / debug_filename), debug_vis)

                if logic_note:
                    move_desc = logic_note
                elif matched_san:
                    move_desc = matched_san
                elif matched_move:
                    move_desc = matched_move
                elif last_success_fen is None:
                    move_desc = "Initial snapshot"
                else:
                    move_desc = describe_move(last_success_fen, fen) or "No change"
                last_success_fen = fen
            except GatekeeperRejectedError as exc:
                status = "error"
                issues = ",".join(exc.result.issues) or "unknown"
                error = "Hand Block"
            except Exception as exc:  # noqa: BLE001
                status = "error"
                error = str(exc)
            duration_ms = (time.perf_counter() - start) * 1000.0

            if (
                status == "success"
                and report_frames_dir is not None
                and report_path is not None
                and img_resized is not None
            ):
                frame_filename = f"frame_{frame_index:06d}.jpg"
                frame_path = report_frames_dir / frame_filename
                # Draw corners on resized frame (640x640) for visualization
                frame_with_corners = draw_corners_on_frame(img_resized, corners_detected)
                maybe_save_frame(frame_with_corners, frame_path)
                report_image_rel = os.path.relpath(frame_path, report_path.parent)

            result = FrameResult(
                frame_index=frame_index,
                timestamp_seconds=timestamp,
                processing_ms=round(duration_ms, 2),
                status=status,
                fen=fen,
                error=error,
                piece_count=piece_count,
                move=move_desc,
                candidate_fen=candidate_fen,
                detection_mode=detection_mode,
                diff_ready=diff_info.ready if diff_info else None,
                diff_threshold=diff_info.threshold if diff_info else None,
                diff_triggered=diff_info.triggered_count if diff_info else None,
                diff_max_z=diff_info.max_z if diff_info else None,
                move_uci=matched_move,
                move_san=matched_san,
                diff_squares=diff_squares,
            )
            log_file.write(result.to_json() + "\n")
            log_file.flush()

            if status == "success":
                successes += 1
                if args.save_successes and img_resized is not None:
                    maybe_save_frame(
                        img_resized,  # Save resized version for consistency
                        success_dir / f"frame_{frame_index:06d}.jpg",
                    )
                # Append move/FEN summary for output.txt only for real moves
                move_label = move_desc or matched_san or matched_move or "No change"
                is_logic_reject = isinstance(move_label, str) and move_label.lower().startswith("logic rejected")
                is_noop = move_label in ("No change", "Initial snapshot")
                if not is_logic_reject and not is_noop:
                    output_lines.append(
                        f"Frame {frame_index}: {move_label} | FEN: {fen or ''}"
                    )
            else:
                failures += 1
                if args.save_failures:
                    maybe_save_frame(
                        frame,
                        failure_dir / f"frame_{frame_index:06d}.jpg",
                    )

            if report_path is not None and status == "success":
                report_entries.append((result, report_image_rel))

            processed += 1
            if args.max_frames is not None and processed >= args.max_frames:
                break

    capture.release()

    # Write compact move/FEN log
    output_txt = output_dir / "output.txt"
    try:
        output_txt.write_text("\n".join(output_lines), encoding="utf-8")
    except Exception:
        pass

    if report_path is not None:
        build_report(report_entries, report_path, args.report_title)

    if args.build_slides:
        with log_path.open("r", encoding="utf-8") as f:
            log_entries = [json.loads(line) for line in f if line.strip()]
        slides_path = build_slides_view(
            log_entries,
            output_dir=output_dir,
            frames_dir=report_frames_dir or default_report_frames_dir,
            success_dir=success_dir,
            failure_dir=failure_dir,
            starting_fen=starting_fen,
        )

    print("\n=== Video Replay Summary ===")
    print(f"Video: {video_path}")
    print(f"Log:   {log_path}")
    print(f"Frames processed: {processed}")
    print(f"Successes: {successes}")
    print(f"Failures:  {failures}")
    if report_path is not None:
        print(f"Report: {report_path}")
    if args.build_slides:
        print(f"Slides: {slides_path}")


if __name__ == "__main__":
    main()
