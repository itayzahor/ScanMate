# Location: ML/scripts/board_mapper.py

import cv2
import numpy as np

# In ML/scripts/board_mapper.py

def convex_hull_order4(pts_xy):
    """
    Robustly order 4 points:
      - convex hull -> angle sort (CCW)
      - rotate to TL, then arrange to TL, TR, BR, BL
    Returns (4,2) float32 or None if we can't form a valid quad.
    """
    P = np.asarray(pts_xy, dtype=np.float32)
    P = np.unique(P, axis=0).astype(np.float32, copy=False)
    P = np.ascontiguousarray(P)

    if P.shape[0] < 4:
        print("ERROR: convex_hull_order4: Not enough unique points.")
        return None

    hull = cv2.convexHull(P).reshape(-1, 2).astype(np.float32)
    if hull.shape[0] != 4:
        if P.shape[0] == 4: hull = P
        else:
            print("ERROR: convex_hull_order4: Hull does not have 4 points.")
            return None

    # centroid + angle sort (CCW)
    c = hull.mean(axis=0)
    ang = np.arctan2(hull[:, 1] - c[1], hull[:, 0] - c[0])
    poly = hull[np.argsort(ang)]

    # rotate so first point is TL (min x+y sum)
    tl_idx = np.argmin(poly.sum(axis=1))
    poly = np.roll(poly, -tl_idx, axis=0) # Now starts with TL, list is [TL, BL, BR, TR]

    # --- THIS IS THE *ACTUAL* FINAL FIX ---
    # Construct the final array in [TL, TR, BR, BL] order.
    # We take elements from the CCW 'poly' array: poly[0]=TL, poly[1]=BL, poly[2]=BR, poly[3]=TR
    # So the correct order is poly[0], poly[3], poly[2], poly[1]
    src_pts = np.array([poly[0], poly[3], poly[2], poly[1]], dtype=np.float32)
    # --- END ACTUAL FINAL FIX ---

    return src_pts

# (The rest of board_mapper.py remains unchanged)

def get_perspective_transform(corners, output_size=800):
    """
    Takes 4 corner points (in any order) and returns a
    transformation matrix and the output size using the robust angle sort.
    """
    
    # --- 1. The Robust Angle-Sort Method ---
    print("INFO:     Using robust angle sort (convex_hull_order4)...")
    src_pts = convex_hull_order4(corners)
    
    if src_pts is None:
        raise ValueError("Could not order the 4 corner points. Check model output.")

    # --- 2. Define the destination (a perfect square) ---
    dst_pts = np.array([
        [0, 0],
        [output_size - 1, 0],
        [output_size - 1, output_size - 1],
        [0, output_size - 1]
    ], dtype="float32")

    # --- 3. Get the transformation matrix ---
    try:
        matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        
        print("INFO:     Successfully created perspective matrix (Angle Sort).")
    except Exception as e:
        print(f"ERROR: cv2.getPerspectiveTransform CRASHED: {e}")
        raise
        
    return matrix, output_size

# In ML/scripts/board_mapper.py

# ... (keep the get_perspective_transform function as is) ...

def map_pieces_to_board(piece_results_boxes, class_names, matrix, output_size):
    """
    Takes the raw piece prediction 'boxes' and the transform matrix,
    and returns a final 8x8 board state.
    Includes detailed debugging prints.
    """
    
    board_state = [["empty" for _ in range(8)] for _ in range(8)]
    square_size = output_size / 8
    
    print(f"\n--- DEBUG: map_pieces_to_board (square_size={square_size}) ---")
    
    for i, piece in enumerate(piece_results_boxes):
        try:
            # box = [x1, y1, x2, y2]
            box = piece.xyxy[0].cpu().numpy()
            class_id = int(piece.cls[0].cpu())
            
            if class_id not in class_names:
                print(f"Piece {i}: Invalid class_id {class_id}. Skipping.")
                continue 
            
            label = class_names[class_id]
            
            # --- Point calculation ---
            center_x = (box[0] + box[2]) / 2
            height = box[3] - box[1]
            map_y = box[1] + (height * 0.75) # 75% down from top
            

            # --- Transform Point ---
            pt = np.array([[[center_x, map_y]]], dtype="float32")
            transformed_pt = cv2.transform(pt, matrix)
            
            if transformed_pt is None:
                print(f"  ERROR: cv2.transform failed! Skipping.")
                continue

            new_x = transformed_pt[0][0][0]
            new_y = transformed_pt[0][0][1]
            
            # --- Print Transformed Point ---
            print(f"  Transformed Pt (NewX, NewY): ({new_x:.1f}, {new_y:.1f})")

            # --- Calculate Row/Col ---
            col = int(new_x // square_size)
            row = int(new_y // square_size)
            
            # --- Assign to Board ---
            if 0 <= row < 8 and 0 <= col < 8:
                if board_state[row][col] != "empty":
                     print(f"  WARNING: Overwriting square [{row}][{col}] (was {board_state[row][col]})")
                board_state[row][col] = label
                print(f"  SUCCESS: Assigned to board_state[{row}][{col}]")
            else:
                 print(f"  FAILED: Mapped OUTSIDE grid. Skipping.")
            
        except Exception as e:
            print(f"ERROR processing piece {i}: {e}")
            continue 
            
    print("\n--- DEBUG: Final board_state before returning ---")
    import pprint
    pprint.pprint(board_state)

    return board_state