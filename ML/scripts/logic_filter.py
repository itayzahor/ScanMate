"""Legal-move reconciliation for noisy detections."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chess


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


@dataclass(frozen=True)
class LogicFilterDecision:
    fen: str
    accepted_candidate: bool
    matched_move: Optional[str]
    fallback_reason: Optional[str]


def _normalize_piece_fen(piece_fen: str) -> tuple[str, bool]:
    fen = piece_fen.strip()
    if not fen:
        return "", False
    try:
        castle = infer_castling_rights(fen)
        board = chess.Board(f"{fen} w {castle} - 0 1")
    except ValueError:
        return fen, False
    return board.board_fen(), True


def _board_from_fen(fen: str, turn: chess.Color) -> Optional[chess.Board]:
    try:
        castle = infer_castling_rights(fen)
        return chess.Board(f"{fen} {'w' if turn else 'b'} {castle} - 0 1")
    except ValueError:
        return None


def _match_legal_transition(previous_fen: str, candidate_fen: str) -> Optional[chess.Move]:
    for turn in (chess.WHITE, chess.BLACK):
        board = _board_from_fen(previous_fen, turn)
        if board is None:
            continue
        for move in board.legal_moves:
            probe = board.copy()
            probe.push(move)
            if probe.board_fen() == candidate_fen:
                return move
    return None


def apply_logic_filter(candidate_fen: str, previous_fen: Optional[str]) -> LogicFilterDecision:
    candidate_norm, candidate_valid = _normalize_piece_fen(candidate_fen)
    
    
    if previous_fen is None or not previous_fen.strip():
        return LogicFilterDecision(
            fen=candidate_norm,
            accepted_candidate=True,
            matched_move=None,
            fallback_reason=None,
        )

    previous_norm, previous_valid = _normalize_piece_fen(previous_fen)
    
    if not previous_valid:
        return LogicFilterDecision(
            fen=candidate_norm,
            accepted_candidate=True,
            matched_move=None,
            fallback_reason="invalid_previous_fen",
        )

    if not candidate_valid:
        return LogicFilterDecision(
            fen=previous_norm,
            accepted_candidate=False,
            matched_move=None,
            fallback_reason="invalid_candidate_fen",
        )

    if candidate_norm == previous_norm:
        return LogicFilterDecision(
            fen=candidate_norm,
            accepted_candidate=True,
            matched_move=None,
            fallback_reason=None,
        )

    move = _match_legal_transition(previous_norm, candidate_norm)
    if move:
        return LogicFilterDecision(
            fen=candidate_norm,
            accepted_candidate=True,
            matched_move=move.uci(),
            fallback_reason=None,
        )

    return LogicFilterDecision(
        fen=previous_norm,
        accepted_candidate=False,
        matched_move=None,
        fallback_reason="candidate_not_legal_transition",
    )
