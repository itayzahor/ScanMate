import math
import numpy as np
from scripts.detectors import IMAGE_SIZE

def _apply_H_point(H, x, y):
    p = np.array([x, y, 1.0], dtype=np.float32)
    q = H @ p
    w = q[2] if q[2] != 0 else 1e-9
    return float(q[0] / w), float(q[1] / w)

def map_pieces_to_board(piece_boxes, PIECE_CLASS_NAMES, homography):
    """
    Inputs:
      - piece_boxes: Ultralytics Boxes (already filtered/NMSed) from 640x640 image
                     (must have .xyxy, .conf, .cls) OR a list of dicts with keys xyxy/conf/cls
      - PIECE_CLASS_NAMES: {cls_id: 'white-queen', ...}
      - matrix: 3x3 homography original -> rectified 640x640 board

    Returns:
      - board_matrix: 8x8 list (top->bottom of rectified board)
          Each cell contains:
            * label string from PIECE_CLASS_NAMES (e.g. 'white-queen')
            * or None if empty
    """
    S = IMAGE_SIZE / 8  # square size on rectified board
    board_matrix = [[None for _ in range(8)] for _ in range(8)]
    conf_grid = [[-1.0 for _ in range(8)] for _ in range(8)]

    # Normalize to iterable of (xyxy, conf, cls)
    if hasattr(piece_boxes, "xyxy"):
        xyxy = piece_boxes.xyxy.cpu().numpy()
        conf = piece_boxes.conf.cpu().numpy() if hasattr(piece_boxes, "conf") else np.ones((len(xyxy),))
        cls  = piece_boxes.cls.cpu().numpy().astype(int)
        items = [(xyxy[i], float(conf[i]), int(cls[i])) for i in range(len(xyxy))]
    else:
        items = []
        for d in piece_boxes:
            x1, y1, x2, y2 = d["xyxy"]
            items.append((np.array([x1, y1, x2, y2], dtype=float),
                          float(d.get("conf", 1.0)),
                          int(d["cls"])))

    H = np.asarray(homography, dtype=np.float32)

    for box, score, cls_id in items:
        x1, y1, x2, y2 = box
        cx = 0.5 * (x1 + x2)
        cy = y2 - (y2 - y1) / 4 

        ux, uy = _apply_H_point(H, cx, cy)  # project to rectified board

        if not (0.0 <= ux < 640.0 and 0.0 <= uy < 640.0):
            continue  # out of board

        c = int(math.floor(ux / S))
        r = int(math.floor(uy / S))
        c = min(max(c, 0), 7)
        r = min(max(r, 0), 7)

        label = PIECE_CLASS_NAMES.get(int(cls_id), None)

        if label and score > conf_grid[r][c]:
            conf_grid[r][c] = score
            board_matrix[r][c] = label

    return board_matrix
