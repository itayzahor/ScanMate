"""Test script: play a video against the /recognize_game/ server endpoints.

Usage
-----
1. Start the server:   python server.py
2. Run this script:    python tests/test_game_server.py [--video data/chessgame.mp4] [--frame-step 25]

The script opens the video, creates a game session, sends every Nth frame,
prints each detected move live, and at the end calls /end to get the full
move list.  A simple OpenCV window shows the current board position and
detected moves as they come in.

terminal:
python tests/test_game_server.py --video data/chessgame.mp4 --frame-step 12
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests

SERVER = "http://localhost:8000"
SEND_SIZE = 640       # resize before encoding — models use 640x640 anyway
JPEG_QUALITY = 70     # lower = smaller payload, still fine for detection
FILES = "abcdefgh"


# ---------------------------------------------------------------------------
# Simple chess-board visualisation (copied from video_viewer, stripped down)
# ---------------------------------------------------------------------------

def draw_chess_board(fen: str, size: int = 480) -> np.ndarray:
    board_img = np.zeros((size, size, 3), dtype=np.uint8)
    sq = size // 8

    for row in range(8):
        for col in range(8):
            color = (240, 217, 181) if (row + col) % 2 == 0 else (181, 136, 99)
            cv2.rectangle(board_img, (col * sq, row * sq), ((col + 1) * sq, (row + 1) * sq), color, -1)

    piece_map = dict(zip("PNBRQKpnbrqk", "PNBRQKpnbrqk"))
    try:
        ranks = fen.split()[0].split("/")
        for rank_idx, rank_str in enumerate(ranks):
            file_idx = 0
            for ch in rank_str:
                if ch.isdigit():
                    file_idx += int(ch)
                elif ch in piece_map:
                    x = file_idx * sq + sq // 2
                    y = rank_idx * sq + sq // 2
                    sym = piece_map[ch]
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    sc, th = 1.0, 2
                    (tw, tht), _ = cv2.getTextSize(sym, font, sc, th + 2)
                    tx, ty = x - tw // 2, y + tht // 2
                    if ch.isupper():
                        cv2.putText(board_img, sym, (tx, ty), font, sc, (0, 0, 0), th + 2, cv2.LINE_AA)
                        cv2.putText(board_img, sym, (tx, ty), font, sc, (255, 255, 255), th, cv2.LINE_AA)
                    else:
                        cv2.putText(board_img, sym, (tx, ty), font, sc, (255, 255, 255), th + 2, cv2.LINE_AA)
                        cv2.putText(board_img, sym, (tx, ty), font, sc, (0, 0, 0), th, cv2.LINE_AA)
                    file_idx += 1
    except Exception:
        pass

    # File / rank labels
    font, sc, th = cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1
    for i, f in enumerate(FILES):
        cv2.putText(board_img, f, (i * sq + sq // 2 - 4, size - 4), font, sc, (100, 100, 100), th)
    for i in range(8):
        cv2.putText(board_img, str(8 - i), (4, i * sq + sq // 2 + 4), font, sc, (100, 100, 100), th)

    return board_img


def draw_move_list(moves: list[str], size: tuple[int, int] = (300, 480)) -> np.ndarray:
    """Draw a panel listing the moves so far (white/black pairs)."""
    w, h = size
    panel = np.zeros((h, w, 3), dtype=np.uint8)
    font, sc, th = cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1
    y = 25
    cv2.putText(panel, "Moves", (10, y), font, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
    y += 30

    for i in range(0, len(moves), 2):
        move_num = i // 2 + 1
        white = moves[i]
        black = moves[i + 1] if i + 1 < len(moves) else ""
        line = f"{move_num}. {white}  {black}"
        cv2.putText(panel, line, (10, y), font, sc, (255, 255, 255), th, cv2.LINE_AA)
        y += 22
        if y > h - 10:
            break

    return panel


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Test /recognize_game/ with a video file")
    p.add_argument("--video", type=Path, default=Path("data/chessgame.mp4"))
    p.add_argument("--server", type=str, default=SERVER)
    p.add_argument("--starting-fen", type=str, default=None, help="Custom starting FEN")
    p.add_argument("--frame-step", type=int, default=25, help="Send every Nth frame (default 25 ≈ 1 FPS)")
    p.add_argument("--start-frame", type=int, default=0)
    p.add_argument("--dump-sent-dir", type=Path, default=None,
                   help="Optional folder to save the exact JPEG bytes sent to /frame")
    p.add_argument("--no-display", action="store_true", help="Headless mode — print only, no OpenCV window")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    base = args.server.rstrip("/")

    if args.dump_sent_dir is not None:
        args.dump_sent_dir.mkdir(parents=True, exist_ok=True)

    if not args.video.exists():
        print(f"Video not found: {args.video}")
        sys.exit(1)

    # Reuse TCP connection across all requests.
    http = requests.Session()

    # 1. Start a game
    payload = {}
    if args.starting_fen:
        payload["starting_fen"] = args.starting_fen
    resp = http.post(f"{base}/recognize_game/", json=payload)
    resp.raise_for_status()
    game = resp.json()
    game_id = game["game_id"]
    starting_fen = game["starting_fen"]
    print(f"Game started: {game_id}")
    print(f"Starting FEN: {starting_fen}\n")

    # 2. Open video
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        print(f"Could not open video: {args.video}")
        sys.exit(1)

    if args.start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, args.start_frame)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    current_fen = starting_fen
    moves: list[str] = []
    frame_idx = args.start_frame - 1
    frames_sent = 0
    frame_times: list[float] = []   # ms per frame (server round-trip)
    show = not args.no_display

    print("Sending frames... (press Q in the window to stop early)\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1

            if (frame_idx - args.start_frame) % args.frame_step != 0:
                continue

            # Resize to model input size and encode as JPEG before sending.
            small = cv2.resize(frame, (SEND_SIZE, SEND_SIZE))
            ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not ok:
                continue

            if args.dump_sent_dir is not None:
                dump_path = args.dump_sent_dir / f"frame_{frames_sent + 1:05d}_upload.jpg"
                dump_path.write_bytes(buf.tobytes())

            t0 = time.perf_counter()
            try:
                resp = http.post(
                    f"{base}/recognize_game/{game_id}/frame",
                    files={"file": ("frame.jpg", buf.tobytes(), "image/jpeg")},
                )
                elapsed = (time.perf_counter() - t0) * 1000
                frame_times.append(elapsed)
                frames_sent += 1
            except requests.ConnectionError:
                print("Connection lost — is the server running?")
                break

            if resp.status_code != 200:
                print(f"  Frame {frame_idx}: HTTP {resp.status_code} — {resp.text[:80]}")
                continue

            data = resp.json()
            status = data["status"]
            current_fen = data.get("fen", current_fen)

            if status == "move_detected":
                move_san = data["move"]
                move_num = data["move_number"]
                moves.append(move_san)
                # Print with move numbering (1. e4 e5  2. Nf3 Nc6 ...)
                if move_num % 2 == 1:
                    print(f"  {move_num // 2 + 1}. {move_san}", end="", flush=True)
                else:
                    print(f"  {move_san}")
            elif status == "rejected":
                pass  # gatekeeper blocked — normal
            elif status == "no_board":
                pass  # board not in view — normal
            elif status == "skipped":
                pass  # hand budget exhausted — cheap frame

            # Progress indicator every 50 frames
            if frames_sent % 50 == 0:
                pct = frame_idx / total_frames * 100 if total_frames else 0
                print(f"\n  [{frames_sent} frames sent, {pct:.0f}% of video, {len(moves)} moves]")

            # Display
            if show:
                board_img = draw_chess_board(current_fen)
                move_panel = draw_move_list(moves)
                display = np.hstack([board_img, move_panel])

                # Status bar
                bar_h = 35
                bar = np.zeros((bar_h, display.shape[1], 3), dtype=np.uint8)
                info = f"Frame {frame_idx}/{total_frames}  |  {elapsed:.0f}ms  |  {status}  |  Moves: {len(moves)}"
                cv2.putText(bar, info, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
                display = np.vstack([bar, display])

                cv2.imshow("Game Test", display)
                if cv2.waitKey(1) in (ord("q"), 27):
                    print("\n\nStopped early by user.")
                    break

    finally:
        cap.release()
        if show:
            cv2.destroyAllWindows()

    # 3. End the game
    print(f"\n\nEnding game ({frames_sent} frames sent)...")
    resp = http.post(f"{base}/recognize_game/{game_id}/end")
    resp.raise_for_status()
    result = resp.json()

    print(f"\n{'=' * 50}")
    print(f"Game ID:    {result['game_id']}")
    print(f"Moves:      {result['move_count']}")
    print(f"Final FEN:  {result['final_fen']}")
    print(f"{'=' * 50}")

    # Pretty-print the full game
    moves_list = result["moves"]
    print("\nFull game:")
    for i in range(0, len(moves_list), 2):
        num = i // 2 + 1
        white = moves_list[i]
        black = moves_list[i + 1] if i + 1 < len(moves_list) else ""
        print(f"  {num}. {white}  {black}")

    # --- Performance summary ---
    if frame_times:
        avg_ms = sum(frame_times) / len(frame_times)
        med_ms = sorted(frame_times)[len(frame_times) // 2]
        max_ms = max(frame_times)
        min_ms = min(frame_times)
        video_interval_ms = (args.frame_step / fps) * 1000
        realtime_ratio = video_interval_ms / avg_ms

        print(f"\n{'=' * 50}")
        print(f"Performance")
        print(f"{'=' * 50}")
        print(f"  Video FPS:          {fps:.1f}")
        print(f"  Frame step:         {args.frame_step}  (1 frame every {args.frame_step / fps:.2f}s of video)")
        print(f"  Video interval:     {video_interval_ms:.0f} ms between sent frames")
        print(f"  Avg processing:     {avg_ms:.0f} ms")
        print(f"  Median processing:  {med_ms:.0f} ms")
        print(f"  Min / Max:          {min_ms:.0f} / {max_ms:.0f} ms")
        print(f"  Realtime ratio:     {realtime_ratio:.2f}x")
        if realtime_ratio >= 1.0:
            print(f"  --> FAST ENOUGH: processing is {realtime_ratio:.1f}x faster than video playback")
        else:
            lag_pct = (1 - realtime_ratio) * 100
            print(f"  --> TOO SLOW: processing is {lag_pct:.0f}% slower than video playback")

    print()


if __name__ == "__main__":
    main()
