# Location: ML/scripts/detectors.py

from ultralytics import YOLO

CORNERS_MODEL_PATH = "runs/corners_11x_640_v2/weights/best.pt"
PIECE_MODEL_PATH = "runs/pieces_11x_640_v1/weights/best.pt"
IMAGE_SIZE = 640  # both models use 640x640 input


try:
    CORNERS_MODEL = YOLO(CORNERS_MODEL_PATH)
    PIECE_MODEL = YOLO(PIECE_MODEL_PATH)
    # Use your specific category mapping, overriding the model's default because our data yaml was wrong.
    PIECE_CLASS_NAMES = {
        0: 'black-bishop',
        1: 'black-king',
        2: 'black-knight',
        3: 'black-pawn',
        4: 'black-queen',
        5: 'black-rook',
        6: 'white-bishop',
        7: 'white-king',
        8: 'white-knight',
        9: 'white-pawn',
        10: 'white-queen',
        11: 'white-rook'
    }
    print("INFO:     Models loaded successfully in detectors.py")
except Exception as e:
    print(f"FATAL ERROR: Could not load models. Check paths in detectors.py.")
    print(f"Error details: {e}")
    import sys
    sys.exit(1)

def get_board_corners(image):
    """
    Run corner model once with very low confidence,
    and return top 4 bbox centers as (x,y).
    """
    results = CORNERS_MODEL.predict(image, imgsz=640, conf=0.01, iou=0.001)[0]
    boxes = results.boxes

    if boxes is None or len(boxes) < 4:
        print("ERROR: Not enough corners detected (need 4).")
        return None

    xywh = boxes.xywh.cpu().numpy()
    conf = boxes.conf.cpu().numpy()

    # take top 4 by confidence
    idx = conf.argsort()[-4:]
    centers = xywh[idx, :2].astype("float32")  # (x, y) are bbox centers
    return centers


def get_piece_predictions(image):
    """
    Runs the piece detection model on an image.
    Image is ASSUMED to be 1024x1024.
    """
    results = PIECE_MODEL.predict(image, verbose=False, iou=0.5, conf=0.3)
    
    return results[0].boxes