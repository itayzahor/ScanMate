"""
prepare_yolo_det.py
Builds a YOLOv8-Detect dataset of chess pieces from the official ChessReD-2K splits.

Process:
- Loads `data/annotations.json` and retrieves the official 2K train/val/test image IDs.
- Keeps only 2K images that exist on disk and whose piece annotations include a bbox.
- Converts COCO bboxes (x,y,w,h in pixels) → YOLO format (cx,cy,bw,bh normalized).
- Writes YOLOv8-Detect labels and copies images into `data/yolo_det/{train,val,test}`.

Input:
- annotations: data/annotations.json
- images:      data/chessred2k/images/...

Output:
- data/yolo_det/
    ├── images/{train,val,test}/
    └── labels/{train,val,test}/

Label format:
`<class_id> <cx> <cy> <w> <h>`  (all values normalized to [0,1])
- `class_id` follows the dataset’s `categories` order (0..11), with “empty” skipped.
- (cx,cy) is the bbox center; (w,h) is bbox size.

Notes:
- Uses only ChessReD-2K (not the full dataset). Images without piece bboxes are skipped.
- Skips category "empty" (id=12).
- `ensure_clean_out()` wipes and recreates the output structure each run.
- Directory layout is consistent with YOLOv8 expectations for detection.

Example run:
    $ python scripts/prepare_yolo_det.py
"""

import json, shutil
from collections import Counter
from typing import Dict, Any, List, Tuple

# shared helper functions
from prepare_helper import (
    DATA, ANN, IMG_2K, SPLIT_KEYS,
    _ids_from, find_image, ensure_clean_out
)

# output path
OUT_DET = DATA / "yolo_det"

def _norm_xywh(x: float, y: float, w: float, h: float, W: float, H: float) -> Tuple[float, float, float, float]:
    """
    Convert COCO bbox (x,y,w,h) in pixels → YOLO bbox (cx,cy,bw,bh) normalized by image size.

    Args:
        x,y,w,h : bbox top-left corner and size (pixels)
        W,H     : full image width/height

    Returns:
        tuple of (cx, cy, bw, bh) all normalized to [0,1].
    """
    cx = (x + w / 2.0) / W
    cy = (y + h / 2.0) / H
    bw = w / W
    bh = h / H
    return cx, cy, bw, bh

def _write_split(split: str, items: List[Dict[str, Any]]) -> int:
    """
    Write images and YOLOv8-Detect labels for one split (train/val/test).

    Each item must include:
        - 'img': pathlib.Path to source image
        - 'labels': list of tuples (class_id, cx, cy, bw, bh)
    """
    img_dir = OUT_DET / "images" / split
    lab_dir = OUT_DET / "labels" / split

    written = 0
    for it in items:
        # copy image into split folder
        src_img = it["img"]
        dst_img = img_dir / src_img.name
        shutil.copy2(src_img, dst_img)

        # write one line per piece: <class_id> <cx> <cy> <w> <h>
        lines = []
        for (cid, cx, cy, bw, bh) in it["labels"]:
            lines.append(f"{cid} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

        # create label file (same base name as image)
        (lab_dir / f"{src_img.stem}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
        written += 1
    return written

def main():
    print(">> prepare_chessred_yolo_det (2K official train/val/test)")

    # load annotations.json
    d = json.loads(ANN.read_text(encoding="utf-8"))
    # map all images by their id
    images = {im["id"]: im for im in d["images"]}
    # load piece annotations and category list
    pieces = d.get("annotations", {}).get("pieces", [])
    categories = d.get("categories", [])
    id2name = {int(c["id"]): str(c["name"]).strip() for c in categories}

    # get official 2K splits (train/val/test)
    ids_train = _ids_from(d, list(SPLIT_KEYS["train"]))
    ids_val   = _ids_from(d, list(SPLIT_KEYS["val"]))
    ids_test  = _ids_from(d, list(SPLIT_KEYS["test"]))
    ids_all_2k = ids_train | ids_val | ids_test

    # collect all usable items (images that exist and have valid piece boxes)
    unresolved = []
    by_image: Dict[int, Dict[str, Any]] = {}

    for ann in pieces:
        img_id = ann.get("image_id")
        # skip images outside the 2K split
        if img_id not in ids_all_2k:
            continue
        im = images.get(img_id)
        if not im:
            continue

        # resolve image path
        rel = im.get("path") or im.get("file_name")
        if not rel:
            continue
        ip = find_image(rel)
        if ip is None:
            unresolved.append((img_id, rel))
            continue

        # skip missing or invalid category
        cid = ann.get("category_id")
        if not isinstance(cid, int) or cid not in id2name:
            continue
        # skip category 'empty'
        if id2name[cid].lower() == "empty":
            continue

        # extract bbox and normalize        
        bbox = ann.get("bbox")
        if not bbox or len(bbox) != 4:
            continue  

        x, y, w, h = map(float, bbox)
        W, H = float(im["width"]), float(im["height"])
        cx, cy, bw, bh = _norm_xywh(x, y, w, h, W, H)

        # add record for this image if not seen yet
        rec = by_image.get(img_id)
        if rec is None:
            rec = {"img": ip, "W": W, "H": H, "img_id": img_id, "labels": []}
            by_image[img_id] = rec

        # append this piece’s label (class_id + normalized bbox)
        rec["labels"].append((cid, cx, cy, bw, bh))

    # gather all usable images and split by official train/val/test
    items_all = [v for v in by_image.values() if v["labels"]]
    det_tr = [it for it in items_all if it["img_id"] in ids_train]
    det_va = [it for it in items_all if it["img_id"] in ids_val]
    det_te = [it for it in items_all if it["img_id"] in ids_test]

    # print dataset stats
    print(f"Official 2K split sizes (declared IDs): train={len(ids_train)} val={len(ids_val)} test={len(ids_test)}")
    print(f"Usable (piece boxes + resolved paths): total_imgs={len(items_all)} → train={len(det_tr)} val={len(det_va)} test={len(det_te)}")
    if unresolved:
        print(f"Unresolved image paths: {len(unresolved)} (skipped)")

    # Class histogram (sanity)
    cid_counter = Counter()
    for it in items_all:
        for (cid, *_rest) in it["labels"]:
            cid_counter[cid] += 1
    if cid_counter:
        print("[debug] Box count by class index:")
        for i, name in enumerate(id2name.keys()):
            print(f"{i:3d} {name:>13}: {cid_counter.get(i, 0)}")

    # write dataset to disk
    ensure_clean_out(OUT_DET, splits=("train", "val", "test"))
    n_tr = _write_split("train", det_tr)
    n_va = _write_split("val",   det_va)
    n_te = _write_split("test",  det_te)
    print(f"Wrote: {OUT_DET}  (train={n_tr}, val={n_va}, test={n_te})")

if __name__ == "__main__":
    main()
