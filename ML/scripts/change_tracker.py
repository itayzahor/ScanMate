"""Difference-map utilities for chess move detection."""
from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
from typing import Optional

import cv2
import numpy as np
import chess
from scripts.fen_converter import board_from_fen, fen_to_piece_squares

_FILES = "abcdefgh"
_EPS = 1e-6


def _square_name(index: int) -> str:
    # Map grid indices to square names using the same orientation as the warped debug overlay:
    # files run right→left (a on the right, h on the left); ranks run top→bottom (1 at the top).
    row, col = divmod(index, 8)
    rank = row + 1                 # top row is rank 1
    file_char = _FILES[7 - col]    # leftmost column is file h
    return f"{file_char}{rank}"


@dataclass(frozen=True)
class SquareChange:
    square: str
    z_score: float
    delta: float
    intensity: float

    @property
    def magnitude(self) -> float:
        return abs(self.z_score)


@dataclass(frozen=True)
class ChangeDetectionResult:
    ready: bool
    threshold: float
    median_z: float
    max_z: float
    frame_index: int
    squares: list[SquareChange]
    triggered: list[SquareChange]

    @property
    def triggered_count(self) -> int:
        return len(self.triggered)


@dataclass(frozen=True)
class MoveResolution:
    fen: str
    move: chess.Move
    score: float
    turn: chess.Color

    @property
    def uci(self) -> str:
        return self.move.uci()


class _SquareStats:
    __slots__ = ("count", "mean", "m2")

    def __init__(self) -> None:
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0

    def variance(self) -> float:
        if self.count < 2:
            return 0.0
        return self.m2 / (self.count - 1)

    def score(self, value: float) -> float:
        if self.count < 2:
            return 0.0
        std = math.sqrt(max(self.variance(), 0.0))
        # Floor of 1.0 pixel ensures meaningful scores even when running
        # variance is near-zero (e.g. first change after many static frames).
        std = max(std, 1.0)
        return (value - self.mean) / std

    def delta(self, value: float) -> float:
        if self.count == 0:
            return 0.0
        return value - self.mean

    def update(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.m2 += delta * delta2

    def reset(self) -> None:
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0


class ChessMoveDetector:
    """Maintains rolling change statistics for each board square."""

    def __init__(
        self,
        *,
        warmup_frames: int = 2,
        min_threshold_z: float = 3.5,
        median_padding: float = 1.5,
    ) -> None:
        self._stats = [_SquareStats() for _ in range(64)]
        self._previous_gray: Optional[np.ndarray] = None
        self._frame_index = 0
        self.warmup_frames = max(1, warmup_frames)
        self.min_threshold_z = min_threshold_z
        self.median_padding = median_padding
        self._last_delta: Optional[np.ndarray] = None

    def reset(self) -> None:
        for stat in self._stats:
            stat.reset()
        self._previous_gray = None
        self._frame_index = 0

    def detect_changes(self, warped_board: np.ndarray) -> ChangeDetectionResult:
        board_gray = cv2.cvtColor(warped_board, cv2.COLOR_BGR2GRAY)
        if self._previous_gray is None:
            self._previous_gray = board_gray
            self._last_delta = None
            return ChangeDetectionResult(
                ready=False,
                threshold=self.min_threshold_z,
                median_z=0.0,
                max_z=0.0,
                frame_index=self._frame_index,
                squares=[],
                triggered=[],
            )

        delta = cv2.absdiff(board_gray, self._previous_gray)
        self._previous_gray = board_gray
        self._last_delta = delta
        self._frame_index += 1

        square_values = self._square_means(delta)
        squares: list[SquareChange] = []
        abs_scores: list[float] = []

        for idx, value in enumerate(square_values):
            stats = self._stats[idx]
            z_score = stats.score(value)
            delta_value = stats.delta(value)
            squares.append(
                SquareChange(
                    square=_square_name(idx),
                    z_score=z_score,
                    delta=delta_value,
                    intensity=value,
                )
            )
            stats.update(value)
            if stats.count > 2:
                abs_scores.append(abs(z_score))

        squares.sort(key=lambda change: change.magnitude, reverse=True)
        median_z = statistics.median(abs_scores) if abs_scores else 0.0
        threshold = max(self.min_threshold_z, median_z + self.median_padding)
        ready = self._frame_index >= self.warmup_frames
        # Use LOW absolute magnitude threshold (0.8) instead of statistical z-score
        # This catches subtle moves like pawns/bishops while filtering true noise
        triggered = [change for change in squares if change.magnitude >= 0.8] if ready else []
        max_z = squares[0].magnitude if squares else 0.0

        return ChangeDetectionResult(
            ready=ready,
            threshold=threshold,
            median_z=median_z,
            max_z=max_z,
            frame_index=self._frame_index,
            squares=squares,
            triggered=triggered,
        )

    def last_delta(self) -> Optional[np.ndarray]:
        if self._last_delta is None:
            return None
        return self._last_delta.copy()

    @staticmethod
    def _square_means(delta: np.ndarray) -> list[float]:
        h, w = delta.shape
        step_y = h // 8
        step_x = w // 8
        values: list[float] = []
        for row in range(8):
            y0 = row * step_y
            y1 = h if row == 7 else (row + 1) * step_y
            for col in range(8):
                x0 = col * step_x
                x1 = w if col == 7 else (col + 1) * step_x
                roi = delta[y0:y1, x0:x1]
                values.append(float(roi.mean()) if roi.size else 0.0)
        return values


def _check_castling(
    previous_fen: str,
    detection: ChangeDetectionResult,
    missing_squares: set[str],
    current_piece_squares: set[str],
    expected_turn: Optional[chess.Color] = None,
) -> Optional[MoveResolution]:
    """Detect castling using diff as primary signal, YOLO as soft bonus.

    YOLO is noisy on the back rank (pieces close together, partial occlusion),
    so we CANNOT rely on all 4 YOLO conditions firing simultaneously.
    Instead, the diff tracker reliably detects physical piece movement —
    castling always disturbs 4 specific squares — so we use diff as the
    primary gate and let YOLO conditions add confidence.

    Acceptance criteria:
      • 3-4 diff hits  → accept (diff alone is strong evidence)
      • 2 diff hits    → need at least 1 YOLO condition as support
      • 0-1 diff hits  → reject

    Castling patterns (square changes):
      White O-O  : e1 h1 vacated → g1 f1 occupied  (king e1→g1, rook h1→f1)
      White O-O-O: e1 a1 vacated → c1 d1 occupied  (king e1→c1, rook a1→d1)
      Black O-O  : e8 h8 vacated → g8 f8 occupied  (king e8→g8, rook h8→f8)
      Black O-O-O: e8 a8 vacated → c8 d8 occupied  (king e8→c8, rook a8→d8)
    """
    # Castling always vacates e1 or e8 — skip entirely if neither king moved.
    if "e1" not in missing_squares and "e8" not in missing_squares:
        return None

    CASTLING_PATTERNS = [
        # (king_from, king_to, rook_from, rook_to, turn, uci)
        ("e1", "g1", "h1", "f1", chess.WHITE, "e1g1"),   # White O-O
        ("e1", "c1", "a1", "d1", chess.WHITE, "e1c1"),   # White O-O-O
        ("e8", "g8", "h8", "f8", chess.BLACK, "e8g8"),   # Black O-O
        ("e8", "c8", "a8", "d8", chess.BLACK, "e8c8"),   # Black O-O-O
    ]

    triggered_set = {ch.square for ch in detection.triggered}
    change_lookup = {ch.square: ch for ch in detection.squares}

    best_castling: Optional[MoveResolution] = None

    for king_from, king_to, rook_from, rook_to, turn, uci in CASTLING_PATTERNS:
        if expected_turn is not None and turn != expected_turn:
            continue
        affected = [king_from, king_to, rook_from, rook_to]

        # ── PRIMARY GATE: diff activity on castling squares ──
        diff_hits = sum(1 for sq in affected if sq in triggered_set)
        total_magnitude = sum(
            change_lookup[sq].magnitude for sq in affected if sq in change_lookup
        )

        if diff_hits < 2:
            continue  # Not enough physical evidence

        # ── SOFT YOLO SCORING ──
        yolo_score = 0.0

        if king_from in missing_squares:
            yolo_score += 30.0
        if rook_from in missing_squares:
            yolo_score += 30.0
        if king_to in current_piece_squares:
            yolo_score += 30.0
        if rook_to in current_piece_squares:
            yolo_score += 30.0

        # ── COMBINED SCORE ──
        diff_score = diff_hits * 40.0 + total_magnitude
        combined_score = diff_score + yolo_score

        # ── ACCEPTANCE ──
        # Always require at least 1 YOLO condition to prevent false positives
        # from hand movement / camera shake causing high diff on unrelated squares.
        # 3+ diff hits → need at least 1 YOLO condition (yolo_score >= 30)
        # 2 diff hits  → need at least 2 YOLO conditions (yolo_score >= 60)
        if yolo_score < 30.0:
            continue
        if diff_hits >= 3:
            pass  # Strong diff + some YOLO, accept
        elif diff_hits == 2 and yolo_score >= 60.0:
            pass  # Moderate diff + solid YOLO, accept
        else:
            continue

        # ── LEGALITY CHECK ──
        board = board_from_fen(previous_fen, turn)
        if board is None:
            continue
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            continue

        board.push(move)
        resolution = MoveResolution(
            fen=board.board_fen(),
            move=move,
            score=combined_score,
            turn=turn,
        )

        if best_castling is None or combined_score > best_castling.score:
            best_castling = resolution

    return best_castling


def resolve_move_from_changes(
    previous_fen: Optional[str],
    detection: Optional[ChangeDetectionResult],
    *,
    current_piece_squares: Optional[set[str]] = None,
    expected_turn: Optional[chess.Color] = None,
) -> Optional[MoveResolution]:
    """Resolve a chess move focusing on Piece Detection (Real FEN vs Current YOLO).
    
    Algorithm:
    1. Compare Previous FEN (Authoritative) vs Current YOLO (Observation).
    2. Identify 'Missing' squares (Pieces that left).
    3. Identify 'New' squares (Pieces that appeared).
    4. Move Generation:
       - Source MUST be a 'Missing' square.
       - Destination favored if it is a 'New' square or Diff-Triggered.
    """
    if not previous_fen or detection is None or not detection.ready:
        return None
    
    if current_piece_squares is None:
        return None

    # 1. Comparison: Real FEN vs Current Observation
    real_fen_squares = fen_to_piece_squares(previous_fen)
    
    # Missing: Squares that had a piece in FEN, but are empty in YOLO now.
    # This is the primary signal for "From Square".
    missing_squares = real_fen_squares - current_piece_squares
    
    # New: Squares that were empty in FEN, but have a piece in YOLO now.
    # This is a strong signal for "To Square" (Moves to empty).
    # Note: Captures won't show up here (dest was already occupied in FEN).
    new_squares = current_piece_squares - real_fen_squares
    
    change_lookup = {change.square: change for change in detection.squares}

    # Optimization: If nothing is missing, no piece moved!
    # (Exception: Dropping a piece? Not valid in chess game).
    if not missing_squares:
        # print("  [Logic] No pieces missing from FEN state - assuming static board.")
        return None

    # --- Priority: Check for castling (two pieces move simultaneously) ---
    castling = _check_castling(
        previous_fen, detection, missing_squares, current_piece_squares, expected_turn=expected_turn,
    )
    if castling is not None:
        return castling

    best_resolution: Optional[MoveResolution] = None
    candidates = []

    # If we know whose turn it is, only consider that side's moves.
    turns_to_try = (expected_turn,) if expected_turn is not None else (chess.WHITE, chess.BLACK)
    for turn in turns_to_try:
        board = board_from_fen(previous_fen, turn)
        if board is None:
            continue
        for move in board.legal_moves:
            from_sq = chess.square_name(move.from_square)
            to_sq = chess.square_name(move.to_square)

            # For promotion moves, default to queen (correct ~99% of the time).
            # Skip underpromotions (knight/bishop/rook) to avoid duplicate candidates.
            if move.promotion and move.promotion != chess.QUEEN:
                continue
            
            # --- STRICT FILTER ---
            # The move MUST originate from a square that we visually confirmed is now empty.
            if from_sq not in missing_squares:
                continue
            
            # Score Components
            score = 0.0
            
            # 1. Destination Confirmation (YOLO)
            # If we see a new piece at dest, huge bonus.
            if to_sq in new_squares:
                score += 100.0
            # If it's a capture (dest was in FEN, and still in YOLO), we must rely on Diff/Logic.
            # Captures are tricky because 'occupancy' doesn't change.
            elif to_sq in current_piece_squares:
                 # It's a capture! The piece at 'to_sq' is still there (replaced by attacker).
                 # We give this a significant bonus because it aligns with visual evidence (occupancy).
                 # This distinguishes captures from "move to empty square that yolo thinks is empty".
                 score += 50.0

            # 2. Diff Validation
            # Even if YOLO says fine, Diff helps tie-break.
            from_change = change_lookup.get(from_sq)
            to_change = change_lookup.get(to_sq)
            from_mag = from_change.magnitude if from_change else 0.0
            to_mag = to_change.magnitude if to_change else 0.0
            
            diff_score = from_mag + to_mag * 1.5
            
            # If we don't have the "New Piece" bonus, we need decent Diff support
            if score < 50.0 and diff_score < 2.0:
                # Weak move (No visual arrival + Low diff activity). Likely a flicker on source.
                continue
                
            score += diff_score

            candidates.append({
                'move': f"{from_sq}{to_sq}",
                'score': score
            })

            if best_resolution is None or score > best_resolution.score:
                board_after = board.copy()
                board_after.push(move)
                best_resolution = MoveResolution(
                    fen=board_after.board_fen(),
                    move=move,
                    score=score,
                    turn=turn,
                )
    
    return best_resolution
