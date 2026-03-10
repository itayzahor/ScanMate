"""Session-scoped helpers for smoothing recognition outputs.

This module manages per-game state for the chess scanning pipeline.
Each capture session (started from the app or video viewer) gets its own
SessionState that keeps track of:
  - The last confirmed FEN (for turn enforcement and legal-move filtering)
  - A smoothed board grid (to hide YOLO flicker across frames)
  - A diff-based change detector (to spot which squares changed between frames)
  - The set of previously occupied squares (for move validation)
  - Debug snapshots of the last warped image and pixel-delta

SessionStore is a thread-safe registry that the FastAPI server uses to
manage multiple concurrent sessions.  Module-level convenience functions
(get_session, create_session, …) wrap a global SessionStore singleton.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from threading import Lock
from typing import Optional
from uuid import uuid4

import numpy as np

from scripts.change_tracker import ChangeDetectionResult, ChessMoveDetector

# 8x8 grid where each cell is a piece label (e.g. "white-pawn") or None.
BoardState = list[list[Optional[str]]]

# Standard chess starting position.
DEFAULT_STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


def _copy_board(board: BoardState) -> BoardState:
    """Deep-copy an 8x8 board so mutations don't leak between frames."""
    return [list(row) for row in board]


def _empty_confidence() -> list[list[int]]:
    """Create a zeroed 8x8 confidence grid for board smoothing."""
    return [[0 for _ in range(8)] for _ in range(8)]


class SessionState:
    """Per-game state for one capture session.

    Tracks the smoothed board, the last confirmed FEN, a pixel-diff change
    detector, and the set of occupied squares from the previous move.
    All public methods are thread-safe (guarded by a Lock).
    """

    def __init__(
        self,
        persistence_frames: int = 3,
        starting_fen: Optional[str] = DEFAULT_STARTING_FEN,
    ) -> None:
        # -- Board smoothing state --
        # The last blended 8x8 board (None until the first frame arrives).
        self._board_state: Optional[BoardState] = None
        # Per-square countdown: how many more frames to keep a piece that YOLO
        # stopped seeing.  Resets to `persistence_frames` on each detection.
        self._square_conf: list[list[int]] = _empty_confidence()

        self._lock = Lock()
        # Number of consecutive "miss" frames before a piece is dropped.
        self.persistence_frames = max(1, persistence_frames)
        # Timestamp of last activity (used by SessionStore.prune).
        self.last_used = time.time()

        # -- FEN tracking --
        # The last confirmed position (used for turn enforcement + legality check).
        self._last_fen: Optional[str] = starting_fen
        self.starting_fen = starting_fen

        # -- Diff-based change detection --
        # Lazily created ChessMoveDetector that compares warped board images.
        self._move_detector: Optional[ChessMoveDetector] = None

        # -- Piece-square tracking --
        # Seed piece squares from starting FEN so the first frame has data.
        from scripts.fen_converter import fen_to_piece_squares
        self._previous_piece_squares: Optional[set[str]] = (
            fen_to_piece_squares(starting_fen) if starting_fen else None
        )

    def touch(self) -> None:
        """Bump the last-used timestamp (keeps the session alive)."""
        self.last_used = time.time()

    # ---- Board smoothing ------------------------------------------------

    def blend_board(self, candidate_board: BoardState, persistence_frames: Optional[int] = None) -> BoardState:
        """Merge a new YOLO detection into the smoothed board.

        If YOLO sees a piece → keep it and reset its countdown.
        If YOLO misses a piece that was there before → keep the old piece
        and tick its countdown down by 1.  Once the countdown reaches 0
        the square is cleared.  This hides single-frame detection gaps.
        """
        with self._lock:
            persistence = max(1, persistence_frames or self.persistence_frames)
            candidate_copy = _copy_board(candidate_board)

            # First frame ever: just adopt the candidate as-is.
            if self._board_state is None:
                self._board_state = candidate_copy
                self._square_conf = [
                    [persistence if cell else 0 for cell in row]
                    for row in candidate_copy
                ]
                self.touch()
                return _copy_board(self._board_state)

            blended: BoardState = [[None for _ in range(8)] for _ in range(8)]
            for row in range(8):
                for col in range(8):
                    cell = candidate_copy[row][col]
                    if cell:
                        # YOLO sees a piece → trust it, reset countdown.
                        blended[row][col] = cell
                        self._square_conf[row][col] = persistence
                    else:
                        # YOLO missed this square — keep the old piece while
                        # its countdown is still positive.
                        if self._square_conf[row][col] > 0 and self._board_state[row][col]:
                            blended[row][col] = self._board_state[row][col]
                            self._square_conf[row][col] -= 1
                        else:
                            blended[row][col] = None
                            self._square_conf[row][col] = 0

            self._board_state = blended
            self.touch()
            return _copy_board(self._board_state)

    # ---- FEN tracking ---------------------------------------------------

    def get_last_fen(self) -> Optional[str]:
        """Return the last confirmed board position as a FEN string."""
        with self._lock:
            return self._last_fen

    def update_last_fen(self, fen: Optional[str]) -> None:
        """Store a newly confirmed FEN after a legal move."""
        with self._lock:
            self._last_fen = fen
            self.touch()

    # ---- Diff-based change detection ------------------------------------

    def detect_square_changes(self, warped_board: np.ndarray) -> ChangeDetectionResult:
        """Compare the new warped board image against the previous one.

        Returns a ChangeDetectionResult listing which squares changed.
        """
        with self._lock:
            if self._move_detector is None:
                self._move_detector = ChessMoveDetector()
            result = self._move_detector.detect_changes(warped_board)
            self.touch()
            return result

    def last_delta(self) -> Optional[np.ndarray]:
        """Return the latest pixel-diff map from the change detector."""
        with self._lock:
            if self._move_detector is None:
                return None
            return self._move_detector.last_delta()

    def reset_change_tracker(self) -> None:
        """Wipe all diff state (used when restarting from a new position)."""
        with self._lock:
            if self._move_detector is not None:
                self._move_detector.reset()
            self._previous_piece_squares = None
    
    # ---- Piece-square tracking ------------------------------------------

    def get_previous_piece_squares(self) -> Optional[set[str]]:
        """Squares occupied in the last confirmed position (e.g. {'e2','d2',…})."""
        with self._lock:
            return self._previous_piece_squares.copy() if self._previous_piece_squares else None

    def set_piece_squares(self, piece_squares: set[str]) -> None:
        """Update the occupied-squares snapshot after a confirmed move."""
        with self._lock:
            self._previous_piece_squares = piece_squares.copy()


# ---------------------------------------------------------------------------
# SessionRecord — lightweight wrapper around SessionState with metadata
# ---------------------------------------------------------------------------

@dataclass
class SessionRecord:
    """Pairs a SessionState with its id and creation-time metadata.

    Used by SessionStore to track all active sessions and serialize
    session info for the REST API.
    """
    session_id: str
    state: SessionState
    starting_fen: Optional[str]
    persistence_frames: int
    created_at: float

    def to_dict(self) -> dict[str, object]:
        """JSON-friendly summary (returned by the /sessions/ endpoints)."""
        return {
            "session_id": self.session_id,
            "starting_fen": self.starting_fen,
            "persistence_frames": self.persistence_frames,
            "created_at": self.created_at,
            "last_used": self.state.last_used,
        }


# ---------------------------------------------------------------------------
# SessionStore — thread-safe registry of all active sessions
# ---------------------------------------------------------------------------

class SessionStore:
    """Thread-safe registry of active capture sessions.

    The FastAPI server creates one global SessionStore.  Each incoming
    request looks up (or auto-creates) its session by id.  Idle sessions
    are cleaned up by `prune()`.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = Lock()

    def _build_record(
        self,
        session_id: str,
        *,
        persistence_frames: int,
        starting_fen: Optional[str],
    ) -> SessionRecord:
        state = SessionState(
            persistence_frames=persistence_frames,
            starting_fen=starting_fen,
        )
        return SessionRecord(
            session_id=session_id,
            state=state,
            starting_fen=starting_fen,
            persistence_frames=state.persistence_frames,
            created_at=time.time(),
        )

    def create(
        self,
        session_id: Optional[str] = None,
        *,
        persistence_frames: int = 3,
        starting_fen: Optional[str] = DEFAULT_STARTING_FEN,
    ) -> SessionRecord:
        with self._lock:
            final_id = session_id or uuid4().hex
            if final_id in self._sessions:
                raise ValueError(f"Session '{final_id}' already exists")

            record = self._build_record(
                final_id,
                persistence_frames=persistence_frames,
                starting_fen=starting_fen,
            )
            self._sessions[final_id] = record
            return record

    def get(
        self,
        session_id: str,
        *,
        persistence_frames: int = 3,
        starting_fen: Optional[str] = DEFAULT_STARTING_FEN,
    ) -> SessionState:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                record = self._build_record(
                    session_id,
                    persistence_frames=persistence_frames,
                    starting_fen=starting_fen,
                )
                self._sessions[session_id] = record
            record.state.touch()
            return record.state

    def describe(self, session_id: str) -> Optional[SessionRecord]:
        with self._lock:
            return self._sessions.get(session_id)

    def discard(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def list(self) -> list[SessionRecord]:
        with self._lock:
            return list(self._sessions.values())

    def prune(self, max_idle_seconds: float = 300.0) -> None:
        """Remove sessions that have been idle longer than the threshold."""
        cutoff = time.time() - max_idle_seconds
        with self._lock:
            stale_ids = [
                session_id
                for session_id, record in self._sessions.items()
                if record.state.last_used < cutoff
            ]
            for session_id in stale_ids:
                self._sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Module-level convenience API — wraps a global SessionStore singleton
# ---------------------------------------------------------------------------

default_persistence_frames = 3
session_store = SessionStore()


def get_session(
    session_id: Optional[str],
    *,
    starting_fen: Optional[str] = DEFAULT_STARTING_FEN,
    persistence_frames: int = default_persistence_frames,
) -> Optional[SessionState]:
    """Look up or auto-create a session.  Returns None if no id given."""
    if not session_id:
        return None
    return session_store.get(
        session_id,
        starting_fen=starting_fen,
        persistence_frames=persistence_frames,
    )


def create_session(
    session_id: Optional[str] = None,
    *,
    starting_fen: Optional[str] = DEFAULT_STARTING_FEN,
    persistence_frames: int = default_persistence_frames,
) -> SessionRecord:
    """Create a brand-new session (raises ValueError if id already taken)."""
    return session_store.create(
        session_id=session_id,
        starting_fen=starting_fen,
        persistence_frames=persistence_frames,
    )


def remove_session(session_id: str) -> bool:
    """Delete a session.  Returns True if it existed."""
    return session_store.discard(session_id)


def describe_session(session_id: str) -> Optional[SessionRecord]:
    """Return the SessionRecord for an id, or None."""
    return session_store.describe(session_id)


def list_sessions() -> list[SessionRecord]:
    """Return all active sessions."""
    return session_store.list()
