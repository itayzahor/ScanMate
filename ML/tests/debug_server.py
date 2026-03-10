# Location: ML/debug_server.py

import uvicorn
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import cv2
import numpy as np
import time
import base64  
from fastapi.responses import JSONResponse, HTMLResponse
from typing import Optional

from scripts.detectors import get_board_corners, get_piece_predictions, PIECE_CLASS_NAMES, IMAGE_SIZE
# board_mapper.py (shim during transition)
from scripts.board_orientation import get_perspective_transform, orient_board_state_for_white
from scripts.piece_mapping import map_pieces_to_board

from scripts.fen_converter import convert_board_to_fen
from scripts.gatekeeper import GatekeeperResult, validate_frame
from scripts.logic_filter import LogicFilterDecision, apply_logic_filter
from scripts.session_state import SessionState, get_session


app = FastAPI(title="Chess Debug Server")
PIECE_PERSISTENCE_FRAMES = 3


class FrameRejectedError(Exception):
    def __init__(self, result: GatekeeperResult) -> None:
        super().__init__("Frame rejected by gatekeeper")
        self.result = result

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

            if class_id in PIECE_CLASS_NAMES:
                label = PIECE_CLASS_NAMES[class_id]
                cv2.rectangle(img_with_grid_and_pieces, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), grid_color_green, 2)
                cv2.putText(img_with_grid_and_pieces, label, (int(box[0]), int(box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, grid_color_green, 2)

        debug_images["04_combined_pieces_and_grid"] = encode_image_to_base64(img_with_grid_and_pieces)

        print("INFO:     All debug images encoded.")
        return debug_images

    except Exception as e:
        print(f"Error generating debug visuals: {e}")
        return {}


def run_full_pipeline(image_bytes, session: Optional[SessionState] = None):
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
    gatekeeper_result = validate_frame(img_resized)
    if not gatekeeper_result.is_valid:
        raise FrameRejectedError(gatekeeper_result)

    # 4. Find Board Corners
    corners = get_board_corners(img_resized)
    if corners is None:
        raise ValueError("Could not find board corners.")
    print(f"[debug] detected corners: {corners}")
    # 5. Get Perspective Transform
    homography = get_perspective_transform(corners, img_resized)
    
    # 6. Get Warped Image (for debug)
    warped_image = cv2.warpPerspective(img_resized, homography, (IMAGE_SIZE, IMAGE_SIZE))
    
    # 7. Find All Pieces
    piece_boxes = get_piece_predictions(img_resized)
    
    # 8. Map Pieces to Board
    board_state = map_pieces_to_board(
        piece_boxes,
        PIECE_CLASS_NAMES,
        homography, 
    )
    print(board_state)
    board_state = orient_board_state_for_white(board_state)
    if session:
        board_state = session.blend_board(board_state, persistence_frames=PIECE_PERSISTENCE_FRAMES)
    
    # 9. Convert to FEN & apply logic filter
    fen_string = convert_board_to_fen(board_state)
    previous_fen = session.get_last_fen() if session else None
    logic_decision = apply_logic_filter(fen_string, previous_fen)
    if session:
        session.update_last_fen(logic_decision.fen)
    
    # 10. Generate ALL Debug Images
    debug_visuals = generate_all_debug_visuals(img_resized, warped_image, corners, piece_boxes, homography, IMAGE_SIZE)
    
    return board_state, logic_decision, gatekeeper_result, debug_visuals


# --- 4. UPDATE THE API ENDPOINT ---
@app.post("/recognize_board/")
async def recognize_board_endpoint(file: UploadFile = File(...), session_id: Optional[str] = None):
    """
    The main API endpoint. Receives an image, runs the
    pipeline, and returns the FEN string + debug images.
    """
    start_time = time.time()
    
    try:
        image_bytes = await file.read()
        session = get_session(session_id)
        
        board, logic_decision, gatekeeper_result, debug_images = run_full_pipeline(image_bytes, session=session)
        
        end_time = time.time()
        processing_time = end_time - start_time
        diagnostics = {
            "gatekeeper": {
                "issues": gatekeeper_result.issues,
                "blur_variance": round(gatekeeper_result.blur_variance, 2),
                "hand_count": gatekeeper_result.hand_count,
            },
            "logic_filter": {
                "accepted_candidate": logic_decision.accepted_candidate,
                "matched_move": logic_decision.matched_move,
                "fallback_reason": logic_decision.fallback_reason,
            },
        }

        return JSONResponse(content={
            "status": "success",
            "fen": logic_decision.fen,
            "board_state": board,
            "processing_time_seconds": round(processing_time, 2),
            "diagnostics": diagnostics,
            "debug_images": debug_images,
        })
        
    except FrameRejectedError as exc:
        result = exc.result
        print(
            f"[gatekeeper][debug] Rejected frame: issues={result.issues} blur={result.blur_variance:.1f} hand_count={result.hand_count}"
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
    except Exception as e:
        print(f"ERROR: {e}") 
        return JSONResponse(status_code=400, content={
            "status": "error",
            "message": str(e)
        })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)