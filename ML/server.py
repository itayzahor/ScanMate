# Location: ML/server.py

import uvicorn
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import cv2
import numpy as np
import time

from scripts.detectors import get_board_corners, get_piece_predictions, PIECE_CLASS_NAMES, IMAGE_SIZE
from scripts.board_orientation import get_perspective_transform, orient_board_state_for_white
from scripts.piece_mapping import map_pieces_to_board
from scripts.fen_converter import convert_board_to_fen

app = FastAPI(title="Chess Recognition Server")



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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)