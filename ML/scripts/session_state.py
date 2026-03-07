"""Session-scoped helpers for smoothing recognition outputs."""
from __future__ import annotations

from dataclasses import dataclass
import time
from threading import Lock
from typing import Optional
from uuid import uuid4

import numpy as np

from scripts.change_tracker import ChangeDetectionResult, ChessMoveDetector

BoardState = list[list[Optional[str]]]
DEFAULT_STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


def _copy_board(board: BoardState) -> BoardState:
    return [list(row) for row in board]


def _empty_confidence() -> list[list[int]]:
    return [[0 for _ in range(8)] for _ in range(8)]


class SessionState:
    """Stores last-known board data for a capture session."""

    def __init__(
        self,
        persistence_frames: int = 3,
        starting_fen: Optional[str] = DEFAULT_STARTING_FEN,
    ) -> None:
        self._board_state: Optional[BoardState] = None
        self._square_conf: list[list[int]] = _empty_confidence()
        self._lock = Lock()
        self.persistence_frames = max(1, persistence_frames)
        self.last_used = time.time()
        self._last_fen: Optional[str] = starting_fen
        self.starting_fen = starting_fen
        self._move_detector: Optional[ChessMoveDetector] = None
        self._last_warped_board: Optional[np.ndarray] = None
        self._last_delta: Optional[np.ndarray] = None
        self._previous_piece_squares: Optional[set[str]] = None  # Track piece locations for diff filtering

    def touch(self) -> None:
        self.last_used = time.time()

    def blend_board(self, candidate_board: BoardState, persistence_frames: Optional[int] = None) -> BoardState:
        with self._lock:
            persistence = max(1, persistence_frames or self.persistence_frames)
            candidate_copy = _copy_board(candidate_board)

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
                        blended[row][col] = cell
                        self._square_conf[row][col] = persistence
                    else:
                        if self._square_conf[row][col] > 0 and self._board_state[row][col]:
                            blended[row][col] = self._board_state[row][col]
                            self._square_conf[row][col] -= 1
                        else:
                            blended[row][col] = None
                            self._square_conf[row][col] = 0

            self._board_state = blended
            self.touch()
            return _copy_board(self._board_state)

    def get_last_fen(self) -> Optional[str]:
        with self._lock:
            return self._last_fen

    def update_last_fen(self, fen: Optional[str]) -> None:
        with self._lock:
            self._last_fen = fen
            self.touch()

    def detect_square_changes(self, warped_board: np.ndarray) -> ChangeDetectionResult:
        with self._lock:
            if self._move_detector is None:
                self._move_detector = ChessMoveDetector()
            result = self._move_detector.detect_changes(warped_board)
            self._last_warped_board = warped_board.copy()
            self._last_delta = self._move_detector.last_delta()
            self.touch()
            return result

    def reset_change_tracker(self) -> None:
        with self._lock:
            if self._move_detector is not None:
                self._move_detector.reset()
            self._last_warped_board = None
            self._last_delta = None
            self._previous_piece_squares = None
    
    def get_previous_piece_squares(self) -> Optional[set[str]]:
        with self._lock:
            return self._previous_piece_squares.copy() if self._previous_piece_squares else None
    
    def set_piece_squares(self, piece_squares: set[str]) -> None:
        with self._lock:
            self._previous_piece_squares = piece_squares.copy()

    def get_last_diff_debug(self) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        with self._lock:
            warped = None if self._last_warped_board is None else self._last_warped_board.copy()
            delta = None if self._last_delta is None else self._last_delta.copy()
            return warped, delta


@dataclass
class SessionRecord:
    session_id: str
    state: SessionState
    starting_fen: Optional[str]
    persistence_frames: int
    created_at: float

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "starting_fen": self.starting_fen,
            "persistence_frames": self.persistence_frames,
            "created_at": self.created_at,
            "last_used": self.state.last_used,
        }


class SessionStore:
    """Thread-safe registry of active capture sessions."""

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
        cutoff = time.time() - max_idle_seconds
        with self._lock:
            stale_ids = [
                session_id
                for session_id, record in self._sessions.items()
                if record.state.last_used < cutoff
            ]
            for session_id in stale_ids:
                self._sessions.pop(session_id, None)


default_persistence_frames = 3
session_store = SessionStore()


def get_session(
    session_id: Optional[str],
    *,
    starting_fen: Optional[str] = DEFAULT_STARTING_FEN,
    persistence_frames: int = default_persistence_frames,
) -> Optional[SessionState]:
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
    return session_store.create(
        session_id=session_id,
        starting_fen=starting_fen,
        persistence_frames=persistence_frames,
    )


def remove_session(session_id: str) -> bool:
    return session_store.discard(session_id)


def describe_session(session_id: str) -> Optional[SessionRecord]:
    return session_store.describe(session_id)


def list_sessions() -> list[SessionRecord]:
    return session_store.list()
