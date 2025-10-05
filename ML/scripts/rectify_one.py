#!/usr/bin/env python
"""
Robust rectification for one image:
- Orders 4 keypoints using convex-hull + angle sort (TL, TR, BR, BL)
- Saves raw-kps overlay (if --debug), ordered overlay, rectified image, and H
- Has geometry checks; use --force to output even if they fail

Usage:
  python scripts/rectify_one.py <pose_model.pt> <image_path> [--imgsz 1024] [--conf 0.25] [--debug] [--force]
"""

import sys
import argparse
from pathlib import Path
import numpy as np
import cv2
from ultralytics import YOLO

OUT_DIR = Path("outputs/rectified")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------- helpers ----------

def draw_points(vis, pts_xy, color=(0, 0, 255), labels=None, r=8, thick=2):
    pts = np.asarray(pts_xy, dtype=np.float32)
    for i, (x, y) in enumerate(pts):
        cv2.circle(vis, (int(x), int(y)), r, color, -1)
        if labels:
            cv2.putText(vis, f"{labels[i]}", (int(x)+8, int(y)-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, thick, cv2.LINE_AA)

def save_overlay(img, pts_xy, out_path, labels=None, color=(0,0,255)):
    vis = img.copy()
    draw_points(vis, pts_xy, color=color, labels=labels)
    cv2.imwrite(str(out_path), vis)

def convex_hull_order4(pts_xy):
    """
    Robustly order 4 points:
      - Drop NaN/inf points
      - convex hull -> angle sort (CCW)
      - rotate to TL,TR,BR,BL
    Returns (4,2) float32 or None if we can't form a valid quad.
    """
    P = np.asarray(pts_xy, dtype=np.float32)

    # drop any rows with NaN/inf
    finite_mask = np.isfinite(P).all(axis=1)
    P = P[finite_mask]
    # unique + contiguous float32 (OpenCV likes this)
    P = np.unique(P, axis=0).astype(np.float32, copy=False)
    P = np.ascontiguousarray(P)

    if P.shape[0] < 4:
        return None

    # OpenCV convex hull expects shape (N,1,2) or (N,2)
    hull = cv2.convexHull(P).reshape(-1, 2).astype(np.float32)
    if hull.shape[0] != 4:
        # If hull ≠ 4 (degenerate), try fallback: take the 4 points and continue
        if P.shape[0] == 4:
            hull = P
        else:
            return None

    # centroid + angle sort (CCW)
    c = hull.mean(axis=0)
    ang = np.arctan2(hull[:, 1] - c[1], hull[:, 0] - c[0])
    poly = hull[np.argsort(ang)]

    # rotate so first is TL (min y then min x)
    tl_idx = np.lexsort((poly[:, 0], poly[:, 1]))[0]
    poly = np.roll(poly, -tl_idx, axis=0)

    # ensure CCW (positive area); if negative, flip
    area2 = 0.0
    for i in range(4):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % 4]
        area2 += (x1 * y2 - x2 * y1)
    if area2 < 0:
        poly = np.array([poly[0], poly[3], poly[2], poly[1]], dtype=np.float32)

    TL, TR, BR, BL = poly[0], poly[1], poly[2], poly[3]
    return np.array([TL, TR, BR, BL], dtype=np.float32)

def quad_is_reasonable(q, min_area=100.0, aspect_low=0.25, aspect_high=4.0):
    """Sanity checks: convex, non-degenerate, aspect not insane."""
    q = np.asarray(q, dtype=np.float32)
    if q.shape != (4, 2):
        return False

    # area (shoelace)
    area = 0.5 * abs(
        q[0,0]*q[1,1] - q[1,0]*q[0,1] +
        q[1,0]*q[2,1] - q[2,0]*q[1,1] +
        q[2,0]*q[3,1] - q[3,0]*q[2,1] +
        q[3,0]*q[0,1] - q[0,0]*q[3,1]
    )
    if area < min_area:
        return False

    # approximate side lengths
    def dist(a, b): return float(np.linalg.norm(a - b))
    w1 = dist(q[0], q[1])  # TL->TR
    w2 = dist(q[3], q[2])  # BL->BR
    h1 = dist(q[0], q[3])  # TL->BL
    h2 = dist(q[1], q[2])  # TR->BR
    w = max(1e-6, (w1 + w2) * 0.5)
    h = max(1e-6, (h1 + h2) * 0.5)
    aspect = w / h
    return (aspect_low <= aspect <= aspect_high)

# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", help="Path to pose weights .pt")
    ap.add_argument("image", help="Path to image")
    ap.add_argument("--imgsz", type=int, default=1024)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--debug", action="store_true", help="Always save raw-kps overlay")
    ap.add_argument("--force", action="store_true", help="Save outputs even if geometry checks fail")
    ap.add_argument("--dst", type=int, default=800, help="Output square size")
    ap.add_argument("--margin", type=float, default=0.04, help="Relative margin inside canvas")
    args = ap.parse_args()

    model_path = Path(args.model)
    img_path = Path(args.image)
    if not model_path.exists():
        print(f"Model not found: {model_path}")
        sys.exit(2)
    if not img_path.exists():
        print(f"Image not found: {img_path}")
        sys.exit(2)

    img = cv2.imread(str(img_path))
    assert img is not None, f"Could not read image: {img_path}"

    model = YOLO(str(model_path))
    res = model.predict(img, imgsz=args.imgsz, conf=args.conf, verbose=False)[0]

    if res.keypoints is None or len(res.keypoints) == 0:
        print("No board detected.")
        sys.exit(1)

    # choose the highest box confidence detection
    i = int(np.argmax(res.boxes.conf.cpu().numpy()))
    kps_xy = res.keypoints.xy[i].cpu().numpy()  # (4,2)
    # (optional) check kps conf
    if res.keypoints.conf is not None:
        kps_conf = res.keypoints.conf[i].cpu().numpy()
    else:
        kps_conf = np.ones((kps_xy.shape[0],), dtype=np.float32)

    base = img_path.stem

    # save raw-kps overlay (for debugging what model predicted)
    if args.debug:
        save_overlay(img, kps_xy, OUT_DIR / f"{base}_rawkps.jpg",
                     labels=[f"{j}:{kps_conf[j]:.2f}" for j in range(len(kps_conf))],
                     color=(0, 165, 255))

        # --- robust ordering with fallback ---
    kps_xy = kps_xy[:4].astype(np.float32)  # ensure 4x2 float32

    # 1) try convex-hull based ordering (handles duplicates/collinear)
    ordered = convex_hull_order4(kps_xy)

    # 2) if that fails, optionally dump raw kps and try a simple fallback
    if ordered is None:
        if args.debug:
            save_overlay(
                img, kps_xy, OUT_DIR / f"{base}_rawkps.jpg",
                labels=[f"{j}:{kps_conf[j]:.2f}" for j in range(len(kps_conf))],
                color=(0, 165, 255)
            )

        # simple geometric fallback: order by y (top/bottom) then x (left/right)
        def simple_order_xy4(pts):
            p = np.array(pts, dtype=np.float32)
            idx = np.argsort(p[:, 1])      # by y
            top2, bot2 = p[idx[:2]], p[idx[2:]]
            top2 = top2[np.argsort(top2[:, 0])]  # x
            bot2 = bot2[np.argsort(bot2[:, 0])]
            TL, TR = top2[0], top2[1]
            BL, BR = bot2[0], bot2[1]
            return np.array([TL, TR, BR, BL], dtype=np.float32)

    # try fallback
        ordered = simple_order_xy4(kps_xy)

    # 3) final geometry sanity check (convex + area + aspect)
    ok_geom = quad_is_reasonable(
        ordered, min_area=500.0, aspect_low=0.2, aspect_high=5.0
    )

    if not ok_geom and not args.force:
        print("Corner geometry invalid (non-convex or bad aspect). Skipping.")
        sys.exit(1)


    # sanity checks
    ok_geom = quad_is_reasonable(ordered, min_area=500.0, aspect_low=0.2, aspect_high=5.0)
    if not ok_geom and not args.force:
        print("Corner geometry invalid (non-convex or bad aspect). Skipping.")
        sys.exit(1)

    # build destination with a small margin so the board sits inside the canvas
    S = int(args.dst)
    m = int(round(S * args.margin))
    dst = np.float32([
        [m, m],           # TL
        [S - 1 - m, m],   # TR
        [S - 1 - m, S - 1 - m],  # BR
        [m, S - 1 - m]    # BL
    ])

    H = cv2.getPerspectiveTransform(ordered, dst)
    rectified = cv2.warpPerspective(img, H, (S, S))

    # save outputs
    out_img = OUT_DIR / f"{base}_rectified.jpg"
    out_H   = OUT_DIR / f"{base}_H.npy"
    np.save(str(out_H), H)
    cv2.imwrite(str(out_img), rectified)

    print("Corners (TL,TR,BR,BL):")
    for p in ordered:
        print(" ", [float(f"{p[0]:.2f}"), float(f"{p[1]:.2f}")])
    print("Saved raw-kps:", OUT_DIR / f"{base}_rawkps.jpg" if args.debug else "(debug off)")
    print("Saved overlay:", OUT_DIR / f"{base}_overlay.jpg")
    print("Saved rectified:", out_img)
    print("Saved H:", out_H)

if __name__ == "__main__":
    main()
