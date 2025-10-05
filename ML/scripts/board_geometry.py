#!/usr/bin/env python
"""
Find board corners with the pose model, compute H, and build the 8x8 grid
**in original image coordinates** (no cropping). Saves JSON + overlay.

Usage:
  python scripts/board_geometry.py \
    --model runs/pose_2k8/weights/best.pt \
    --image data/yolo_kp/images/val/G006_IMG001.jpg \
    --out outputs/geometry --save_raw
"""
import argparse, json
from pathlib import Path
import cv2
import numpy as np
from ultralytics import YOLO


# ------------------------- utils -------------------------

def save_overlay_points(img, pts, path, color=(0,165,255), labels=None):
    vis = img.copy()
    pts = np.asarray(pts, np.float32).reshape(-1, 2)
    for i, (x, y) in enumerate(pts):
        cv2.circle(vis, (int(x), int(y)), 8, color, -1)
        if labels:
            cv2.putText(vis, str(labels[i]), (int(x)+8, int(y)-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    cv2.imwrite(str(path), vis)

def is_convex_quad(q):
    """q: (4,2). Return True if convex with consistent winding."""
    q = np.asarray(q, np.float32).reshape(4, 2)
    s = 0.0
    ok = True
    for i in range(4):
        a, b, c = q[i], q[(i+1)%4], q[(i+2)%4]
        cross = np.cross(b - a, c - b)
        if i == 0:
            s = np.sign(cross) if cross != 0 else 0
        else:
            ok &= (np.sign(cross) == s or cross == 0)
    return bool(ok)

def quad_is_reasonable(q, min_area=800.0, aspect_low=0.25, aspect_high=4.0):
    q = np.asarray(q, np.float32).reshape(4, 2)
    if not is_convex_quad(q):
        return False
    area = cv2.contourArea(q.astype(np.float32))
    if area < float(min_area):
        return False
    # approx aspect by extreme box
    x, y, w, h = cv2.boundingRect(q.astype(np.int32))
    asp = w / max(h, 1)
    return (aspect_low <= asp <= aspect_high)

def hull_order4(kps_xy):
    """
    Order 4 points as TL,TR,BR,BL using convex hull + angle sort.
    Returns (4,2) float32 or None if hull fails.
    """
    P = np.asarray(kps_xy, np.float32).reshape(-1, 2)

    # sanitize: remove NaN/Inf rows
    m = np.isfinite(P).all(axis=1)
    P = P[m]
    # de-duplicate (some models can output very close duplicates)
    if len(P) >= 2:
        _, idx = np.unique(np.round(P, 3), axis=0, return_index=True)
        P = P[np.sort(idx)]

    if P.shape[0] != 4:
        return None

    try:
        hull = cv2.convexHull(P).reshape(-1, 2).astype(np.float32)
    except cv2.error:
        return None

    if hull.shape[0] != 4:
        return None

    cx, cy = hull.mean(axis=0)
    ang = np.arctan2(hull[:, 1] - cy, hull[:, 0] - cx)
    hull = hull[np.argsort(ang)]  # CCW
    idx_tl = np.argmin(np.sum(hull, axis=1))  # TL = min(x+y)
    return np.roll(hull, -idx_tl, axis=0)

def rowcol_fallback(kps_xy):
    """
    Fallback ordering if hull fails: split top/bottom by y,
    left/right by x -> TL,TR,BR,BL.
    """
    P = np.asarray(kps_xy, np.float32).reshape(-1, 2)
    if P.shape[0] != 4: 
        return None
    idx = np.argsort(P[:,1])
    top2, bot2 = P[idx[:2]], P[idx[2:]]
    top2 = top2[np.argsort(top2[:,0])]
    bot2 = bot2[np.argsort(bot2[:,0])]
    TL, TR = top2[0], top2[1]
    BL, BR = bot2[0], bot2[1]
    return np.stack([TL, TR, BR, BL], axis=0).astype(np.float32)

def expand_poly(poly, scale=1.02):
    P = np.asarray(poly, np.float32)
    c = P.mean(axis=0, keepdims=True)
    return (c + (P - c) * float(scale)).astype(np.float32)

def build_grid_polys(Hinv, S=800, expand=1.02):
    xs = np.linspace(0, S, 9, dtype=np.float32)
    ys = np.linspace(0, S, 9, dtype=np.float32)
    squares = []
    for r in range(8):
        for c in range(8):
            p = np.array([[xs[c],ys[r]],[xs[c+1],ys[r]],[xs[c+1],ys[r+1]],[xs[c],ys[r+1]]], np.float32)
            if expand != 1.0:
                p = expand_poly(p, expand)
            p = p.reshape(-1,1,2)
            q = cv2.perspectiveTransform(p, Hinv).reshape(-1,2)
            squares.append({"rc":[r,c], "poly": q.tolist()})
    return squares

def draw_overlay(img, squares, board_quad, path):
    vis = img.copy()
    for sq in squares:
        poly = np.array(sq["poly"], np.int32).reshape(-1,1,2)
        cv2.polylines(vis, [poly], True, (0,255,0), 1)
    quad = np.array(board_quad, np.int32).reshape(-1,1,2)
    cv2.polylines(vis, [quad], True, (0,0,255), 2)
    cv2.imwrite(str(path), vis)


# ------------------------- main -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="pose model .pt")
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", default="outputs/geometry")
    ap.add_argument("--imgsz", type=int, default=1024)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--min_kp_conf", type=float, default=0.35)
    ap.add_argument("--expand", type=float, default=1.02)
    ap.add_argument("--min_area", type=float, default=800.0)
    ap.add_argument("--aspect_low", type=float, default=0.25)
    ap.add_argument("--aspect_high", type=float, default=4.0)
    ap.add_argument("--save_raw", action="store_true",
                    help="save raw keypoint overlay for debugging")
    args = ap.parse_args()

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(args.model)
    img = cv2.imread(args.image)
    assert img is not None, f"Could not read image: {args.image}"

    res = model.predict(img, imgsz=args.imgsz, conf=args.conf, verbose=False)[0]
    if res.keypoints is None or len(res.keypoints) == 0:
        print("No board found (no keypoints).")
        return

    # top detection by box conf
    i = int(np.argmax(res.boxes.conf.cpu().numpy()))
    kps_xy = res.keypoints.xy[i].cpu().numpy()
    kps_conf = res.keypoints.conf[i].cpu().numpy() if res.keypoints.conf is not None else np.ones((kps_xy.shape[0],), np.float32)

    base = Path(args.image).stem
    if args.save_raw:
        save_overlay_points(
            img, kps_xy,
            out_dir / f"{base}_rawkps.jpg",
            color=(0,165,255),
            labels=[f"{j}:{kps_conf[j]:.2f}" for j in range(len(kps_conf))]
        )

    # require 4 kps and reasonable conf
    if kps_xy.shape[0] < 4:
        print("Not enough keypoints:", kps_xy.shape)
        return
    if (kps_conf < args.min_kp_conf).any():
        print("Some keypoints below confidence threshold:", kps_conf)

    # ordering with hull → fallback
    ordered = hull_order4(kps_xy)
    if ordered is None:
        ordered = rowcol_fallback(kps_xy)
    if ordered is None:
        print("Could not order the 4 points (hull+fallback failed).")
        # save raw to inspect and exit gracefully
        if args.save_raw:
            save_overlay_points(img, kps_xy, out_dir / f"{base}_rawkps.jpg",
                                color=(0,165,255),
                                labels=[f"{j}:{kps_conf[j]:.2f}" for j in range(len(kps_conf))])
        return
    # validate quad
    if not quad_is_reasonable(ordered, args.min_area, args.aspect_low, args.aspect_high):
        print("Quad failed geometry checks (convex/area/aspect).")
        # still draw an overlay to inspect:
        draw_overlay(img, [], ordered, out_dir / f"{base}_grid_overlay_BAD.jpg")
        return

    # H and grid
    S = 800.0
    dst = np.array([[0,0],[S,0],[S,S],[0,S]], np.float32)
    H = cv2.getPerspectiveTransform(ordered, dst)
    Hinv = np.linalg.inv(H)
    squares = build_grid_polys(Hinv, S=int(S), expand=float(args.expand))

    # save JSON + overlay
    data = {
        "image_path": str(Path(args.image).resolve()),
        "corners_tltrbrbl": ordered.tolist(),
        "H": H.tolist(),
        "squares": squares
    }
    (out_dir / f"{base}_geom.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    draw_overlay(img, squares, ordered, out_dir / f"{base}_grid_overlay.jpg")
    print(f"Saved:\n  {out_dir / (base + '_geom.json')}\n  {out_dir / (base + '_grid_overlay.jpg')}")


if __name__ == "__main__":
    main()
