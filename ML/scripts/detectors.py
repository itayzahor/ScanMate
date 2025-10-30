# Location: ML/scripts/detectors.py

from ultralytics import YOLO
import numpy as np

POSE_MODEL_PATH = "runs/pose_kp_a100_medium_v1/weights/best.pt"
PIECE_MODEL_PATH = "runs/det_pieces_a100_v1_polish/weights/best.pt"


try:
    POSE_MODEL = YOLO(POSE_MODEL_PATH)
    PIECE_MODEL = YOLO(PIECE_MODEL_PATH)
    # Use your specific category mapping, overriding the model's default because our data yaml was wrong.
    PIECE_CLASS_NAMES = {
        0: 'white-pawn',
        1: 'white-rook',
        2: 'white-knight',
        3: 'white-bishop',
        4: 'white-queen',
        5: 'white-king',
        6: 'black-pawn',
        7: 'black-rook',
        8: 'black-knight',
        9: 'black-bishop',
        10: 'black-queen',
        11: 'black-king'
    }
    print("INFO:     Models loaded successfully in detectors.py")
except Exception as e:
    print(f"FATAL ERROR: Could not load models. Check paths in detectors.py.")
    print(f"Error details: {e}")
    import sys
    sys.exit(1)

def get_board_corners(image):
    """
    Runs the pose model on an image.
    Image is ASSUMED to be 1024x1024.
    """
    # --- NO imgsz=1024 ---
    results = POSE_MODEL.predict(image, verbose=False)
    
    keypoints_data = results[0].keypoints.xy[0].cpu().numpy()
    
    if len(keypoints_data) < 4:
        print("ERROR: Not enough keypoints found to form a board.")
        return None
    elif len(keypoints_data) > 4:
        keypoints_data = keypoints_data[:4]
        
    return keypoints_data

def get_piece_predictions(image):
    """
    Runs the piece detection model on an image.
    Image is ASSUMED to be 1024x1024.
    """
    # --- NO imgsz=1024 ---
    # We KEEP conf=0.1, which was a correct fix.
    results = PIECE_MODEL.predict(image, verbose=False, conf=0.1)
    
    return results[0].boxes