"""
prepare_yolo_kp.py
Builds a YOLOv8-Pose dataset of chessboard corners from the official ChessReD-2K splits.

Process:
- Loads `data/annotations.json` and retrieves the official train/val/test image IDs.
- Keeps only 2K images that exist on disk and have all 4 board corners.
- Computes a bounding box from the corners (with small padding) and normalizes both box and keypoints.
- Writes YOLOv8-Pose labels and copies images into `data/yolo_kp/{train,val,test}`.

Input:
- annotations: data/annotations.json  
- images: data/chessred2k/images/...

Output:
- data/yolo_kp/
    ├── images/{train,val,test}/
    └── labels/{train,val,test}/

Label format:
`0 cx cy w h x1 y1 v1 x2 y2 v2 x3 y3 v3 x4 y4 v4`
(class_id=0, visibility=2 for all points)

Notes:
- Uses only ChessReD-2K (not the full dataset).
- Corner order: bottom-left → bottom-right → top-right → top-left.
- ensure_clean_out() wipes and recreates the output structure each run.

Example run:
    $ python scripts/prepare_yolo_kp.py
"""


import json
import shutil
from typing import List
import numpy as np

# shared helpers
from prepare_helper import (
    DATA, ANN, SPLIT_KEYS,
    _ids_from, find_image, ensure_clean_out
)

# Paths
OUT_KP   = DATA / "yolo_kp"

# Board-box padding around the 4 corners (as fraction of image size)
PAD = 0.08

def write_kp_split(split: str, items: List[dict], pad: float):
    """
    Write images and YOLOv8-pose labels for one split (train/val/test).

    Expects each `item` to contain:
      - item["img"]   : pathlib.Path to source image (must exist)
      - item["W"],["H"]: image width/height (for normalization)
      - item["corners"]: dict with keys bottom_left, bottom_right, top_right, top_left

    Notes:
      - Keypoint order is BL, BR, TR, TL (consistent across all labels).
      - Visibility is set to 2 (visible) for all 4 keypoints.
      - Bounding box is built from the 4 corners and expanded by `pad`×(W,H).
    """
    img_dir = OUT_KP / "images" / split
    lab_dir = OUT_KP / "labels" / split

    for it in items:
        # Get the source image
        src_img = it["img"]
        # define its destination inside the current split folder
        dst_img = img_dir / src_img.name
        # Copy the image file into the YOLO split (train/val/test)
        shutil.copy2(src_img, dst_img)

        # Extract the four chessboard corners in a fixed order (Bottom-Left → Bottom-Right → Top-Right → Top-Left)
        bl = it["corners"]["bottom_left"]
        br = it["corners"]["bottom_right"]
        tr = it["corners"]["top_right"]
        tl = it["corners"]["top_left"]
        # Convert corners to a NumPy array for easy coordinate operations
        pts = np.array([bl, br, tr, tl], dtype=np.float32)

        # Compute the bounding box around the four corners
        xmin, ymin = float(pts[:, 0].min()), float(pts[:, 1].min())
        xmax, ymax = float(pts[:, 0].max()), float(pts[:, 1].max())
        W, H = float(it["W"]), float(it["H"])

        # Expand the box slightly (padding) and clamp it inside the image borders
        xmin = max(0.0, xmin - pad * W)
        ymin = max(0.0, ymin - pad * H)
        xmax = min(W,   xmax + pad * W)
        ymax = min(H,   ymax + pad * H)

        # Calculate the box width, height, and center coordinates
        bw = xmax - xmin
        bh = ymax - ymin
        cx = xmin + bw / 2.0
        cy = ymin + bh / 2.0

        # Normalize all box coordinates by image width/height (YOLO format)
        cx /= W
        cy /= H
        bw /= W
        bh /= H

        # Normalize keypoints as (x/W, y/H, visibility)
        # Visibility=2 → visible and labeled (required by YOLOv8-pose)
        kps = []
        for (x, y) in (bl, br, tr, tl):
            kps += [x / W, y / H, 2]

        # Compose YOLOv8 label line:
        # class_id (0) + bbox center + bbox size + all keypoints
        line = f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f} " + " ".join(f"{v:.6f}" for v in kps)

        # Save the label as a .txt file with the same base name as the image
        (lab_dir / f"{src_img.stem}.txt").write_text(line + "\n", encoding="utf-8")



def main():
    print(">> prepare_yolo_kp (2K official train/val/test)")
    # Load annotations.json
    d = json.loads(ANN.read_text(encoding="utf-8"))
    # Load all images from the annotations.json
    images = {im["id"]: im for im in d["images"]}
    # Load all corner data from annotations.json
    corners = d.get("annotations", {}).get("corners", [])

     # official ChessReD-2K split IDs (train/val/test)
    ids_train = _ids_from(d, list(SPLIT_KEYS["train"]))
    ids_val   = _ids_from(d, list(SPLIT_KEYS["val"]))
    ids_test  = _ids_from(d, list(SPLIT_KEYS["test"]))
    ids_all_2k = ids_train | ids_val | ids_test
    
    # create usable data
    kp_all = []
    unresolved = []
    # go over all corner data
    for obj in corners:
        img_id = obj.get("image_id")
        # check if in 2K splits
        if img_id not in ids_all_2k:
            continue
        # check image exists
        im = images.get(img_id)
        if not im:
            continue
        # check image relative path
        rel = im.get("path") or im.get("file_name")
        if not rel:
            continue
        # check image can be found
        ip = find_image(rel)
        if ip is None:
            unresolved.append((img_id, rel))
            continue
        # check corners exist
        cs = obj.get("corners") or {}
        if not all(k in cs for k in ("bottom_left", "bottom_right", "top_right", "top_left")):
            continue
        # all good → add all the collected info
        kp_all.append(dict(
            img=ip, W=im["width"], H=im["height"],
            img_id=img_id, corners=cs
        ))

    # split into train/val/test
    kp_tr = [it for it in kp_all if it["img_id"] in ids_train]
    kp_va = [it for it in kp_all if it["img_id"] in ids_val]
    kp_te = [it for it in kp_all if it["img_id"] in ids_test]

    # Print the stats on the splits
    print(f"Official 2K split sizes (declared): train={len(ids_train)} val={len(ids_val)} test={len(ids_test)}")
    print(f"Usable with corners & resolved paths: total={len(kp_all)} → train={len(kp_tr)} val={len(kp_va)} test={len(kp_te)}")
    if unresolved:
        print(f"Unresolved image paths: {len(unresolved)} (skipped)")
 
    # write all splits to data/yolo_kp
    ensure_clean_out(OUT_KP, splits=("train","val","test"))
    write_kp_split('train', kp_tr, PAD)
    write_kp_split('val',   kp_va, PAD)
    write_kp_split('test',  kp_te, PAD)
    print("Wrote:", OUT_KP)


if __name__ == "__main__":
    main()
