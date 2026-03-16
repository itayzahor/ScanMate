import {Platform} from 'react-native';

// Set this to your laptop/desktop LAN IP when testing on a physical device.
// Leave it as an empty string when using an Android emulator (which can hit 10.0.2.2).
const LAN_HOST = '';
const LAN_BASE_URL = LAN_HOST ? `http://${LAN_HOST}:8000` : null;

const DEFAULT_BASE_URL = Platform.select({
  android: 'http://10.0.2.2:8000',
  ios: 'http://localhost:8000',
  default: 'http://localhost:8000',
});

const API_BASE_URL = LAN_BASE_URL ?? DEFAULT_BASE_URL ?? 'http://localhost:8000';

export type RecognizeBoardResponse = {
  status: 'success' | 'error';
  fen?: string;
  message?: string;
};

export type AnalysisLine = {
  best_move: string;
  best_move_san: string;
  evaluation: {
    type: 'cp' | 'mate' | 'unknown';
    value: number | null;
  };
  pv: string[];
};

export type AnalyzePositionResponse = {
  status: 'success';
  depth: number;
  engine: string;
  lines: AnalysisLine[];
};

type AnalyzePositionErrorResponse = {
  detail?: string;
  message?: string;
};

const extractApiMessage = (payload: unknown): string | undefined => {
  if (!payload || typeof payload !== 'object') {
    return undefined;
  }

  const detail = (payload as AnalyzePositionErrorResponse).detail;
  if (typeof detail === 'string') {
    return detail;
  }

  const message = (payload as AnalyzePositionErrorResponse).message;
  if (typeof message === 'string') {
    return message;
  }

  return undefined;
};

export const uploadBoardPhoto = async (filePath: string): Promise<string> => {
  const fileUri = filePath.startsWith('file://') ? filePath : `file://${filePath}`;
  const formData = new FormData();

  formData.append('file', {
    uri: fileUri,
    type: 'image/jpeg',
    name: 'scan.jpg',
  } as unknown as Blob);

  const endpoint = `${API_BASE_URL}/recognize_position/`;
  console.log('[uploadBoardPhoto] POST ->', endpoint);

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: 'POST',
      body: formData,
      headers: {
        Accept: 'application/json',
      },
    });
  } catch (error) {
    console.error('[uploadBoardPhoto] Network error', error);
    throw error;
  }

  const responseText = await response.text();
  let json: RecognizeBoardResponse | null = null;
  try {
    json = JSON.parse(responseText);
  } catch (parseError) {
    console.warn('[uploadBoardPhoto] Failed to parse server response as JSON', parseError);
  }

  if (!response.ok) {
    const message = json?.message ?? `Server responded with status ${response.status}`;
    throw new Error(message);
  }

  if (!json) {
    throw new Error('Server returned an unexpected response.');
  }

  if (json.status !== 'success' || !json.fen) {
    throw new Error(json.message ?? 'Failed to process board image.');
  }

  return json.fen;
};

// --- Game Session Types ---

export type GameStartResponse = {
  status: string;
  game_id: string;
  starting_fen: string;
};

export type GameFrameResponse = {
  status: string;
  fen: string;
  move_number: number;
  move?: string;
  pending?: string;
};

export type GameEndResponse = {
  status: string;
  game_id: string;
  moves: string[];
  move_count: number;
  final_fen: string;
};

// --- Game Session Functions ---

export const startGame = async (startingFen?: string, mode?: 'live' | 'video'): Promise<GameStartResponse> => {
  const endpoint = `${API_BASE_URL}/recognize_game/`;
  console.log('[startGame] POST ->', endpoint);
  const t0 = Date.now();

  const payload: Record<string, string | undefined> = {};
  if (startingFen) {
    payload.starting_fen = startingFen;
  }
  if (mode) {
    payload.mode = mode;
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {Accept: 'application/json', 'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });

  const json = await response.json();
  if (!response.ok) {
    throw new Error(extractApiMessage(json) ?? `Server responded with status ${response.status}`);
  }
  console.log('[startGame] RTT(ms)=', Date.now() - t0);
  return json as GameStartResponse;
};

export const sendGameFrame = async (
  gameId: string,
  filePath: string,
): Promise<GameFrameResponse> => {
  const fileUri = filePath.startsWith('file://') || filePath.startsWith('content://')
    ? filePath
    : `file://${filePath}`;
  const formData = new FormData();
  formData.append('file', {
    uri: fileUri,
    type: 'image/jpeg',
    name: 'frame.jpg',
  } as unknown as Blob);

  const endpoint = `${API_BASE_URL}/recognize_game/${encodeURIComponent(gameId)}/frame`;
  console.log('[sendGameFrame] POST ->', endpoint);
  const t0 = Date.now();

  const response = await fetch(endpoint, {
    method: 'POST',
    body: formData,
    headers: {Accept: 'application/json'},
  });

  const json = await response.json();
  if (!response.ok) {
    throw new Error(extractApiMessage(json) ?? `Server responded with status ${response.status}`);
  }
  console.log('[sendGameFrame] RTT(ms)=', Date.now() - t0);
  console.log('[sendGameFrame] response:', JSON.stringify(json));
  return json as GameFrameResponse;
};

export const endGame = async (gameId: string): Promise<GameEndResponse> => {
  const endpoint = `${API_BASE_URL}/recognize_game/${encodeURIComponent(gameId)}/end`;
  console.log('[endGame] POST ->', endpoint);
  const t0 = Date.now();

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {Accept: 'application/json'},
  });

  const json = await response.json();
  if (!response.ok) {
    throw new Error(extractApiMessage(json) ?? `Server responded with status ${response.status}`);
  }
  console.log('[endGame] RTT(ms)=', Date.now() - t0);
  console.log('[endGame] response:', JSON.stringify(json));
  return json as GameEndResponse;
};

export const discardGame = async (gameId: string): Promise<void> => {
  const endpoint = `${API_BASE_URL}/recognize_game/${encodeURIComponent(gameId)}/`;
  console.log('[discardGame] DELETE ->', endpoint);

  const response = await fetch(endpoint, {
    method: 'DELETE',
    headers: {Accept: 'application/json'},
  });

  if (!response.ok) {
    const json = await response.json().catch(() => null);
    throw new Error(extractApiMessage(json) ?? `Server responded with status ${response.status}`);
  }
};

export const analyzePosition = async (
  fen: string,
  options?: { depth?: number; multipv?: number },
): Promise<AnalyzePositionResponse> => {
  const endpoint = `${API_BASE_URL}/analyze_position/`;
  console.log('[analyzePosition] POST ->', endpoint);

  const payload = {
    fen,
    depth: options?.depth,
    multipv: options?.multipv,
  };

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    console.error('[analyzePosition] Network error', error);
    throw error;
  }

  const responseText = await response.text();
  let json: AnalyzePositionResponse | AnalyzePositionErrorResponse | null = null;
  try {
    json = JSON.parse(responseText);
  } catch (parseError) {
    console.warn('[analyzePosition] Failed to parse server response as JSON', parseError);
  }

  if (!response.ok || !json || !('status' in json) || json.status !== 'success') {
    const message = extractApiMessage(json) ?? `Server responded with status ${response.status}`;
    throw new Error(message);
  }

  return json;
};
