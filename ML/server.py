# Location: ML/server.py
"""FastAPI server for chess board recognition and position analysis.

Endpoints
---------
POST   /recognize_position/                Stateless: single image → FEN
POST   /recognize_game/                    Start a game session
POST   /recognize_game/{game_id}/frame     Send one frame during a game
GET    /recognize_game/{game_id}/          Peek at current game state
POST   /recognize_game/{game_id}/end       End game → full SAN move list
DELETE /recognize_game/{game_id}/          Discard a game session
POST   /analyze_position/                  Stockfish evaluation of a FEN
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Optional, Union
from uuid import uuid4

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

import cv2
import numpy as np
import uvicorn
import chess
import chess.engine
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from scripts.detectors import get_board_corners, get_piece_predictions, PIECE_CLASS_NAMES, IMAGE_SIZE
from scripts.board_orientation import get_perspective_transform, orient_board_state_for_white
from scripts.piece_mapping import map_pieces_to_board
from scripts.fen_converter import convert_board_to_fen
from scripts.gatekeeper import validate_frame, HAND_DETECTED, DEFAULT_BLUR_THRESHOLD
from scripts.board_mapper import warp_board_to_grid
from scripts.change_tracker import resolve_move_from_changes
from scripts.session_state import DEFAULT_STARTING_FEN, SessionState

app = FastAPI(title="Chess Recognition Server")


# ---------------------------------------------------------------------------
# Stockfish engine
# ---------------------------------------------------------------------------

def _resolve_stockfish_path() -> str:
    """Return engine path from env or fallback to engines/stockfish bundle."""
    env_path = os.getenv("STOCKFISH_PATH")
    if env_path:
        return env_path

    engines_root = Path(__file__).resolve().parent / "engines" / "stockfish"
    if engines_root.exists():
        preferred_names = [
            "stockfish-windows-x86-64-avx2.exe",
            "stockfish-windows-x86-64-modern.exe",
            "stockfish.exe",
            "stockfish",
        ]
        for name in preferred_names:
            candidate = engines_root / name
            if candidate.exists():
                return str(candidate)

        for candidate in engines_root.iterdir():
            if candidate.is_file() and "stockfish" in candidate.name.lower():
                return str(candidate)

    return "stockfish"


_STOCKFISH_PATH = _resolve_stockfish_path()
_engine: Optional[chess.engine.SimpleEngine] = None


@app.on_event("startup")
def _init_engine():
    global _engine
    try:
        _engine = chess.engine.SimpleEngine.popen_uci(_STOCKFISH_PATH)
        info = _engine.id.get("name", "stockfish")
        print(f"[engine] Loaded {info} from '{_STOCKFISH_PATH}'")
    except FileNotFoundError as exc:
        print(f"[engine] Stockfish binary not found: {exc}")
        _engine = None
    except Exception as exc:
        print(f"[engine] Failed to start Stockfish: {exc}")
        _engine = None


@app.on_event("shutdown")
def _shutdown_engine():
    global _engine
    if _engine is not None:
        _engine.quit()
        _engine = None


# ---------------------------------------------------------------------------
# POST /recognize_position/ — stateless single-image recognition
# ---------------------------------------------------------------------------

def _run_stateless_pipeline(image_bytes: bytes) -> Optional[str]:
    """Decode an image and return the detected board position as FEN.

    Returns None when no chessboard is found in the image.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image.")

    img_resized = cv2.resize(img, (IMAGE_SIZE, IMAGE_SIZE))

    corners = get_board_corners(img_resized)
    if corners is None:
        return None

    homography = get_perspective_transform(corners, img_resized)
    piece_boxes = get_piece_predictions(img_resized)

    board_state = map_pieces_to_board(piece_boxes, PIECE_CLASS_NAMES, homography)
    board_state = orient_board_state_for_white(board_state)

    return convert_board_to_fen(board_state)


@app.post("/recognize_position/")
async def recognize_position(file: UploadFile = File(...)):
    """Receive a single image and return the detected board position as FEN."""
    start_time = time.time()
    try:
        image_bytes = await file.read()
        fen = _run_stateless_pipeline(image_bytes)

        if fen is None:
            return JSONResponse(status_code=422, content={
                "status": "error",
                "message": "Failed to recognize a chess board in the image.",
            })

        elapsed = time.time() - start_time
        return JSONResponse(content={
            "status": "success",
            "fen": fen,
            "processing_time_seconds": round(elapsed, 2),
        })
    except Exception as exc:
        return JSONResponse(status_code=400, content={
            "status": "error",
            "message": str(exc),
        })


# ---------------------------------------------------------------------------
# /recognize_game/ — stateful game recognition (frame-by-frame)
# ---------------------------------------------------------------------------

# How many consecutive "no-move" detection frames before discarding a pending move.
_PENDING_IDLE_LIMIT = 3
# Initial hand budget — high enough for the diff detector to warm up.
_HAND_BUDGET_INIT = 5
# How much budget a *new* hand appearance adds.
_HAND_BUDGET_BOOST = 2

_DUMP_GAME_FRAMES = os.getenv("DUMP_GAME_FRAMES", "0").lower() in {"1", "true", "yes", "on"}
_DUMP_GAME_FRAMES_DIR = Path(
    os.getenv(
        "DUMP_GAME_FRAMES_DIR",
        str(Path(__file__).resolve().parent / "runs" / "incoming_frames"),
    )
)
if _DUMP_GAME_FRAMES:
    _DUMP_GAME_FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Game frame dumping enabled: %s", _DUMP_GAME_FRAMES_DIR)


@dataclass
class _GameSession:
    """All mutable state for one in-progress game."""

    game_id: str
    session: SessionState
    moves: list[str] = field(default_factory=list)          # confirmed SAN moves
    current_fen: str = DEFAULT_STARTING_FEN
    expected_turn: Optional[chess.Color] = None              # None = try both
    pending_uci: Optional[str] = None
    pending_san: Optional[str] = None
    pending_idle: int = 0
    frame_count: int = 0
    created_at: float = field(default_factory=time.time)
    lock: Lock = field(default_factory=Lock)
    # Hand-triggered pipeline budget.  When > 0 the full pipeline runs;
    # when 0 only the gatekeeper runs (cheap).  A new hand bumps it up.
    hand_budget: int = _HAND_BUDGET_INIT
    hand_was_present: bool = False  # tracks whether the *previous* frame had a hand
    mode: str = "live"  # "live" or "video"


# Thread-safe registry of active games.
_games: dict[str, _GameSession] = {}
_games_lock = Lock()


def _normalize_starting_fen(raw_fen: Optional[str]) -> str:
    """Validate and normalise a user-supplied FEN to board-only form."""
    if raw_fen is None or not raw_fen.strip():
        return DEFAULT_STARTING_FEN
    fen = raw_fen.strip()
    try:
        board = chess.Board(fen)
    except ValueError:
        try:
            board = chess.Board(f"{fen} w - - 0 1")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid starting_fen: {exc}")
    return board.board_fen()


def _compute_san(previous_fen: str, move: chess.Move, turn: chess.Color) -> str:
    """Return the SAN string (e.g. Nf3) for a move, falling back to UCI."""
    try:
        turn_char = "w" if turn == chess.WHITE else "b"
        board = chess.Board(f"{previous_fen} {turn_char} - - 0 1")
        return board.san(move)
    except Exception:
        return move.uci()


def _dump_received_frame(game: _GameSession, image_bytes: bytes) -> None:
    """Persist incoming frame bytes for visual debugging/comparison."""
    if not _DUMP_GAME_FRAMES:
        return

    frame_index = game.frame_count + 1
    game_dir = _DUMP_GAME_FRAMES_DIR / game.game_id
    game_dir.mkdir(parents=True, exist_ok=True)

    upload_path = game_dir / f"frame_{frame_index:05d}_upload.jpg"
    upload_path.write_bytes(image_bytes)

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        (game_dir / f"frame_{frame_index:05d}_meta.txt").write_text(
            f"decode=failed\nbytes={len(image_bytes)}\n",
            encoding="utf-8",
        )
        return

    h, w = img.shape[:2]
    model_input = cv2.resize(img, (IMAGE_SIZE, IMAGE_SIZE))
    model_path = game_dir / f"frame_{frame_index:05d}_model_{IMAGE_SIZE}x{IMAGE_SIZE}.jpg"
    cv2.imwrite(str(model_path), model_input, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    (game_dir / f"frame_{frame_index:05d}_meta.txt").write_text(
        f"decode=ok\nwidth={w}\nheight={h}\nbytes={len(image_bytes)}\n",
        encoding="utf-8",
    )


def _process_frame(game: _GameSession, image_bytes: bytes) -> dict:
    """Run the full detection pipeline on one frame (mirrors video_viewer logic).

    Returns a JSON-friendly dict describing what happened on this frame.
    """
    # Decode
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image.")
    img_resized = cv2.resize(img, (IMAGE_SIZE, IMAGE_SIZE))

    session = game.session
    game.frame_count += 1

    # Gatekeeper — always runs (cheap relative to YOLO).
    # Video / replay frames are pre-compressed JPEGs with inherently lower
    # Laplacian variance, so use a relaxed blur threshold.
    is_video = game.mode == "video"
    blur_th = 80.0 if is_video else DEFAULT_BLUR_THRESHOLD
    gk = validate_frame(img_resized, blur_threshold=blur_th)
    hand_now = gk.hand_count > 0

    # Update hand budget (live mode only).
    if not is_video:
        if hand_now and not game.hand_was_present:
            game.hand_budget = max(game.hand_budget, _HAND_BUDGET_BOOST)
        game.hand_was_present = hand_now

    if not gk.is_valid:
        # In video mode, only reject if blurry (not just hand)
        if is_video:
            only_hand = gk.issues == [HAND_DETECTED]
            if only_hand:
                pass  # allow through
            else:
                print(f"[Frame {game.frame_count}] rejected: {gk.issues} blur={gk.blur_variance:.1f}")
                return {"status": "rejected", "fen": game.current_fen, "move_number": len(game.moves)}
        else:
            print(f"[Frame {game.frame_count}] rejected: {gk.issues} blur={gk.blur_variance:.1f} hands={gk.hand_count}")
            return {"status": "rejected", "fen": game.current_fen, "move_number": len(game.moves)}

    # If budget is exhausted, skip the expensive pipeline (live mode only).
    if not is_video and game.hand_budget <= 0:
        return {"status": "skipped", "fen": game.current_fen, "move_number": len(game.moves)}

    if not is_video:
        game.hand_budget -= 1

    # Corner detection
    corners = get_board_corners(img_resized)
    if corners is None or len(corners) != 4:
        print(f"[Frame {game.frame_count}] no board corners detected")
        return {"status": "no_board", "fen": game.current_fen, "move_number": len(game.moves)}

    # Perspective transform + warp
    h_matrix = get_perspective_transform(corners, img_resized)
    warped = warp_board_to_grid(img_resized, h_matrix, IMAGE_SIZE)

    # Piece detection
    piece_boxes = get_piece_predictions(img_resized)
    board_state = map_pieces_to_board(piece_boxes, PIECE_CLASS_NAMES, h_matrix)
    board_oriented = orient_board_state_for_white(board_state)

    print(f"[Frame {game.frame_count}] corners=OK pieces={len(piece_boxes)} moves={game.moves}")

    # Current piece squares from raw YOLO (before smoothing)
    current_piece_squares: set[str] = set()
    if board_oriented:
        for rank_idx, rank in enumerate(board_oriented):
            for file_idx, piece in enumerate(rank):
                if piece:
                    square = chr(ord("a") + file_idx) + str(8 - rank_idx)
                    current_piece_squares.add(square)

    # Diff-based change detection
    change = session.detect_square_changes(warped)
    previous_fen = session.get_last_fen()

    if change and change.triggered_count > 0:
        top3 = change.triggered[:3]
        top3_str = ", ".join(f"{t.square}={t.magnitude:.1f}" for t in top3)
        print(f"[Frame {game.frame_count}] change.ready={change.ready} triggered={change.triggered_count} [{top3_str}] pending={game.pending_uci}")
    else:
        print(f"[Frame {game.frame_count}] change.ready={change.ready if change else None} triggered={change.triggered_count if change else None} pending={game.pending_uci}")

    move_san: Optional[str] = None

    if previous_fen and change:
        if not change.ready:
            pass  # diff detector still warming up

        elif change.triggered_count == 0 and game.pending_uci is None:
            pass  # board is quiet, nothing pending

        elif change.triggered_count == 0 and game.pending_uci is not None:
            # Quiet board + pending move → try to confirm via YOLO agreement
            res = resolve_move_from_changes(
                previous_fen=previous_fen,
                detection=change,
                current_piece_squares=current_piece_squares,
                expected_turn=game.expected_turn,
            )
            if res and res.uci == game.pending_uci:
                # YOLO still agrees → CONFIRM
                move_san = game.pending_san or res.move.uci()
                game.current_fen = res.fen
                game.expected_turn = chess.BLACK if res.turn == chess.WHITE else chess.WHITE
                game.moves.append(move_san)
                session.set_piece_squares(current_piece_squares)
                game.pending_uci = None
                game.pending_san = None
                game.pending_idle = 0
            else:
                game.pending_idle += 1
                if game.pending_idle >= _PENDING_IDLE_LIMIT:
                    game.pending_uci = None
                    game.pending_san = None
                    game.pending_idle = 0

        else:
            # Squares changed → try to resolve a move
            res = resolve_move_from_changes(
                previous_fen=previous_fen,
                detection=change,
                current_piece_squares=current_piece_squares,
                expected_turn=game.expected_turn,
            )
            if res:
                candidate_san = _compute_san(previous_fen, res.move, res.turn)

                if game.pending_uci and res.uci == game.pending_uci:
                    # Same move seen again → CONFIRM
                    move_san = candidate_san
                    game.current_fen = res.fen
                    game.expected_turn = chess.BLACK if res.turn == chess.WHITE else chess.WHITE
                    game.moves.append(move_san)
                    session.set_piece_squares(current_piece_squares)
                    game.pending_uci = None
                    game.pending_san = None
                    game.pending_idle = 0
                else:
                    # New / different move → store as pending (not committed yet)
                    game.pending_uci = res.uci
                    game.pending_san = candidate_san
                    game.pending_idle = 0
            else:
                if game.pending_uci is not None:
                    game.pending_idle += 1
                    if game.pending_idle >= _PENDING_IDLE_LIMIT:
                        game.pending_uci = None
                        game.pending_san = None
                        game.pending_idle = 0

    if game.current_fen:
        session.update_last_fen(game.current_fen)

    # Build response
    result: dict = {
        "status": "move_detected" if move_san else "ok",
        "fen": game.current_fen,
        "move_number": len(game.moves),
    }
    if move_san:
        result["move"] = move_san
    if game.pending_uci:
        result["pending"] = game.pending_san or game.pending_uci
    return result


# --- Pydantic models for game endpoints ---

class GameStartRequest(BaseModel):
    starting_fen: Optional[str] = Field(
        None, description="Custom starting position (board-only or full FEN). Defaults to standard."
    )
    mode: Optional[str] = Field(
        "live", description="'live' for camera stream, 'video' for uploaded video."
    )


class GameStartResponse(BaseModel):
    status: str
    game_id: str
    starting_fen: str


class GameFrameResponse(BaseModel):
    status: str
    fen: str
    move_number: int
    move: Optional[str] = None
    pending: Optional[str] = None


class GameStateResponse(BaseModel):
    game_id: str
    starting_fen: str
    current_fen: str
    move_count: int
    moves: list[str]
    frame_count: int


class GameEndResponse(BaseModel):
    status: str
    game_id: str
    moves: list[str]
    move_count: int
    final_fen: str


# --- Endpoints ---

@app.post("/recognize_game/", response_model=GameStartResponse)
async def start_game(payload: GameStartRequest):
    """Create a new game session and return its id."""
    starting_fen = _normalize_starting_fen(payload.starting_fen)
    game_id = uuid4().hex[:12]

    session = SessionState(starting_fen=starting_fen)
    game = _GameSession(game_id=game_id, session=session, current_fen=starting_fen,
                        mode=payload.mode or "live")

    with _games_lock:
        _games[game_id] = game

    if _DUMP_GAME_FRAMES:
        game_dir = _DUMP_GAME_FRAMES_DIR / game_id
        game_dir.mkdir(parents=True, exist_ok=True)
        (game_dir / "session_meta.txt").write_text(
            f"game_id={game_id}\nmode={game.mode}\nstarting_fen={starting_fen}\n",
            encoding="utf-8",
        )
        logger.info("Created game frame dump dir: %s", game_dir)

    return GameStartResponse(status="created", game_id=game_id, starting_fen=starting_fen)


@app.post("/recognize_game/{game_id}/frame", response_model=GameFrameResponse)
async def submit_frame(game_id: str, file: UploadFile = File(...)):
    """Submit one frame to an active game. Returns per-frame detection result."""
    with _games_lock:
        game = _games.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    image_bytes = await file.read()

    try:
        with game.lock:
            _dump_received_frame(game, image_bytes)
            result = _process_frame(game, image_bytes)
    except Exception:
        logging.exception("Error processing frame %d for game %s", game.frame_count, game_id)
        return GameFrameResponse(status="error", fen=game.current_fen, move_number=len(game.moves))

    return GameFrameResponse(**result)


@app.get("/recognize_game/{game_id}/", response_model=GameStateResponse)
async def get_game_state(game_id: str):
    """Peek at the current state of an active game."""
    with _games_lock:
        game = _games.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    return GameStateResponse(
        game_id=game.game_id,
        starting_fen=game.session.starting_fen or DEFAULT_STARTING_FEN,
        current_fen=game.current_fen,
        move_count=len(game.moves),
        moves=list(game.moves),
        frame_count=game.frame_count,
    )


@app.post("/recognize_game/{game_id}/end", response_model=GameEndResponse)
async def end_game(game_id: str):
    """End a game and return the full move list. Removes the session."""
    with _games_lock:
        game = _games.pop(game_id, None)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    # Auto-confirm any pending move so the last detected move isn't lost.
    if game.pending_san:
        game.moves.append(game.pending_san)
        print(f"[endGame] Auto-confirmed pending move: {game.pending_san}")

    return GameEndResponse(
        status="completed",
        game_id=game_id,
        moves=list(game.moves),
        move_count=len(game.moves),
        final_fen=game.current_fen,
    )


@app.delete("/recognize_game/{game_id}/")
async def discard_game(game_id: str):
    """Discard a game session without returning results."""
    with _games_lock:
        game = _games.pop(game_id, None)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return JSONResponse(content={"status": "discarded", "game_id": game_id})


# ---------------------------------------------------------------------------
# POST /analyze_position/ — Stockfish evaluation
# ---------------------------------------------------------------------------

class AnalysisRequest(BaseModel):
    fen: str = Field(..., description="Position in Forsyth-Edwards Notation")
    depth: Optional[int] = Field(14, ge=1, le=40, description="Search depth")
    multipv: Optional[int] = Field(1, ge=1, le=5, description="Number of candidate lines")


class AnalysisLine(BaseModel):
    best_move: str
    best_move_san: str
    evaluation: dict
    pv: list[str]


class AnalysisResponse(BaseModel):
    status: str
    lines: list[AnalysisLine]
    depth: int
    engine: str


@app.post("/analyze_position/", response_model=AnalysisResponse)
async def analyze_position(request: AnalysisRequest):
    if _engine is None:
        raise HTTPException(status_code=503, detail="Stockfish engine is not available on the server.")

    try:
        board = chess.Board(request.fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid FEN: {exc}")

    missing_kings = []
    if board.king(chess.WHITE) is None:
        missing_kings.append("white king")
    if board.king(chess.BLACK) is None:
        missing_kings.append("black king")

    if missing_kings:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid FEN: missing {' and '.join(missing_kings)}",
        )

    if not board.is_valid():
        raise HTTPException(status_code=400, detail="Invalid FEN: board state is not valid chess.")

    limit = chess.engine.Limit(depth=request.depth or 14)
    multipv = request.multipv or 1

    try:
        raw_info = await asyncio.to_thread(_engine.analyse, board, limit, multipv=multipv)
    except chess.engine.EngineTerminatedError:
        raise HTTPException(status_code=500, detail="Stockfish engine terminated unexpectedly.")
    except chess.engine.EngineError as exc:
        raise HTTPException(status_code=500, detail=f"Engine error: {exc}")

    infos = raw_info if isinstance(raw_info, list) else [raw_info]
    response_lines: list[AnalysisLine] = []

    for info in infos:
        pv_moves = info.get("pv", [])
        if not pv_moves:
            continue

        pv_san: list[str] = []
        pv_board = board.copy()
        for move in pv_moves:
            pv_san.append(pv_board.san(move))
            pv_board.push(move)

        score = info.get("score")
        evaluation: dict[str, Union[int, str, None]]
        if score is None:
            evaluation = {"type": "unknown", "value": None}
        else:
            score = score.white()
            if score.is_mate():
                evaluation = {"type": "mate", "value": score.mate()}
            else:
                evaluation = {"type": "cp", "value": score.score()}

        response_lines.append(AnalysisLine(
            best_move=pv_moves[0].uci(),
            best_move_san=pv_san[0],
            evaluation=evaluation,
            pv=pv_san,
        ))

    if not response_lines:
        raise HTTPException(status_code=500, detail="Engine returned no analysis.")

    return AnalysisResponse(
        status="success",
        lines=response_lines,
        depth=limit.depth or request.depth or 0,
        engine=_engine.id.get("name", "stockfish") if _engine else "unknown",
    )


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")