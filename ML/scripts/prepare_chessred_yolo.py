#!/usr/bin/env python
# Convert ChessReD/ChessReD2K to YOLOv8 datasets:
# - yolo_kp: board keypoints (4 corners) in YOLO pose format
# - yolo_det: piece detections (12 classes) in YOLO detect format
# Supports:
#   --subset splits:chessred2k.train | splits:chessred2k.val | splits:chessred2k.test | splits:train/val/test
#   --val_from auto|official|none  (how to form the validation split)
#   --limit_kp / --limit_det       (limit total examples; 0 means zero)
#
# Examples:
#   python scripts/prepare_chessred_yolo.py --subset splits:chessred2k.train --val_from official --limit_kp 999999 --limit_det 0
#   python scripts/prepare_chessred_yolo.py --subset splits:train --val_from auto --limit_kp 400 --limit_det 40
#   python scripts/prepare_chessred_yolo.py --subset splits:chessred2k.train --val_from none --limit_kp 999999 --limit_det 0

import json, shutil, re, random, argparse
from pathlib import Path
from typing import Optional
import numpy as np

print(">> prepare_chessred_yolo v2 (nested subset support)")

ROOT = Path(__file__).resolve().parents[1]  # ML/
DATA = ROOT / "data"
ANN  = DATA / "annotations.json"

IMG_FULL = DATA / "chessred" / "images"
IMG_2K   = DATA / "chessred2k" / "images"

OUT_KP  = DATA / "yolo_kp"
OUT_DET = DATA / "yolo_det"

# 12-class order (skip "empty")
ORDER = ["white-king","white-queen","white-rook","white-bishop","white-knight","white-pawn",
         "black-king","black-queen","black-rook","black-bishop","black-knight","black-pawn"]
CLSIDX = {name:i for i,name in enumerate(ORDER)}

def find_image(rel: str) -> Optional[Path]:
    """Resolve an image path in either chessred or chessred2k."""
    relp = Path(rel)
    # If rel already starts with 'images/...', join to dataset roots directly
    if len(relp.parts) > 0 and relp.parts[0].lower() == "images":
        p = (DATA / "chessred" / relp)
        if p.exists(): return p
        p2 = (DATA / "chessred2k" / relp)
        if p2.exists(): return p2
        return None
    # else treat as filename/subpath under images/
    p = (DATA / "chessred" / "images" / relp)
    if p.exists(): return p
    p2 = (DATA / "chessred2k" / "images" / relp)
    if p2.exists(): return p2
    return None

def game_id_from_path(path_str: str) -> int:
    m = re.search(r"/(\d+)/", path_str.replace("\\","/"))
    return int(m.group(1)) if m else -1

def ensure_clean(d: Path):
    if d.exists(): shutil.rmtree(d)
    for s in ("train","val"):
        (d/"images"/s).mkdir(parents=True, exist_ok=True)
        (d/"labels"/s).mkdir(parents=True, exist_ok=True)

def split_by_games(items, val_ratio=0.2, seed=42):
    """Group-aware split by game_id to avoid leakage."""
    random.seed(seed)
    games = sorted({it["game_id"] for it in items})
    random.shuffle(games)
    nval = max(1, int(len(games)*val_ratio)) if games else 0
    val_games = set(games[:nval])
    tr, va = [], []
    for it in items:
        (va if it["game_id"] in val_games else tr).append(it)
    return tr, va

# ---- nested walking for dotted subset names ----
def _walk(node, dotted: str):
    cur = node
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur

def get_ids_by_subset(d: dict, subset: Optional[str]):
    """
    Accepts either layout:
      --subset chessred2k:train|val|test
      --subset splits:chessred2k.train|val|test
      --subset splits:train|val|test
    Returns: set(image_ids) or None (if no subset).
    """
    if not subset:
        return None
    try:
        root, name = subset.split(":", 1)
    except ValueError:
        raise SystemExit(f"Bad --subset value '{subset}'. Use 'root:name'.")

    if root == "splits":
        node = _walk(d.get("splits", {}), name)
        if isinstance(node, dict):
            ids = node.get("image_ids", [])
            return set(ids) if isinstance(ids, list) else set()
        return set()

    if root == "chessred2k":
        node = _walk(d.get("chessred2k", {}), name)
        ids = node.get("image_ids", []) if isinstance(node, dict) else []
        if not ids:
            node2 = _walk(d.get("splits", {}).get("chessred2k", {}), name)
            ids = node2.get("image_ids", []) if isinstance(node2, dict) else []
        return set(ids) if isinstance(ids, list) else set()

    raise SystemExit(f"Unknown subset root '{root}'. Use 'splits' or 'chessred2k'.")

def get_ids(d: dict, dotted: str):
    """Fetch ids from a dotted path under a dict (e.g., 'chessred2k.val')."""
    node = _walk(d, dotted)
    if isinstance(node, dict):
        return set(node.get("image_ids", []))
    return set()

def limit_pair(tr, va, total: Optional[int]):
    """Limit total count across (train,val) while keeping current ratio."""
    if total is None:
        return tr, va
    if total <= 0:
        return [], []
    n_tr = len(tr); n_va = len(va); n_total = n_tr + n_va
    if n_total == 0:
        return [], []
    # proportional rounding
    new_tr = int(round(total * (n_tr / n_total)))
    new_va = total - new_tr
    return tr[:new_tr], va[:new_va]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit_kp",  type=int, default=40, help="max total KP images (train+val); 0 means 0")
    ap.add_argument("--limit_det", type=int, default=40, help="max total DET images (train+val); 0 means 0")
    ap.add_argument("--subset", type=str, default=None,
                    help="e.g. 'splits:chessred2k.train' or 'splits:train'")
    ap.add_argument("--val_from", type=str, default="auto",
                    choices=["auto", "official", "none"],
                    help="auto: resplit by games; official: use chessred2k.{train,val}; none: all to train")
    ap.add_argument("--dry_run", action="store_true")
    args = ap.parse_args()

    d = json.loads(ANN.read_text(encoding="utf-8"))
    images = {im["id"]: im for im in d["images"]}
    id2name = {c["id"]: c["name"] for c in d["categories"]}

    pieces = d.get("annotations", {}).get("pieces", [])
    corners = d.get("annotations", {}).get("corners", [])

    # subset base (usually train ids)
    subset_ids = get_ids_by_subset(d, args.subset)
    if args.subset:
        print(f"Subset active: {args.subset} with {len(subset_ids or [])} ids")
        if subset_ids is not None and len(subset_ids) == 0:
            print("WARNING: subset returned 0 ids.")

    # Decide train_ids / val_ids from val_from mode
    train_ids = set()
    val_ids   = set()
    if args.subset:
        train_ids = set(subset_ids or [])
        if args.val_from == "official":
            # if subset is chessred2k.train → val is chessred2k.val
            parts = args.subset.split(":", 1)
            if parts[0] == "splits" and parts[1].startswith("chessred2k"):
                val_ids = get_ids(d.get("splits", {}), "chessred2k.val")
            else:
                # fallback: empty val if not a known pair
                val_ids = set()
        elif args.val_from == "none":
            val_ids = set()
        else:
            # auto: we’ll re-split by games below using train_ids only
            pass
    else:
        # no subset → use full dataset, auto split
        train_ids = set(im["id"] for im in d["images"])

    # ---- Build ALL KP items ----
    kp_items_all = []
    for obj in corners:
        im = images.get(obj.get("image_id"))
        if not im:
            continue
        rel = im.get("path") or im.get("file_name")
        if not rel:
            continue
        ip = find_image(rel)
        if ip is None:
            continue
        cs = obj.get("corners") or {}
        if not all(k in cs for k in ("bottom_left","bottom_right","top_right","top_left")):
            continue
        kp_items_all.append(dict(
            img=ip, rel=rel, W=im["width"], H=im["height"],
            game_id=game_id_from_path(rel), img_id=im["id"], corners=cs
        ))

    # ---- Build ALL DET items (group boxes per image) ----
    tmp = {}
    for ann in pieces:
        im = images.get(ann.get("image_id"))
        if not im:
            continue
        rel = im.get("path") or im.get("file_name")
        if not rel:
            continue
        ip = find_image(rel)
        if ip is None:
            continue
        if "bbox" not in ann:
            continue
        entry = tmp.setdefault(im["id"], dict(
            img=ip, rel=rel, W=im["width"], H=im["height"],
            game_id=game_id_from_path(rel), img_id=im["id"], boxes=[]
        ))
        entry["boxes"].append(dict(cid=ann["category_id"], bbox=ann["bbox"]))
    det_items_all = list(tmp.values())

    # ---- Train/Val partitioning ----
    if args.val_from == "official":
        kp_tr = [it for it in kp_items_all if it["img_id"] in train_ids]
        kp_va = [it for it in kp_items_all if it["img_id"] in val_ids]
        det_tr = [it for it in det_items_all if it["img_id"] in train_ids]
        det_va = [it for it in det_items_all if it["img_id"] in val_ids]
    elif args.val_from == "none":
        kp_tr = [it for it in kp_items_all if (not subset_ids or it["img_id"] in train_ids)]
        kp_va = []
        det_tr = [it for it in det_items_all if (not subset_ids or it["img_id"] in train_ids)]
        det_va = []
    else:
        # auto: resplit by games within whatever we selected as 'train_ids'
        base_kp  = [it for it in kp_items_all  if (not subset_ids or it["img_id"] in train_ids)]
        base_det = [it for it in det_items_all if (not subset_ids or it["img_id"] in train_ids)]
        kp_tr, kp_va = split_by_games(base_kp)
        det_tr, det_va = split_by_games(base_det)

    # ---- Limits (total across train+val) ----
    kp_tr, kp_va   = limit_pair(kp_tr, kp_va, args.limit_kp)
    det_tr, det_va = limit_pair(det_tr, det_va, args.limit_det)

    print(f"Corners total available: {len(kp_items_all)} → using train={len(kp_tr)} val={len(kp_va)}")
    print(f"Detections total available imgs: {len(det_items_all)} → using train={len(det_tr)} val={len(det_va)}")

    if args.dry_run:
        print("Dry run only; no files written.")
        return

    # ---- write YOLO dirs ----
    ensure_clean(OUT_KP); ensure_clean(OUT_DET)

    # Keypoints labels: class 0 (board)
    # Line format: "0 cx cy w h  (BLx BLy 2 BRx BRy 2 TRx TRy 2 TLx TLy 2)"  (all normalized)
    def write_kp(split, items):
        pad = 0.08  # 8% padding around board bbox
        for it in items:
            dst_img = OUT_KP/"images"/split/it["img"].name
            shutil.copy2(it["img"], dst_img)
            lab = OUT_KP/"labels"/split/(it["img"].stem + ".txt")

            bl = it["corners"]["bottom_left"]; br = it["corners"]["bottom_right"]
            tr = it["corners"]["top_right"];   tl = it["corners"]["top_left"]
            pts = np.array([bl, br, tr, tl], dtype=np.float32)

            xmin, ymin = pts[:,0].min(), pts[:,1].min()
            xmax, ymax = pts[:,0].max(), pts[:,1].max()

            w = it["W"]; h = it["H"]
            pw, ph = pad*w, pad*h
            xmin = max(0.0, xmin - pw); ymin = max(0.0, ymin - ph)
            xmax = min(w,   xmax + pw); ymax = min(h,   ymax + ph)

            bw = xmax - xmin; bh = ymax - ymin
            cx = xmin + bw/2; cy = ymin + bh/2

            # normalize bbox
            cx /= w; cy /= h; bw /= w; bh /= h

            # normalized keypoints + visibility=2
            kps = []
            for (x,y) in (bl, br, tr, tl):
                kps += [x / w, y / h, 2]

            line = f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f} " + " ".join(f"{v:.6f}" for v in kps)
            lab.write_text(line+"\n", encoding="utf-8")

    # Detection labels: "<cls cx cy w h>" normalized (skip 'empty')
    def write_det(split, items):
        for it in items:
            dst_img = OUT_DET/"images"/split/it["img"].name
            shutil.copy2(it["img"], dst_img)
            lab = OUT_DET/"labels"/split/(it["img"].stem + ".txt")
            lines=[]
            for b in it["boxes"]:
                name = id2name.get(b["cid"])
                if name not in CLSIDX:
                    continue
                cls = CLSIDX[name]
                x, y, w, h = b["bbox"]
                cx = (x + w/2) / it["W"]
                cy = (y + h/2) / it["H"]
                bw = w / it["W"]; bh = h / it["H"]
                lines.append(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
            lab.write_text("\n".join(lines)+("\n" if lines else ""), encoding="utf-8")

    write_kp("train", kp_tr); write_kp("val", kp_va)
    write_det("train", det_tr); write_det("val", det_va)
    print("Wrote:", OUT_KP, "and", OUT_DET)

if __name__ == "__main__":
    main()
