# Location: ML/server.py

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

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
from scripts.gatekeeper import GatekeeperResult, validate_frame
from scripts.logic_filter import LogicFilterDecision, apply_logic_filter
from scripts.change_tracker import (
    ChangeDetectionResult,
    warp_board_to_grid,
    resolve_move_from_changes,
)
from scripts.session_state import (
    DEFAULT_STARTING_FEN,
    SessionRecord,
    SessionState,
    create_session,
    describe_session,
    get_session,
    list_sessions,
    remove_session,
)

app = FastAPI(title="Chess Recognition Server")

PIECE_PERSISTENCE_FRAMES = 3


class FrameRejectedError(Exception):
    def __init__(self, result: GatekeeperResult) -> None:
        super().__init__("Frame rejected by gatekeeper")
        self.result = result


@dataclass
class PipelineResult:
    fen: str
    gatekeeper: Optional[GatekeeperResult]
    logic: LogicFilterDecision
    detection_mode: str
    diff: Optional[ChangeDetectionResult]
    piece_count: Optional[int]
    move_uci: Optional[str]
    move_san: Optional[str]
    diff_squares: Optional[list[dict[str, float | str]]]


def _normalize_starting_fen(raw_fen: Optional[str]) -> Optional[str]:
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


def _board_from_fen_turn(fen: str, turn: chess.Color) -> Optional[chess.Board]:
    try:
        return chess.Board(f"{fen} {'w' if turn else 'b'} - - 0 1")
    except ValueError:
        return None


def _is_valid_position(fen: str) -> bool:
    """Check if FEN represents a valid chess position (has both kings, legal placement)."""
    try:
        for turn in (chess.WHITE, chess.BLACK):
            board = chess.Board(f"{fen} {'w' if turn else 'b'} - - 0 1")
            if board.king(chess.WHITE) is not None and board.king(chess.BLACK) is not None:
                if board.is_valid():
                    return True
        return False
    except ValueError:
        return False


def _move_san_from_move(previous_fen: Optional[str], move: chess.Move, turn: chess.Color) -> Optional[str]:
    if not previous_fen:
        return None
    board = _board_from_fen_turn(previous_fen, turn)
    if board is None:
        return None
    try:
        return board.san(move)
    except ValueError:
        return None


def _move_san_from_uci(previous_fen: Optional[str], move_uci: Optional[str]) -> Optional[str]:
    if not previous_fen or not move_uci:
        return None
    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        return None
    for turn in (chess.WHITE, chess.BLACK):
        board = _board_from_fen_turn(previous_fen, turn)
        if board is None or move not in board.legal_moves:
            continue
        try:
            return board.san(move)
        except ValueError:
            continue
    return None


def _summarize_diff_squares(
    diff_result: Optional[ChangeDetectionResult],
    limit: int = 8,
) -> Optional[list[dict[str, float | str]]]:
    if diff_result is None:
        return None
    squares: list[dict[str, float | str]] = []
    for change in diff_result.triggered[:limit]:
        squares.append(
            {
                "square": change.square,
                "z_score": float(change.z_score),
                "delta": float(change.delta),
                "intensity": float(change.intensity),
            }
        )
    return squares or None


def _ts_to_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _session_record_to_info(record: SessionRecord) -> SessionInfo:
    return SessionInfo(
        session_id=record.session_id,
        starting_fen=record.starting_fen,
        persistence_frames=record.persistence_frames,
        created_at=_ts_to_iso(record.created_at),
        last_activity_at=_ts_to_iso(record.state.last_used),
    )


def resolve_stockfish_path() -> str:
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


STOCKFISH_PATH = resolve_stockfish_path()
engine: Optional[chess.engine.SimpleEngine] = None
class AnalysisRequest(BaseModel):
    fen: str = Field(..., description="Position in Forsyth-Edwards Notation")
    depth: Optional[int] = Field(14, ge=1, le=40, description="Search depth for Stockfish")
    multipv: Optional[int] = Field(1, ge=1, le=5, description="Number of candidate lines to return")


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


class SessionInfo(BaseModel):
    session_id: str
    starting_fen: Optional[str]
    persistence_frames: int
    created_at: str
    last_activity_at: str


class SessionCreateRequest(BaseModel):
    session_id: Optional[str] = Field(
        None,
        description="Provide to control the identifier; otherwise a UUID is generated.",
        min_length=1,
        max_length=64,
    )
    starting_fen: Optional[str] = Field(
        None,
        description="Optional custom FEN (either full or board-only) to seed the session history.",
    )
    persistence_frames: int = Field(
        PIECE_PERSISTENCE_FRAMES,
        ge=1,
        le=12,
        description="How many frames a piece remains when detections temporarily drop.",
    )


class SessionCreateResponse(BaseModel):
    status: str
    session: SessionInfo


class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]


class SessionDetailResponse(BaseModel):
    session: SessionInfo


class SessionDeleteResponse(BaseModel):
    status: str
    session_id: str

@app.post("/analyze_position/", response_model=AnalysisResponse)
async def analyze_position(request: AnalysisRequest):
    if engine is None:
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

    limit = chess.engine.Limit(depth=request.depth) if request.depth else chess.engine.Limit(depth=14)
    multipv = request.multipv or 1

    try:
        raw_info = await asyncio.to_thread(engine.analyse, board, limit, multipv=multipv)
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

        best_move_uci = pv_moves[0].uci()
        best_move_san = pv_san[0]

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
            best_move=best_move_uci,
            best_move_san=best_move_san,
            evaluation=evaluation,
            pv=pv_san,
        ))

    if not response_lines:
        raise HTTPException(status_code=500, detail="Engine returned no analysis.")

    return AnalysisResponse(
        status="success",
        lines=response_lines,
        depth=limit.depth or request.depth or 0,
        engine=engine.id.get("name", "stockfish") if engine else "unknown",
    )


@app.post("/sessions/", response_model=SessionCreateResponse)
async def create_session_endpoint(payload: SessionCreateRequest):
    starting_fen = _normalize_starting_fen(payload.starting_fen)
    persistence = payload.persistence_frames or PIECE_PERSISTENCE_FRAMES

    try:
        record = create_session(
            session_id=payload.session_id,
            starting_fen=starting_fen,
            persistence_frames=persistence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return SessionCreateResponse(
        status="created",
        session=_session_record_to_info(record),
    )


@app.get("/sessions/", response_model=SessionListResponse)
async def list_sessions_endpoint():
    records = sorted(
        list_sessions(),
        key=lambda record: record.state.last_used,
        reverse=True,
    )
    return SessionListResponse(
        sessions=[_session_record_to_info(record) for record in records],
    )


@app.get("/sessions/{session_id}/", response_model=SessionDetailResponse)
async def describe_session_endpoint(session_id: str):
    record = describe_session(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetailResponse(session=_session_record_to_info(record))


@app.delete("/sessions/{session_id}/", response_model=SessionDeleteResponse)
async def delete_session_endpoint(session_id: str):
    removed = remove_session(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDeleteResponse(status="deleted", session_id=session_id)


def run_stateless_pipeline(image_bytes) -> PipelineResult:
    """
    Takes raw image bytes and runs the complete recognition pipeline.
    """
    # 1. Decode the image
    nparr = np.frombuffer(image_bytes, np.uint8)
    img_original = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_original is None:
        raise ValueError("Could not decode image.")

    # 2. Resize the image ONCE
    img_resized = cv2.resize(img_original, (IMAGE_SIZE, IMAGE_SIZE))

    # 3. Find Board Corners
    corners = get_board_corners(img_resized)
    if corners is None:
        return None
    
    # 4. Get Perspective Transform
    homography = get_perspective_transform(corners, img_resized)
    
    # 5. Find All Pieces
    piece_boxes = get_piece_predictions(img_resized)
    
    # 6. Map Pieces to Board
    board_state = map_pieces_to_board(
        piece_boxes,
        PIECE_CLASS_NAMES,
        homography, 
    )
    board_state = orient_board_state_for_white(board_state)

    # 7. Convert to FEN
    fen_string = convert_board_to_fen(board_state)
    return fen_string
    

@app.on_event("startup")
def init_engine():
    global engine
    try:
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        info = engine.id.get("name", "stockfish")
        print(f"[engine] Loaded {info} from '{STOCKFISH_PATH}'")
    except FileNotFoundError as exc:
        print(f"[engine] Stockfish binary not found: {exc}")
        engine = None
    except Exception as exc:
        print(f"[engine] Failed to start Stockfish: {exc}")
        engine = None


@app.on_event("shutdown")
def shutdown_engine():
    global engine
    if engine is not None:
        engine.quit()
        engine = None



@app.post("/recognize_board/")
async def recognize_board_endpoint(file: UploadFile = File(...)):
    """
    Receives an image, runs the pipeline, and returns the FEN string.
    """
    start_time = time.time()
    
    try:
        image_bytes = await file.read()
        print(
            f"[recognize_board] Received upload: name={file.filename} size={len(image_bytes)} bytes"
        )
        
        fen = run_stateless_pipeline(image_bytes)
        if fen is None:
            return JSONResponse(status_code=422, content={
                "status": "error",
                "message": "Failed to recognize a chess board in the image."
            })
        print(f"[recognize_board] Recognized FEN: {fen}")
        
        end_time = time.time()
        processing_time = end_time - start_time
        print(
            f"[recognize_board] Finished processing in {processing_time:.2f}s"
        )
        
        return JSONResponse(content={
            "status": "success",
            "fen": fen,
            "processing_time_seconds": round(processing_time, 2),
        })
        
    except Exception as e:
        print(f"ERROR: {e}") 
        return JSONResponse(status_code=400, content={
            "status": "error",
            "message": str(e)
        })


def run_full_pipeline(
    image_bytes,
    session: Optional[SessionState] = None,
    *,
    gatekeeper_enabled: bool = True,
):
    """
    Takes raw image bytes and runs the complete recognition pipeline.
    """
    # 1. Decode the image
    nparr = np.frombuffer(image_bytes, np.uint8)
    img_original = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_original is None:
        raise ValueError("Could not decode image.")

    # 2. Resize the image ONCE
    img_resized = cv2.resize(img_original, (IMAGE_SIZE, IMAGE_SIZE))

    # 3. Gatekeeper checks (blur + hand occlusion)
    gatekeeper_result = GatekeeperResult(is_valid=True, issues=[], blur_variance=0.0, hand_count=0)
    if gatekeeper_enabled:
        gatekeeper_result = validate_frame(img_resized)
        if not gatekeeper_result.is_valid:
            raise FrameRejectedError(gatekeeper_result)

    # 4. Find Board Corners
    corners = get_board_corners(img_resized)
    if corners is None:
        return None
    
    # 5. Get Perspective Transform
    homography = get_perspective_transform(corners, img_resized)

    # 6. Find all pieces (needed for both orientation check and fallback detection)
    piece_boxes = get_piece_predictions(img_resized)
    piece_count = len(piece_boxes) if piece_boxes is not None else 0

    # 7. Map pieces to board and orient for white
    board_state = map_pieces_to_board(
        piece_boxes,
        PIECE_CLASS_NAMES,
        homography,
    )
    board_state_oriented = orient_board_state_for_white(board_state)

    previous_fen = session.get_last_fen() if session else None
    diff_result: Optional[ChangeDetectionResult] = None
    detection_mode = "piece_detection"
    logic_decision: Optional[LogicFilterDecision] = None
    reset_tracker = False
    move_uci: Optional[str] = None
    move_san: Optional[str] = None
    diff_squares: Optional[list[dict[str, float | str]]] = None

    if session:
        warped_board = warp_board_to_grid(img_resized, homography)
        # Orient warped board same way as piece board
        if board_state != board_state_oriented:  # Was rotated
            warped_board = cv2.rotate(warped_board, cv2.ROTATE_180)
        diff_result = session.detect_square_changes(warped_board)
    else:
        diff_result = None
    diff_squares = _summarize_diff_squares(diff_result)

    if previous_fen and diff_result:
        # Only reset when diff is ready AND we see catastrophic noise
        # During warmup (not ready), high z-scores are expected after gatekeeper gaps
        if diff_result.ready and diff_result.triggered_count > 20:
            reset_tracker = True
        else:
            move_resolution = resolve_move_from_changes(previous_fen, diff_result)
            if move_resolution:
                logic_decision = LogicFilterDecision(
                    fen=move_resolution.fen,
                    accepted_candidate=True,
                    matched_move=move_resolution.uci,
                    fallback_reason=None,
                )
                detection_mode = "diff_tracking"
                move_uci = move_resolution.uci
                move_san = _move_san_from_move(previous_fen, move_resolution.move, move_resolution.turn)

    if logic_decision is None:
        # 8. Use already computed board state and apply blending
        if session:
            board_state_oriented = session.blend_board(board_state_oriented, persistence_frames=PIECE_PERSISTENCE_FRAMES)

        # 9. Convert to FEN and run legal reconciliation
        fen_string = convert_board_to_fen(board_state_oriented)
        logic_decision = apply_logic_filter(fen_string, previous_fen)
        detection_mode = "piece_detection"
        
        # If logic filter rejected but we have a valid position (both kings present),
        # accept it as a multi-move jump when diff tracking isn't available
        if not logic_decision.accepted_candidate and _is_valid_position(fen_string):
            logic_decision = LogicFilterDecision(
                fen=fen_string,
                accepted_candidate=True,
                matched_move=None,
                fallback_reason="valid_position_multi_move_jump",
            )
        
        if logic_decision.matched_move and move_uci is None:
            move_uci = logic_decision.matched_move
            move_san = _move_san_from_uci(previous_fen, move_uci)

    if session:
        session.update_last_fen(logic_decision.fen)
        if reset_tracker:
            session.reset_change_tracker()

    return PipelineResult(
        fen=logic_decision.fen,
        gatekeeper=gatekeeper_result,
        logic=logic_decision,
        detection_mode=detection_mode,
        diff=diff_result,
        piece_count=piece_count,
        move_uci=move_uci,
        move_san=move_san,
        diff_squares=diff_squares,
    )

@app.post("/recognize_board_session/")
async def recognize_board_session_endpoint(
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
):
    """Session-aware recognition with gatekeeper + smoothing."""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required for this endpoint")

    session = get_session(session_id)
    start_time = time.time()

    try:
        image_bytes = await file.read()
        print(
            f"[recognize_board_session] upload session={session_id} name={file.filename} size={len(image_bytes)}"
        )

        pipeline_result = run_full_pipeline(
            image_bytes,
            session=session,
            gatekeeper_enabled=True,
        )
        if pipeline_result is None:
            return JSONResponse(status_code=422, content={
                "status": "error",
                "message": "Failed to recognize a chess board in the image.",
            })

        elapsed = time.time() - start_time
        print(f"[recognize_board_session] FEN={pipeline_result.fen} session={session_id}")
        print(f"[recognize_board_session] Finished processing in {elapsed:.2f}s")

        diagnostics = {
            "gatekeeper": {
                "issues": pipeline_result.gatekeeper.issues,
                "blur_variance": round(pipeline_result.gatekeeper.blur_variance, 2),
                "hand_count": pipeline_result.gatekeeper.hand_count,
            },
            "logic_filter": {
                "accepted_candidate": pipeline_result.logic.accepted_candidate,
                "matched_move": pipeline_result.logic.matched_move,
                "fallback_reason": pipeline_result.logic.fallback_reason,
            },
        }

        if pipeline_result.diff is not None:
            diff_info = pipeline_result.diff
            diagnostics["diff"] = {
                "ready": diff_info.ready,
                "threshold": round(diff_info.threshold, 3),
                "median_z": round(diff_info.median_z, 3),
                "max_z": round(diff_info.max_z, 3),
                "triggered_count": diff_info.triggered_count,
                "triggered": pipeline_result.diff_squares or [],
            }

        move_info = {
            "uci": pipeline_result.move_uci,
            "san": pipeline_result.move_san,
            "mode": pipeline_result.detection_mode,
        }

        return JSONResponse(content={
            "status": "success",
            "fen": pipeline_result.fen,
            "processing_time_seconds": round(elapsed, 2),
            "mode": pipeline_result.detection_mode,
            "piece_count": pipeline_result.piece_count,
            "move": move_info,
            "diagnostics": diagnostics,
        })

    except FrameRejectedError as exc:
        result = exc.result
        print(
            f"[recognize_board_session] gatekeeper rejected session={session_id} issues={result.issues} blur={result.blur_variance:.1f}"
        )
        return JSONResponse(status_code=422, content={
            "status": "rejected",
            "message": "Frame rejected by gatekeeper.",
            "issues": result.issues,
            "gatekeeper": {
                "blur_variance": round(result.blur_variance, 2),
                "hand_count": result.hand_count,
            },
        })
    except Exception as exc:
        print(f"[recognize_board_session] ERROR: {exc}")
        return JSONResponse(status_code=400, content={
            "status": "error",
            "message": str(exc),
        })




if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)