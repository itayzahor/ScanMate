"""
prepare_helper.py
Minimal shared helpers for dataset preparation (paths, JSON, splits, FS).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
import shutil

# Paths 
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ANN  = DATA / "annotations.json"
IMG_2K = DATA / "chessred2k" / "images"

# Official 2K split key paths inside annotations.json
SPLIT_KEYS = {
    "train": ("splits", "chessred2k", "train"),
    "val":   ("splits", "chessred2k", "val"),
    "test":  ("splits", "chessred2k", "test"),
}

# JSON navigation helpers
def _walk(node: Dict[str, Any], path: List[str]):
    """
    Safely navigate a nested dictionary using a list of keys.

    Args:
        node (dict): The root dictionary to traverse.
        path (list[str]): List of keys representing the nested path to follow.

    Returns:
        Any or None: The value found at the nested path, or None if any key is missing.

    Example:
        data = {"splits": {"chessred2k": {"train": {"image_ids": [1, 2, 3]}}}}
        _walk(data, ["splits", "chessred2k", "train"])
        → {'image_ids': [1, 2, 3]}
    """
    cur = node
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _ids_from(d: Dict[str, Any], key_path: List[str]):
    """
    Retrieve a set of image IDs from a nested dictionary path.

    Uses `_walk()` to safely locate the node, then extracts the "image_ids" list
    (if present) and converts it to a set for fast membership checks.

    Args:
        d (dict): The dataset dictionary (usually parsed from annotations.json).
        key_path (list[str]): The nested path to the target split (e.g. ["splits", "chessred2k", "train"]).

    Returns:
        set[int]: Set of image IDs found under the given path, or an empty set if not found.

    Example:
        _ids_from(d, ["splits", "chessred2k", "train"])
        → {1, 2, 3}
    """
    node = _walk(d, key_path)
    if isinstance(node, dict):
        ids = node.get("image_ids", [])
        return set(ids) if isinstance(ids, list) else set()
    return set()


# Filesystem helpers
def find_image(rel: str) -> Optional[Path]:
    """
    Join the dataset root (IMG_2K) with a relative path from JSON and verify it exists.

    Args:
        rel (str): Relative path from annotations.json, e.g. "images/3/G003_IMG000.jpg".

    Returns:
        pathlib.Path | None: Absolute, resolved path if the file exists; otherwise None.

    Notes:
        - .resolve() normalizes the path (handles "..", symlinks) and produces an absolute path.
        - Returning None lets the caller skip unusable records without crashing.
    """
    p = (IMG_2K / rel).resolve()
    return p if p.exists() else None



def ensure_clean_out(out_root: Path, splits=("train", "val", "test")) -> None:
    """
    Recreate an empty YOLO-KP output tree at data/yolo_kp/.

    Side effects:
        - If data/yolo_kp/ exists, delete it entirely (shutil.rmtree).
        - Then make:
            data/yolo_kp/images/{train,val,test}
            data/yolo_kp/labels/{train,val,test}

    Notes:
        - This guarantees a fresh dataset each run (no stale files).
        - Be careful: rmtree() permanently removes the existing output directory.
    """
    if out_root.exists():
        shutil.rmtree(out_root)
    for s in splits:
        (out_root / "images" / s).mkdir(parents=True, exist_ok=True)
        (out_root / "labels" / s).mkdir(parents=True, exist_ok=True)