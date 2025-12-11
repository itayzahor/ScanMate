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


# data

corners detection dataset

https://universe.roboflow.com/chessboard-corner-detection-3b5bs/chessboard-detection-yqcnu/dataset/3

chess pieces detection dataset 

https://universe.roboflow.com/fhv/chess-pieces-2-6l8qq


# Strategy to get better perosnalised boards 

### Personalized Chess-Piece Recognition — Final Strategy
1. Default mode: generic model

App uses the pretrained YOLO model right away.

If predictions are accurate → done (no friction).

If confidence drops or errors > 2 → suggest a quick board scan.

2. Board scan (user calibration)

User takes 1–3 photos of the starting position.

App detects board corners, flattens image, and uses the known FEN to auto-label all pieces.

This generates ~32 labeled samples instantly (one per piece).

3. Two-layer learning process

A. On-device “train” (fast)

Extract embeddings → build per-class prototypes.

Use nearest-prototype classification for immediate, personalized results.

B. Server-side “update” (background)

Upload these crops and auto-labels.

Fine-tune only YOLO’s final layers on the new samples (1–5 min).

Improved global model benefits all users over time.

4. Active learning while playing

If the app is uncertain, show a one-tap correction (“Knight? Bishop?”).

Store correction → refine prototypes and feed back to global training.

✅ Result

Smooth experience for most users (no scan needed).

Personalized accuracy for unique boards when scanned.

Continuous improvement of both local and global models.


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

