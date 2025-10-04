#!/usr/bin/env python
# Visualize YOLOv8 pose labels (bbox + 4 keypoints) on images in data/yolo_kp.
# Saves overlays to outputs/viz_kp_labels/.
import random, os
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
IMG_ROOT = ROOT / "data/yolo_kp/images"
LBL_ROOT = ROOT / "data/yolo_kp/labels"
OUT = ROOT / "outputs/viz_kp_labels"
OUT.mkdir(parents=True, exist_ok=True)

def draw_one(split, name):
    img_p = IMG_ROOT / split / f"{name}.jpg"
    if not img_p.exists():
        for ext in (".png",".jpeg",".JPG",".PNG",".JPEG"):
            t = img_p.with_suffix(ext)
            if t.exists():
                img_p = t; break
    lbl_p = LBL_ROOT / split / f"{name}.txt"
    if not (img_p.exists() and lbl_p.exists()):
        return False

    img = cv2.imread(str(img_p))
    H, W = img.shape[:2]
    txt = lbl_p.read_text().strip().split()
    if len(txt) < 5 + 4*3:  # cls cx cy w h + 4*(x,y,v)
        return False

    cls = int(float(txt[0]))
    cx, cy, bw, bh = map(float, txt[1:5])
    kps = list(map(float, txt[5:5+12]))  # 4*3
    kps = np.array(kps, dtype=np.float32).reshape(4,3)
    # denormalize
    box = [cx*W, cy*H, bw*W, bh*H]
    # xywh -> xyxy
    x1 = int(box[0] - box[2]/2); y1 = int(box[1] - box[3]/2)
    x2 = int(box[0] + box[2]/2); y2 = int(box[1] + box[3]/2)
    cv2.rectangle(img, (x1,y1), (x2,y2), (0,255,0), 2)

    # keypoints (x,y,v), v=2 means visible
    colors = [(0,0,255),(255,0,0),(0,255,255),(255,0,255)]
    labels = ["bl","br","tr","tl"]  # the order we wrote in prepare script
    for i, (x,y,v) in enumerate(kps):
        px, py = int(x*W), int(y*H)
        cv2.circle(img, (px,py), 6, colors[i], -1)
        cv2.putText(img, labels[i], (px+6, py-6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, colors[i], 2)

    out_p = OUT / f"{split}_{name}.jpg"
    cv2.imwrite(str(out_p), img)
    return True

def main():
    for split in ("train","val"):
        img_dir = IMG_ROOT / split
        names = [p.stem for p in img_dir.glob("*.*")]
        random.shuffle(names)
        shown = 0
        for n in names[:24]:
            if draw_one(split, n):
                shown += 1
        print(f"{split}: wrote {shown} overlays to {OUT}")

if __name__ == "__main__":
    main()
