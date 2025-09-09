# To run this script, use the command line:
# python ML\scripts\check_dataset.py

#!/usr/bin/env python
"""
ChessReD data quality test (single-file).

- Safe & fast: reads JSON, samples file existence, no heavy I/O
- PASS/FAIL output and non-zero exit on failures (use --strict to enforce)
- Autodetects lists that contain piece bboxes and corner annotations
- Supports explicit overrides and subset checks (incl. chessred2k)
- --explain shows which lists match pieces/corners

Usage (from repo root):
  python ML\scripts\check_dataset.py
  python ML\scripts\check_dataset.py --strict
  python ML\scripts\check_dataset.py --subset splits:train
  python ML\scripts\check_dataset.py --subset chessred2k:train
  python ML\scripts\check_dataset.py --pieces-key annotations.pieces --corners-key annotations.corners
  python ML\scripts\check_dataset.py --explain
"""
import json, sys, statistics, re, argparse
from pathlib import Path
from collections import Counter

# ---- Expectations (edit if your release differs) -----------------------------
EXPECT_TOTAL = 10800   # total images (set None to skip)
EXPECT_CATS  = 13      # 12 pieces + 1 extra label ("empty")
SAMPLE_CHECK = 2000    # how many images to sample for on-disk existence
MIN_WITH_BOXES   = 100 # minimal images with ≥1 bbox (just to catch "zero")
MIN_WITH_CORNERS = 100 # minimal images with corners
# ------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]  # ML/
DATA = ROOT / "data"
ANN  = DATA / "annotations.json"

def ok(msg):  print(f"[PASS] {msg}")
def bad(msg): print(f"[FAIL] {msg}")

# -------------------- helpers --------------------

def find_image(rel):
    """Resolve an image relative path under chessred or chessred2k."""
    rel = Path(rel)
    for base in (DATA / "chessred", DATA / "chessred2k"):
        p = base / rel
        if p.exists():
            return p
    return None

def get_by_keypath(d, keypath: str):
    """Resolve dotted key paths like 'annotations.pieces'."""
    cur = d
    for part in keypath.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur

def list_from_key(d, keypath: str):
    v = get_by_keypath(d, keypath) if keypath else None
    return v if isinstance(v, list) else None

def autodetect_lists(d):
    """Return (pieces_key, corners_key), checking both root and 'annotations.*'."""
    search_space = []
    # root lists
    for k, v in d.items():
        if isinstance(v, list):
            search_space.append((k, v))
    # nested lists under 'annotations'
    if isinstance(d.get("annotations"), dict):
        for k, v in d["annotations"].items():
            if isinstance(v, list):
                search_space.append((f"annotations.{k}", v))

    pieces_key = corners_key = None
    for k, v in search_space:
        if not v or not isinstance(v[0], dict):
            continue
        sample = v[:500]
        if any("bbox" in x for x in sample) and any("image_id" in x for x in sample):
            pieces_key = pieces_key or k
        if any(isinstance(x.get("corners"), dict) for x in sample):
            corners_key = corners_key or k
    return pieces_key, corners_key

def explain_lists(d):
    """Print a quick summary of lists for discovery."""
    print("Root keys:", list(d.keys()))
    # root
    for k, v in d.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            sample = v[:200]
            has_img   = sum("image_id" in x for x in sample)
            has_bbox  = sum("bbox"     in x for x in sample)
            has_corn  = sum(isinstance(x.get("corners"), dict) for x in sample)
            print(f"- {k}: len={len(v)} | image_id={has_img} | bbox={has_bbox} | corners={has_corn}")
            print(f"  sample keys: {list(v[0].keys())[:10]}")
    # nested under annotations
    if isinstance(d.get("annotations"), dict):
        for k, v in d["annotations"].items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                sample = v[:200]
                has_img   = sum("image_id" in x for x in sample)
                has_bbox  = sum("bbox"     in x for x in sample)
                has_corn  = sum(isinstance(x.get("corners"), dict) for x in sample)
                print(f"- annotations.{k}: len={len(v)} | image_id={has_img} | bbox={has_bbox} | corners={has_corn}")
                print(f"  sample keys: {list(v[0].keys())[:10]}")

def subset_filter(images, ids):
    ids = set(ids)
    return [im for im in images if im.get("id") in ids]

# -------------------- main --------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="fail on mismatches/shortfalls")
    ap.add_argument("--sample", type=int, default=SAMPLE_CHECK, help="sample size for file existence")
    ap.add_argument("--pieces-key", type=str, default=None, help="key for piece+bbox list (supports dotted paths)")
    ap.add_argument("--corners-key", type=str, default=None, help="key for corners list (supports dotted paths)")
    ap.add_argument("--subset", type=str, default=None,
                    help="limit to a split: 'splits:train|val|test' or 'chessred2k:train|val|test'")
    ap.add_argument("--explain", action="store_true", help="print which lists look like pieces/corners")
    args = ap.parse_args()

    if not ANN.exists():
        bad(f"Missing annotations.json at {ANN}")
        return 2

    d = json.loads(ANN.read_text(encoding="utf-8"))
    images     = d.get("images", [])
    categories = d.get("categories", [])
    splits     = d.get("splits", {})
    cr2k       = d.get("chessred2k", {})

    if args.explain:
        explain_lists(d)  # continues to run tests afterwards

    # Optional subset
    subset_ids = None
    if args.subset:
        try:
            root, name = args.subset.split(":", 1)
            if root == "splits":
                subset_ids = splits.get(name, {}).get("image_ids", [])
            elif root == "chessred2k":
                subset_ids = cr2k.get(name, {}).get("image_ids", [])
            else:
                bad(f"Unknown subset root '{root}'. Use 'splits' or 'chessred2k'.")
                return 2
            ok(f"Subset active: {args.subset} with {len(subset_ids)} image_ids")
        except Exception as e:
            bad(f"Bad --subset value '{args.subset}': {e}")
            return 2

    # Filter images if subset active
    if subset_ids is not None:
        images = subset_filter(images, subset_ids)

    # 1) Counts
    exit_code = 0
    total = len(images)
    if subset_ids is None and EXPECT_TOTAL is not None:
        if total != EXPECT_TOTAL and args.strict:
            bad(f"Total images entries = {total}, expected {EXPECT_TOTAL}")
            exit_code = 1
        else:
            ok(f"Total images entries = {total} (expected ~{EXPECT_TOTAL})")
    else:
        ok(f"Total images entries (after subset filter) = {total}")

    # 2) Categories (print all)
    id2name = {c["id"]: c["name"] for c in categories}
    if len(categories) != EXPECT_CATS and args.strict:
        bad(f"Categories = {len(categories)}, expected {EXPECT_CATS}")
        exit_code = 1
    else:
        ok(f"Categories = {len(categories)} (expected ~{EXPECT_CATS})")
    print("Categories:")
    for cid in sorted(id2name):
        print(f"  {cid:>2} -> {id2name[cid]}")

    # 3) File existence (sampled)
    sample = images[: max(1, min(args.sample, len(images)))]
    found, missing = 0, 0
    widths, heights = [], []
    for im in sample:
        rel = im.get("path") or im.get("file_name")
        if not rel:
            missing += 1
            continue
        if find_image(rel):
            found += 1
            if "width" in im and "height" in im:
                widths.append(im["width"]); heights.append(im["height"])
        else:
            missing += 1
    if missing == 0:
        ok(f"Sampled {len(sample)} images: all found on disk")
    else:
        bad(f"Sampled {len(sample)} images: missing {missing} files")
        exit_code = 1
    if widths and heights:
        print(f"Image size (sampled): width median={int(statistics.median(widths))} "
              f"range=[{min(widths)},{max(widths)}]; height median={int(statistics.median(heights))} "
              f"range=[{min(heights)},{max(heights)}]")

    # 4) Splits sum (only meaningful without subset)
    if subset_ids is None and splits:
        total_from_splits = sum(len(splits[k].get("image_ids", [])) for k in ("train","val","test") if k in splits)
        if EXPECT_TOTAL is not None and total_from_splits != EXPECT_TOTAL and args.strict:
            bad(f"train+val+test = {total_from_splits}, expected {EXPECT_TOTAL}")
            exit_code = 1
        else:
            ok(f"train+val+test = {total_from_splits} (expected ~{EXPECT_TOTAL})")
        for k in ("train","val","test"):
            if k in splits:
                print(f"  {k:>5}: {len(splits[k]['image_ids'])} images")

    # 5) Determine lists with bboxes/corners (autodetect + allow overrides)
    def detect_keys():
        pk, ck = autodetect_lists(d)
        return args.pieces_key or pk, args.corners_key or ck

    pieces_key, corners_key = detect_keys()
    pieces_list  = list_from_key(d, pieces_key)  if pieces_key  else None
    corners_list = list_from_key(d, corners_key) if corners_key else None

    if not pieces_list:
        bad("Could not find a valid pieces list with bboxes. Try --explain and pass --pieces-key <name>.")
        if args.strict: exit_code = 1
    else:
        ok(f"Using pieces list: '{pieces_key}'")
        anns = pieces_list
        if subset_ids is not None:
            idset = set(subset_ids)
            anns = [a for a in anns if a.get("image_id") in idset]
        img_with_boxes = set(a["image_id"] for a in anns if "image_id" in a and "bbox" in a)
        print(f"  images with ≥1 bbox: {len(img_with_boxes)}")
        if len(img_with_boxes) < MIN_WITH_BOXES and args.strict:
            bad(f"Too few images with boxes (<{MIN_WITH_BOXES})")
            exit_code = 1
        cls_counts = Counter(id2name.get(a.get("category_id"), "UNK") for a in anns if "category_id" in a)
        print("  top classes:", cls_counts.most_common(12))

    if not corners_list:
        bad("Could not find a valid corners list. Try --explain and pass --corners-key <name>.")
        if args.strict: exit_code = 1
    else:
        ok(f"Using corners list: '{corners_key}'")
        anns = corners_list
        if subset_ids is not None:
            idset = set(subset_ids)
            anns = [a for a in anns if a.get("image_id") in idset]
        img_with_corners = set(a["image_id"] for a in anns if "image_id" in a and isinstance(a.get("corners"), dict))
        print(f"  images with corners: {len(img_with_corners)}")
        if len(img_with_corners) < MIN_WITH_CORNERS and args.strict:
            bad(f"Too few images with corners (<{MIN_WITH_CORNERS})")
            exit_code = 1

    # 6) ChessReD2K nested counts (informational)
    if isinstance(d.get("chessred2k"), dict):
        print("ChessReD2K splits:")
        for name, obj in d["chessred2k"].items():
            print(f"  {name:>8}: {len(obj.get('image_ids', []))} images")

    print("\nDone.")
    return exit_code

if __name__ == "__main__":
    sys.exit(main())


