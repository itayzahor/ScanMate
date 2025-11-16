import cv2, numpy as np
from scripts.detectors import IMAGE_SIZE


import numpy as np

def order_corners(points):
    """
    Input: 4 (x,y) points in any order.
    Output: np.float32 [TL, TR, BR, BL] in CCW order.
    """
    # 1. Compute centroid = the average point
    centroid = points.mean(axis=0)

    # 2. Sort CW by angle around centroid in a descending order
    angle = np.arctan2(points[:,1] - centroid[1], points[:,0] - centroid[0])
    poly = points[np.argsort(angle)]  # CW loop

    # after: poly = points[np.argsort(-angle)]  # CW loop (or np.argsort(angle) for CCW)
    tl_idx = np.argmin(poly[:,0] + poly[:,1])   # TL = min x+y
    poly   = np.roll(poly, -tl_idx, axis=0)     # start at TL
    
    return poly.astype(np.float32)



import cv2, numpy as np

def _a1_is_dark(rect, is_bgr=True):
    # 1) L channel (perceptual lightness)
    code = cv2.COLOR_BGR2LAB if is_bgr else cv2.COLOR_RGB2LAB
    L = cv2.cvtColor(rect, code)[:, :, 0]

    H, W = L.shape
    ys = np.linspace(0, H, 9).astype(int)
    xs = np.linspace(0, W, 9).astype(int)

    # 2) mean L per square (use a small inner crop to avoid borders)
    means = np.empty((8, 8), np.float32)
    for r in range(8):
        for c in range(8):
            y0, y1 = ys[r], ys[r+1]
            x0, x1 = xs[c], xs[c+1]
            pad_y = max(1, (y1 - y0) // 10)
            pad_x = max(1, (x1 - x0) // 10)
            roi = L[y0+pad_y:y1-pad_y, x0+pad_x:x1-pad_x]
            means[r, c] = float(roi.mean()) if roi.size else float(L[y0:y1, x0:x1].mean())

    # 3) test both legal parities; pick the one where "dark" squares are darker
    # parity mask with a1 at (row=7, col=0)
    mask_a1_dark = ((np.add.outer(np.arange(8), np.arange(8))) % 2 == 1)

    mu_dark  = means[mask_a1_dark].mean()
    mu_light = means[~mask_a1_dark].mean()

    return bool(mu_dark < mu_light)


def get_perspective_transform(corners, img_resized):
    """
    Orders corners internally, then chooses rotation so bottom-left (a1) is dark.
    Returns: (M, (out_size, out_size), rotation_degrees)
    """
    # 1) Order corners in Clock Wise order TL, TR, BR, BL
    src = order_corners(corners)

    # 2) Try 0/90/180/270 by rotating the DESTINATION square; pick one with a1 dark
    dst0 = np.array([
        [0, 0],                 # TL
        [IMAGE_SIZE-1, 0],      # TR
        [IMAGE_SIZE-1, IMAGE_SIZE-1], # BR
        [0, IMAGE_SIZE-1],      # BL
    ], dtype=np.float32)
    homography = cv2.getPerspectiveTransform(src, dst0)
    rect = cv2.warpPerspective(img_resized, homography, (IMAGE_SIZE, IMAGE_SIZE))
    if _a1_is_dark(rect):
            return homography
    # 3) a1 is light → rotate ±90° decided in *source* geometry:
    TL, TR, BR, BL = src
    
    # Determine rotation direction by comparing x-coords of TL and BL
    k = 1 if TL[0] < BL[0] else -1
    # print(f"DEBUG: get_perspective_transform: TL={TL[0]}, BL={BL[0]}, rotating {'CW' if k==1 else 'CCW'} to make a1 dark")
    dst90 = np.roll(dst0, k, axis=0)
    return cv2.getPerspectiveTransform(src, dst90)
        
    