#!/usr/bin/env python
"""
Run rectify_one.py on many images (val set by default).

Usage examples (from ML/):
  python scripts/rectify_batch.py --model runs/pose_2k_official/weights/best.pt
  python scripts/rectify_batch.py --model runs/pose_2k_official/weights/best.pt --root data/yolo_kp/images/val --pattern *.jpg --limit 120
"""
import argparse, subprocess, sys
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Path to pose weights .pt")
    ap.add_argument("--root",  default="data/yolo_kp/images/val", help="Folder to scan for images")
    ap.add_argument("--pattern", default="*.jpg", help="Glob pattern (e.g. *.jpg, G006_*.jpg)")
    ap.add_argument("--limit", type=int, default=0, help="Max images to process (0 = all)")
    ap.add_argument("--fail_log", default="outputs/rectified/_failures.txt", help="File to write failing image paths")
    args = ap.parse_args()

    root = Path(args.root)
    assert root.exists(), f"Input folder not found: {root}"

    images = sorted(root.rglob(args.pattern))
    if args.limit and args.limit > 0:
        images = images[:args.limit]

    if not images:
        print(f"No images found in {root} matching {args.pattern}")
        return 2

    print(f"Batch-rectifying {len(images)} images from {root} ...")
    ok, fail = 0, 0
    failed_paths = []

    # call the existing single-image tool so behavior stays identical
    rectify_one = str(Path("scripts/rectify_one.py"))

    for i, im in enumerate(images, 1):
        cmd = [sys.executable, rectify_one, args.model, str(im)]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        # print a one-line status (comment out if too chatty)
        print(f"[{i:4d}/{len(images)}] {im.name}: ", end="")
        if r.returncode == 0:
            print("OK")
            ok += 1
        else:
            print("FAIL")
            fail += 1
            failed_paths.append(str(im))
            # optional: uncomment to see error text
            # print(r.stdout)

    if failed_paths:
        Path(args.fail_log).parent.mkdir(parents=True, exist_ok=True)
        Path(args.fail_log).write_text("\n".join(failed_paths) + "\n", encoding="utf-8")

    print("\nDone.")
    print(f"  Success: {ok}")
    print(f"  Failed : {fail}")
    if fail:
        print(f"  See failed list: {args.fail_log}")

if __name__ == "__main__":
    sys.exit(main())
