# Location: ML/server.py

import uvicorn
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import cv2
import numpy as np
import time

from scripts.detectors import get_board_corners, get_piece_predictions, PIECE_CLASS_NAMES
from scripts.board_mapper import get_perspective_transform, map_pieces_to_board
from scripts.fen_converter import convert_board_to_fen

app = FastAPI(title="Chess Recognition Server")

# (You can optionally keep or remove save_debug_image for production)
def save_debug_image(img_copy, corners, piece_results, class_names):
    """Saves a visual copy of what the models detected."""
    try:
        # Image is already 1024x1024
        for i, (x, y) in enumerate(corners):
            cv2.circle(img_copy, (int(x), int(y)), 10, (0, 0, 255), -1)
        
        for piece in piece_results:
            box = piece.xyxy[0].cpu().numpy()
            class_id = int(piece.cls[0].cpu())
            conf = float(piece.conf[0].cpu())
            if class_id in class_names:
                label = f"{class_names[class_id]} ({conf:.2f})"
                cv2.rectangle(img_copy, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (0, 255, 0), 2)
                cv2.putText(img_copy, label, (int(box[0]), int(box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        cv2.imwrite("debug_output.jpg", img_copy)
        print("INFO:     Saved debug_output.jpg")
    except Exception as e:
        print(f"Error saving debug image: {e}")


def run_full_pipeline(image_bytes):
    """
    Takes raw image bytes and runs the complete recognition pipeline.
    """
    # 1. Decode the image
    nparr = np.frombuffer(image_bytes, np.uint8)
    img_original = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_original is None:
        raise ValueError("Could not decode image.")

    
    # 2. Resize the image ONCE to the size our models were trained on.
    img_resized = cv2.resize(img_original, (1024, 1024))

    # --- 3. Find Board Corners (on resized image) ---
    corners = get_board_corners(img_resized)
    if corners is None:
        raise ValueError("Could not find board corners.")
    
    # --- 4. Get Perspective Transform (with Classic Sort) ---
    matrix, output_size = get_perspective_transform(corners)
    
    # --- 5. Find All Pieces (on resized image) ---
    piece_results = get_piece_predictions(img_resized)
    
    # --- 6. Map Pieces to Board ---
    board_state = map_pieces_to_board(
        piece_results, 
        PIECE_CLASS_NAMES, 
        matrix, 
        output_size
    )
    
    # --- 7. Convert to FEN ---
    fen_string = convert_board_to_fen(board_state)
    
    # --- 8. Save Debug Image ---
    save_debug_image(img_resized, corners, piece_results, PIECE_CLASS_NAMES)
    
    return fen_string, board_state

# (Keep the @app.post and if __name__ == "__main__" sections)
@app.post("/recognize_board/")
async def recognize_board_endpoint(file: UploadFile = File(...)):
    start_time = time.time()
    try:
        image_bytes = await file.read()
        fen, board = run_full_pipeline(image_bytes)
        end_time = time.time()
        processing_time = end_time - start_time
        
        return JSONResponse(content={
            "status": "success",
            "fen": fen,
            "board_state": board,
            "processing_time_seconds": round(processing_time, 2)
        })
    except Exception as e:
        print(f"ERROR: {e}") 
        return JSONResponse(status_code=400, content={
            "status": "error",
            "message": str(e)
        })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)