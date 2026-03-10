# ScanMate
```
git clone https://github.com/itayzahor/ScanMate.git

cd ScanMate\ML

py -m venv .venv

.\.venv\Scripts\activate

pip install -r requirements.txt

to run debug server

python debug_server.py

and go to link http://127.0.0.1:8000/

to run server for app 

python server.py 

then on another terminal 

npx react-native run-android

> ℹ️ The `/recognize_board/` gatekeeper (blur + hand detection) now depends on MediaPipe. Run `pip install -r requirements.txt` after pulling to ensure the `mediapipe` wheels are present; on Windows you may need Visual C++ Redistributable 2015 or newer for the native ops.


# data

corners detection dataset

https://universe.roboflow.com/chessboard-corner-detection-3b5bs/chessboard-detection-yqcnu/dataset/3

chess pieces detection dataset 

https://universe.roboflow.com/fhv/chess-pieces-2-6l8qq



# download stockfish 

extract it to ML/engines folder

https://stockfishchess.org/download/


## API Endpoints

### `POST /recognize_board/`
- **Body**: multipart form with a single `file` field (JPEG or PNG bytes of the board photo).
- **Response**:
	```json
	{
		"status": "success",
		"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
		"processing_time_seconds": 3.41
	}
	```
- **Errors**: `422` when the pipeline cannot find a chessboard, `400` on invalid input.

### `POST /analyze_position/`
- **Body (JSON)**:
	```json
	{
		"fen": "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 2 4",
		"depth": 18,
		"multipv": 3
	}
	```
	- `fen` (required): Forsyth–Edwards Notation string understood by Stockfish.
	- `depth` (optional): 1–40 search depth, defaults to 14 if omitted.
	- `multipv` (optional): 1–5 candidate lines to return, defaults to 1.
- **Response**:
	```json
	{
		"status": "success",
		"depth": 18,
		"engine": "Stockfish 17.1",
		"lines": [
			{
				"best_move": "e4e5",
				"best_move_san": "e5",
				"evaluation": { "type": "cp", "value": 35 },
				"pv": ["e5", "Nf3", "Nc6", "Bc4"]
			}
		]
	}
	```
- **Errors**:
	- `400` for invalid FEN strings.
	- `503` if the Stockfish binary is missing (set the `STOCKFISH_PATH` env var or place the engine under `ML/engines/stockfish`).
	- `500` for unexpected engine failures.

Both endpoints are served by `python ML/server.py` (Uvicorn on `http://0.0.0.0:8000`).

## Offline video replay + occlusion smoothing

- `python ML/video_replay.py --video data/chessgame.mp4 --frame-step 2 --save-failures` replays a recording frame-by-frame, logs one JSON line per sampled frame (`runs/video_replay/<video>_log.jsonl`), and optionally dumps the raw frames for later inspection.
- Add `--report-html chessgame_report.html` (optionally `--report-title "My Test"`) to emit an HTML report under `runs/video_replay/`. The report lists every sampled frame, embeds the captured image, and annotates the inferred move (difference between consecutive FEN snapshots).
- Add `--clean-output` if you want to wipe the previous log, `successes/`, `failures/`, and report frame folders inside `--output-dir` before reprocessing the video.
- `python ML/replay_viewer.py --log runs/video_replay/chessgame_log.jsonl --frames runs/video_replay/report_frames --port 8050` launches a FastAPI viewer at `http://127.0.0.1:8050/` that streams the same frames/moves via an endpoint so you can browse them live. (Instead of CLI flags you can also set `REPLAY_LOG_PATH`, `REPLAY_FRAMES_DIR`, and `REPLAY_TITLE` env vars and run `uvicorn replay_viewer:app`).
- The replay harness and both FastAPI servers now keep lightweight per-session history for piece placement (each mapped square persists for three frames unless a new detection contradicts it), but board corners are recalculated per photo so occluded corners once again fail fast.
- Use `/recognize_board/` for single-shot captures (no gatekeeper, no session state) and `/recognize_board_session/` when you need the full smoothing + gatekeeper flow. The session endpoint requires a `session_id` query parameter (pick any string, e.g. `?session_id=debug`).
- Session-aware calls still seed their history from the standard starting FEN, so the first accepted frame must be a legal move from that baseline. Stream a photo of the untouched opening position (or create a session with a custom `starting_fen`) before jumping into a mid-game, otherwise the logic filter will keep falling back to the initial board.
- Manage capture lifecycles with the new session endpoints:
	- `POST /sessions/` with an optional `session_id`, custom `starting_fen`, and `persistence_frames` lets you preconfigure smoothing before streaming frames.
	- `GET /sessions/` lists active sessions plus timestamps, while `GET /sessions/{session_id}/` returns a single record.
	- `DELETE /sessions/{session_id}/` clears the smoothing cache once a game finishes so idle sessions do not accumulate forever.
	- `/recognize_board_session/` will still lazily create a session on first use, but explicit creation is required if you want non-default settings for mid-game resumes.


The flow is now:

Frame N	Frame N+1	Result
Diff triggers → move found	No diff, but YOLO still sees same move	✅ Confirmed
Diff triggers → move found	No diff, YOLO disagrees	Idle counter +1, discard after 3
Diff triggers → move A found	Diff triggers → different move B	Pending replaced with B
Diff triggers → flicker move	No diff, YOLO no longer sees it	Idle → discarded

python video_viewer.py --video data/chessgame.mp4 --frame-step 25 --start-frame 4500 --starting-fen "r1bqk2r/p4ppp/2pp4/2b1p3/8/3P1N2/PPP2PPP/R1BQK2R"

python video_viewer.py --video data/chessgame.mp4 --frame-step 25 --start-frame 20000 --starting-fen "r5k1/p4pp1/7p/2p5/3r4/P7/5RPP/7K"