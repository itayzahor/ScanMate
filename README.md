# ScanMate

git clone https://github.com/itayzahor/ScanMate.git

cd ScanMate\ML

py -m venv .venv

.\.venv\Scripts\activate

pip install -r requirements.txt


grid recognition run example on the first 30 images under data/yolo_kp/val
from the ML folder run:

# first 30 .jpgs in the val set
$imgs = Get-ChildItem -Path data\yolo_kp\images\val -Filter *.jpg | Select-Object -First 30
foreach ($im in $imgs) {
  python scripts\board_geometry.py `
    --model runs\pose_2k8\weights\best.pt `
    --image $im.FullName `
    --out outputs\geometry `
    --save_raw
}
