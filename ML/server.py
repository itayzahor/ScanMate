# Location: ML/server.py

import asyncio
import os
import time
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

app = FastAPI(title="Chess Recognition Server")


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




def run_full_pipeline(image_bytes):
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
        
        fen = run_full_pipeline(image_bytes)
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)