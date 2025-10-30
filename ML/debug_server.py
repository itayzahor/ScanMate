# Location: ML/debug_server.py

import uvicorn
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import cv2
import numpy as np
import time
import os
import base64  # <-- 1. IMPORT BASE64
from io import BytesIO
from fastapi.responses import JSONResponse, HTMLResponse

# These files are all CORRECT from our previous steps
from scripts.detectors import get_board_corners, get_piece_predictions, PIECE_CLASS_NAMES
from scripts.board_mapper import get_perspective_transform, map_pieces_to_board
from scripts.fen_converter import convert_board_to_fen

app = FastAPI(title="Chess Debug Server")

# --- 2. ADD THIS NEW ENDPOINT ---
@app.get("/", response_class=HTMLResponse)
async def get_debug_viewer():
    """
    Serves the main HTML debug page.
    """
    try:
        with open("debug_viewer.html", "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Error: debug_viewer.html not found.</h1>", status_code=404)

# --- 2. NEW HELPER FUNCTION ---
def encode_image_to_base64(img_np):
    """Takes an OpenCV (numpy) image and returns a Base64 string."""
    # Encode the image to JPEG in memory
    is_success, buffer = cv2.imencode(".jpg", img_np)
    if not is_success:
        return None
    
    # Convert the in-memory buffer to a Base64 string
    b64_string = base64.b64encode(buffer).decode("utf-8")
    
    # Return it in a format web/mobile apps can read directly
    return "data:image/jpeg;base64," + b64_string

def generate_all_debug_visuals(img_resized, warped_image, corners, piece_results, matrix, output_size):
    """
    Generates the debug images in your requested order and combines
    piece detections with the warped grid. Returns a dict of Base64 strings.
    """
    print("INFO:     Generating debug visuals...")
    debug_images = {}

    try:
        # --- Common Calculations ---
        square_size = output_size / 8
        grid_color_green = (0, 255, 0)
        grid_color_blue = (255, 0, 0)
        grid_dot_color_blue = (255, 0, 0) # Use a distinct name for clarity
        piece_center_color_red = (0, 0, 255)

        # --- 1. Corner Detections (As Requested: First) ---
        img_with_corners = img_resized.copy()
        for i, (x, y) in enumerate(corners):
            cv2.circle(img_with_corners, (int(x), int(y)), 10, piece_center_color_red, -1)
        debug_images["01_corners_detected"] = encode_image_to_base64(img_with_corners)

        # --- 2. Rectified Image + Grid (As Requested: Second) ---
        warped_with_grid = warped_image.copy()
        for i in range(9):
            pt1_v = (int(i * square_size), 0)
            pt2_v = (int(i * square_size), output_size)
            pt1_h = (0, int(i * square_size))
            pt2_h = (output_size, int(i * square_size))
            cv2.line(warped_with_grid, pt1_v, pt2_v, grid_color_green, 1)
            cv2.line(warped_with_grid, pt1_h, pt2_h, grid_color_green, 1)
        debug_images["02_rectified_with_grid"] = encode_image_to_base64(warped_with_grid)

        # --- 3. Generate Warped Grid Points ---
        points_warped = []
        for r in range(9):
            for c in range(9):
                points_warped.append([c * square_size, r * square_size])
        points_warped = np.array(points_warped, dtype=np.float32).reshape(-1, 1, 2)
        H_inv = np.linalg.inv(matrix)
        points_original = cv2.perspectiveTransform(points_warped, H_inv)

        # --- 4. Original Image + Warped Grid (As Requested: Third) ---
        # *** FIX START ***
        # Create a fresh copy for this image
        img_original_with_warped_grid = img_resized.copy()
        # *** FIX END ***
        for (x, y) in points_original.reshape(-1, 2):
             cv2.circle(img_original_with_warped_grid, (int(x), int(y)), 5, grid_dot_color_blue, -1) # Blue dots
        debug_images["03_original_with_warped_grid"] = encode_image_to_base64(img_original_with_warped_grid)


        # --- 5. Piece Detections ON TOP OF Warped Grid (As Requested: Fourth) ---
        # *** FIX START ***
        # Start with the image created in the previous step
        img_with_grid_and_pieces = img_original_with_warped_grid.copy()
         # *** FIX END ***
        for piece in piece_results:
            box = piece.xyxy[0].cpu().numpy()
            class_id = int(piece.cls[0].cpu())
            center_x = int((box[0] + box[2]) / 2)
            center_y = int((box[1] + box[3]) / 2)

            if class_id in PIECE_CLASS_NAMES:
                label = PIECE_CLASS_NAMES[class_id]
                cv2.rectangle(img_with_grid_and_pieces, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), grid_color_green, 2)
                cv2.putText(img_with_grid_and_pieces, label, (int(box[0]), int(box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, grid_color_green, 2)
                cv2.circle(img_with_grid_and_pieces, (center_x, center_y), 5, piece_center_color_red, -1)

        debug_images["04_combined_pieces_and_grid"] = encode_image_to_base64(img_with_grid_and_pieces)

        print("INFO:     All debug images encoded.")
        return debug_images

    except Exception as e:
        print(f"Error generating debug visuals: {e}")
        return {}


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
    img_resized = cv2.resize(img_original, (1024, 1024))

    # 3. Find Board Corners
    corners = get_board_corners(img_resized)
    if corners is None:
        raise ValueError("Could not find board corners.")
    
    # 4. Get Perspective Transform
    matrix, output_size = get_perspective_transform(corners)
    
    # 5. Get Warped Image (for debug)
    warped_image = cv2.warpPerspective(img_resized, matrix, (output_size, output_size))
    
    # 6. Find All Pieces
    piece_results = get_piece_predictions(img_resized)
    
    # 7. Map Pieces to Board
    board_state = map_pieces_to_board(
        piece_results, 
        PIECE_CLASS_NAMES, 
        matrix, 
        output_size
    )
    
    # 8. Convert to FEN
    fen_string = convert_board_to_fen(board_state)
    
    # 9. Generate ALL Debug Images
    debug_visuals = generate_all_debug_visuals(img_resized, warped_image, corners, piece_results, matrix, output_size)
    
    return fen_string, board_state, debug_visuals


# --- 4. UPDATE THE API ENDPOINT ---
@app.post("/recognize_board/")
async def recognize_board_endpoint(file: UploadFile = File(...)):
    """
    The main API endpoint. Receives an image, runs the
    pipeline, and returns the FEN string + debug images.
    """
    start_time = time.time()
    
    try:
        image_bytes = await file.read()
        
        # --- This now returns 3 items ---
        fen, board, debug_images = run_full_pipeline(image_bytes)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # --- We add the debug_images to the response ---
        return JSONResponse(content={
            "status": "success",
            "fen": fen,
            "board_state": board,
            "processing_time_seconds": round(processing_time, 2),
            "debug_images": debug_images  # <-- HERE
        })
        
    except Exception as e:
        print(f"ERROR: {e}") 
        return JSONResponse(status_code=400, content={
            "status": "error",
            "message": str(e)
        })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)