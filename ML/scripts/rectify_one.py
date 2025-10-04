#!/usr/bin/env python
# Robust rectification for one image:
# - Reorders 4 keypoints by geometry (TL, TR, BR, BL)
# - Saves rectified image, overlay debug, and homography matrix
# Usage:
#   python scripts/rectify_one.py runs\pose_tiny\weights\best.pt data\yolo_kp\images\val\G072_IMG000.jpg

import sys
from pathlib import Path
import numpy as np
import cv2
from ultralytics import YOLO

OUT_DIR = Path("outputs/rectified")  # under ML/
OUT_DIR.mkdir(parents=True, exist_ok=True)

def order_corners_xy4(kps_xy):
    """
    kps_xy: array-like shape (4,2) in image coordinates.
    Return np.float32 in order: TL, TR, BR, BL.
    """
    pts = np.array(kps_xy, dtype=np.float32)

    # sort by y to split top vs bottom
    idx = np.argsort(pts[:, 1])
    top2 = pts[idx[:2]]
    bot2 = pts[idx[2:]]

    # sort each row by x for left/right
    top2 = top2[np.argsort(top2[:, 0])]   # [TL, TR]
    bot2 = bot2[np.argsort(bot2[:, 0])]   # [BL, BR] (left then right)

    TL, TR = top2[0], top2[1]
    BL, BR = bot2[0], bot2[1]
    # return in TL, TR, BR, BL order (common homography ordering)
    return np.array([TL, TR, BR, BL], dtype=np.float32)

def draw_overlay(img, corners_xy, path):
    """Draw circles and labels on a copy of the image for debugging."""
    vis = img.copy()
    labels = ["TL","TR","BR","BL"]
    for (x, y), lab in zip(corners_xy, labels):
        cv2.circle(vis, (int(x), int(y)), 10, (0, 0, 255), -1)
        cv2.putText(vis, lab, (int(x)+8, int(y)-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2, cv2.LINE_AA)
    cv2.imwrite(str(path), vis)

def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts\\rectify_one.py <pose_model.pt> <image_path>")
        sys.exit(2)

    model_path = Path(sys.argv[1])
    img_path = Path(sys.argv[2])
    if not model_path.exists():
        print(f"Model not found: {model_path}")
        sys.exit(2)
    if not img_path.exists():
        print(f"Image not found: {img_path}")
        sys.exit(2)

    model = YOLO(str(model_path))
    results = model(str(img_path), imgsz=640, device="cpu")
    r = results[0]

    if r.keypoints is None or len(r.keypoints.xy) == 0:
        print("No board detected.")
        sys.exit(1)

    # Take the best prediction (first)
    kps = r.keypoints.xy[0].cpu().numpy()  # shape (N_kpts, 2). We expect 4.
    if kps.shape[0] < 4:
        print("Detected fewer than 4 keypoints.")
        sys.exit(1)

    # Reorder corners robustly: TL, TR, BR, BL
    corners = order_corners_xy4(kps[:4])

    # Debug overlay on original image
    img = cv2.imread(str(img_path))
    overlay_path = OUT_DIR / f"{img_path.stem}_overlay.jpg"
    draw_overlay(img, corners, overlay_path)

    # Homography to a square canvas (e.g., 800x800)
    dst_size = 800
    dst = np.float32([
        [0, 0],                     # TL
        [dst_size - 1, 0],          # TR
        [dst_size - 1, dst_size - 1],# BR
        [0, dst_size - 1]           # BL
    ])

    H = cv2.getPerspectiveTransform(corners, dst)
    rectified = cv2.warpPerspective(img, H, (dst_size, dst_size))

    # Save outputs
    out_img = OUT_DIR / f"{img_path.stem}_rectified.jpg"
    out_H   = OUT_DIR / f"{img_path.stem}_H.npy"
    np.save(str(out_H), H)
    cv2.imwrite(str(out_img), rectified)

    print("Corners (TL,TR,BR,BL):")
    for p in corners:
        print(" ", [float(f"{p[0]:.2f}"), float(f"{p[1]:.2f}")])
    print("Saved overlay:", overlay_path)
    print("Saved rectified:", out_img)
    print("Saved H:", out_H)

if __name__ == "__main__":
    main()
