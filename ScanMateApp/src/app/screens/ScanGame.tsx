import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Dimensions,
  Text,
  TouchableOpacity,
  View,
  StyleSheet,
  Image,
} from 'react-native';
import { Camera, useCameraDevice, useCameraFormat } from 'react-native-vision-camera';
import { useIsFocused } from '@react-navigation/native';
import ImageEditor from '@react-native-community/image-editor';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { launchImageLibrary } from 'react-native-image-picker';
import { createThumbnail } from 'react-native-create-thumbnail';
import RNFS from 'react-native-fs';
import { Chess } from 'chess.js';

import { styles } from '../../ui/styles/ScanBoard.styles';
import type { RootStackParamList } from '../../../App';
import { ScreenHeader } from '../../ui/components/ScreenHeader';
import { getBoardSize, HEADER_HEIGHT } from '../../shared/constants/layout';
import { startGame, sendGameFrame, endGame, discardGame } from '../../services/api';
import type { GameSnapshot } from '../../shared/types/game';
import { STARTING_FEN, normalizeFen } from '../../shared/utils/fen';

const BOARD_TOP_GAP = 24;
const CAPTURE_INTERVAL_MS = 1000;
const FRAME_STEP_MS = 2000;
const RECORD_TIPS = [
  'Mount the phone so the board stays centered',
  'Keep hands outside the green frame between moves',
  'Pause recording any time play stops',
];

type ScanGameProps = NativeStackScreenProps<RootStackParamList, 'ScanGame'>;

type CaptureState = 'idle' | 'recording' | 'uploading_video';

function movesToSnapshots(moves: string[], fen: string): GameSnapshot[] {
  const chess = new Chess(normalizeFen(fen));
  const snapshots: GameSnapshot[] = [{ fen: chess.fen(), timestamp: Date.now() }];
  for (const san of moves) {
    chess.move(san);
    snapshots.push({ fen: chess.fen(), timestamp: Date.now() });
  }
  return snapshots;
}

export const ScanGame = ({ navigation }: ScanGameProps) => {
  const device = useCameraDevice('back');
  const cameraRef = useRef<Camera>(null);
  const isScreenFocused = useIsFocused();
  const boardSize = getBoardSize();
  const windowDimensions = Dimensions.get('window');
  const windowWidth = windowDimensions.width;
  const windowHeight = windowDimensions.height;
  const overlayTopPx = HEADER_HEIGHT + BOARD_TOP_GAP;
  const boardOffsetX = (windowWidth - boardSize) / 2;

  const [captureState, setCaptureState] = useState<CaptureState>('idle');
  const captureStateRef = useRef<CaptureState>('idle');
  const [moveCount, setMoveCount] = useState(0);
  const [videoProgress, setVideoProgress] = useState<{ current: number; total: number } | null>(null);
  const gameIdRef = useRef<string | null>(null);
  const movesRef = useRef<string[]>([]);
  const startingFenRef = useRef<string>(STARTING_FEN);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelledRef = useRef(false);
  const reviewOnStopRef = useRef(false);
  const isProcessingRef = useRef(false);

  const setCaptureStateSafe = useCallback((next: CaptureState) => {
    captureStateRef.current = next;
    setCaptureState(next);
  }, []);

  const format = useCameraFormat(device, [
    { photoResolution: 'max' },
    { fps: 30 },
  ]);
  const isActive = isScreenFocused;

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const finishGame = useCallback(async (navigateToReview: boolean) => {
    clearTimer();
    const gameId = gameIdRef.current;
    if (!gameId) {
      setCaptureStateSafe('idle');
      return;
    }

    try {
      const result = await endGame(gameId);
      console.log('[ScanGame] endGame result:', JSON.stringify(result));
      console.log('[ScanGame] movesRef had:', movesRef.current.length, 'moves');
      gameIdRef.current = null;
      setCaptureStateSafe('idle');
      setVideoProgress(null);

      if (navigateToReview && result.moves.length > 0) {
        const snapshots = movesToSnapshots(result.moves, startingFenRef.current);
        navigation.navigate('GameReview', { snapshots, moves: result.moves });
      } else if (navigateToReview) {
        Alert.alert('No moves detected', 'The server could not detect any moves in the recording.');
      }
    } catch (error) {
      console.error('[ScanGame] endGame failed', error);
      gameIdRef.current = null;
      setCaptureStateSafe('idle');
      setVideoProgress(null);
    }
  }, [clearTimer, navigation, setCaptureStateSafe]);

  const stopGame = useCallback(() => {
    clearTimer();
    cancelledRef.current = true;
    reviewOnStopRef.current = true;
    // The upload loop will see the flags and call finishGame after the in-flight frame completes
  }, [clearTimer]);

  const cancelGame = useCallback(async () => {
    clearTimer();
    cancelledRef.current = true;
    reviewOnStopRef.current = false;
    const gameId = gameIdRef.current;
    if (gameId) {
      try { await discardGame(gameId); } catch {}
      gameIdRef.current = null;
    }
    setCaptureStateSafe('idle');
    setVideoProgress(null);
    setMoveCount(0);
  }, [clearTimer, setCaptureStateSafe]);

  // --- Live Recording ---

  const captureFrame = useCallback(async () => {
    if (captureStateRef.current !== 'recording' || !cameraRef.current || isProcessingRef.current) {
      return;
    }

    isProcessingRef.current = true;
    try {
      const photo = await cameraRef.current.takePhoto({ flash: 'off' });
      const photoPath = photo.path;
      const photoUri = photoPath.startsWith('file://') ? photoPath : `file://${photoPath}`;

      if (!photo.width || !photo.height) {
        throw new Error('Captured photo missing size info');
      }

      const { width: actualWidth, height: actualHeight } = await new Promise<{ width: number; height: number }>(
        (resolve, reject) => {
          Image.getSize(photoUri, (w, h) => resolve({ width: w, height: h }), reject);
        },
      );

      const displayScale = Math.max(windowWidth / actualWidth, windowHeight / actualHeight);
      const boardPixelWidth = Math.floor(boardSize / displayScale);
      const squareSize = Math.min(boardPixelWidth, actualWidth, actualHeight);
      const horizontalOverflow = Math.max(actualWidth * displayScale - windowWidth, 0) / 2;
      const verticalOverflow = Math.max(actualHeight * displayScale - windowHeight, 0) / 2;

      let offsetX = Math.floor((boardOffsetX + horizontalOverflow) / displayScale);
      offsetX = Math.max(0, Math.min(offsetX, actualWidth - squareSize));
      let offsetY = Math.floor((overlayTopPx + verticalOverflow) / displayScale);
      offsetY = Math.max(0, Math.min(offsetY, actualHeight - squareSize));

      const croppedResult = await ImageEditor.cropImage(photoUri, {
        offset: { x: offsetX, y: offsetY },
        size: { width: squareSize, height: squareSize },
        displaySize: { width: 640, height: 640 },
        resizeMode: 'contain' as const,
      });

      const resizedPath = croppedResult.uri.replace('file://', '');
      const gameId = gameIdRef.current;
      if (!gameId || captureStateRef.current !== 'recording') {
        return;
      }

      const resp = await sendGameFrame(gameId, resizedPath);
      if (resp.move) {
        movesRef.current.push(resp.move);
        setMoveCount(movesRef.current.length);
      }
    } catch (error) {
      console.error('[ScanGame] Capture loop error', error);
    } finally {
      isProcessingRef.current = false;
      if (captureStateRef.current === 'recording') {
        clearTimer();
        timerRef.current = setTimeout(() => captureFrame(), CAPTURE_INTERVAL_MS);
      }
    }
  }, [boardOffsetX, boardSize, clearTimer, overlayTopPx, windowHeight, windowWidth]);

  const handleRecordToggle = useCallback(async () => {
    if (captureState === 'recording') {
      await finishGame(true);
      return;
    }
    if (captureState !== 'idle') {
      return;
    }

    try {
      movesRef.current = [];
      setMoveCount(0);
      cancelledRef.current = false;
      const result = await startGame();
      gameIdRef.current = result.game_id;
      startingFenRef.current = result.starting_fen;
      setCaptureStateSafe('recording');
      captureFrame();
    } catch (error) {
      console.error('[ScanGame] startGame failed', error);
      Alert.alert('Error', error instanceof Error ? error.message : 'Failed to start game session');
    }
  }, [captureState, captureFrame, finishGame, setCaptureStateSafe]);

  // --- Video Upload ---

  const handleLoadVideo = useCallback(async () => {
    if (captureState !== 'idle') {
      return;
    }

    const pickerResult = await launchImageLibrary({ mediaType: 'video', selectionLimit: 1 });
    const asset = pickerResult.assets?.[0];
    if (!asset?.uri || !asset.duration) {
      return;
    }

    const videoUri = asset.uri;
    const durationMs = asset.duration * 1000;
    const totalFrames = Math.ceil(durationMs / FRAME_STEP_MS);
    console.log(`[ScanGame] video duration=${asset.duration}s  durationMs=${durationMs}  totalFrames=${totalFrames}`);

    try {
      movesRef.current = [];
      setMoveCount(0);
      cancelledRef.current = false;
      reviewOnStopRef.current = false;
      const gameResult = await startGame(undefined, 'video');
      gameIdRef.current = gameResult.game_id;
      startingFenRef.current = gameResult.starting_fen;
      setCaptureStateSafe('uploading_video');
      setVideoProgress({ current: 0, total: totalFrames });

      for (let i = 0; i < totalFrames; i++) {
        if (cancelledRef.current) {
          break;
        }

        const timestampMs = i * FRAME_STEP_MS;
        const thumbnail = await createThumbnail({
          url: videoUri,
          timeStamp: timestampMs,
          format: 'jpeg',
          maxWidth: 640,
          maxHeight: 640,
        });

        if (cancelledRef.current) {
          break;
        }

        const resp = await sendGameFrame(gameIdRef.current!, thumbnail.path);
        // Delete temp thumbnail to avoid filling up storage
        RNFS.unlink(thumbnail.path).catch(() => {});
        if (resp.move) {
          movesRef.current.push(resp.move);
          setMoveCount(movesRef.current.length);
        }
        setVideoProgress({ current: i + 1, total: totalFrames });
      }

      if (!cancelledRef.current) {
        await finishGame(true);
      } else if (reviewOnStopRef.current) {
        // User pressed "Stop & Review" — finalize after the in-flight frame is done
        await finishGame(true);
      }
      // else: user pressed Cancel — cancelGame already handled cleanup
    } catch (error) {
      console.error('[ScanGame] Video upload error', error);
      if (!cancelledRef.current) {
        Alert.alert('Error', error instanceof Error ? error.message : 'Video processing failed');
        await cancelGame();
      }
    }
  }, [captureState, finishGame, cancelGame, setCaptureStateSafe]);

  // --- Cleanup ---

  useEffect(() => {
    return () => {
      clearTimer();
      cancelledRef.current = true;
      const gameId = gameIdRef.current;
      if (gameId) {
        discardGame(gameId).catch(() => {});
        gameIdRef.current = null;
      }
    };
  }, [clearTimer]);

  if (device == null) {
    return (
      <View style={styles.errorContainer}>
        <Text style={styles.errorText}>No camera device found.</Text>
      </View>
    );
  }

  const isRecording = captureState === 'recording';
  const isUploading = captureState === 'uploading_video';
  const isIdle = captureState === 'idle';

  return (
    <View style={styles.container}>
      <Camera
        ref={cameraRef}
        style={StyleSheet.absoluteFill}
        device={device}
        isActive={isActive}
        format={format}
        photo
        resizeMode="cover"
      />

      <View style={styles.viewfinderContainer}>
        <View style={[styles.viewfinderTopMask, { height: overlayTopPx }]} />
        <View style={styles.viewfinderMiddleRow}>
          <View style={styles.viewfinderSideMask} />
          <View style={styles.viewfinderGuide} />
          <View style={styles.viewfinderSideMask} />
        </View>
        <View style={styles.viewfinderBottomMask} />
      </View>

      <View style={styles.overlayControls}>
        <View style={styles.instructionBox}>
          <ScreenHeader
            title="Record Game"
            subtitle="Phone stays over the board. We capture every few seconds."
            onBack={() => {
              if (isRecording || isUploading) {
                cancelGame();
              }
              navigation.goBack();
            }}
            style={styles.screenHeader}
          />
        </View>

        <View style={styles.viewfinderSpacer} />

        {isIdle && (
          <View style={[styles.tipsList, { width: boardSize }]}>
            {RECORD_TIPS.map((tip) => (
              <Text key={tip} style={styles.tipText}>
                {`• ${tip}`}
              </Text>
            ))}
          </View>
        )}

        {isRecording && (
          <View style={localStyles.statusBar}>
            <Text style={localStyles.statusText}>
              {moveCount > 0
                ? `${moveCount} move${moveCount !== 1 ? 's' : ''} detected`
                : 'Watching for moves…'}
            </Text>
          </View>
        )}

        {isUploading && videoProgress && (
          <View style={localStyles.progressOverlay}>
            <ActivityIndicator size="large" color="#fff" />
            <Text style={localStyles.progressText}>
              Frame {videoProgress.current}/{videoProgress.total}
            </Text>
            {moveCount > 0 && (
              <Text style={localStyles.statusText}>
                {moveCount} move{moveCount !== 1 ? 's' : ''} detected
              </Text>
            )}
            <View style={localStyles.buttonRow}>
              <TouchableOpacity style={localStyles.stopButton} onPress={stopGame}>
                <Text style={localStyles.stopText}>Stop & Review</Text>
              </TouchableOpacity>
              <TouchableOpacity style={localStyles.cancelButton} onPress={cancelGame}>
                <Text style={localStyles.cancelText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        <View style={styles.captureButtonContainer}>
          {!isUploading && (
            <TouchableOpacity
              style={[styles.captureButton, isRecording && localStyles.recordingButton]}
              onPress={handleRecordToggle}
            >
              <Text style={styles.buttonText}>{isRecording ? 'Stop' : 'Record'}</Text>
            </TouchableOpacity>
          )}
          {isIdle && (
            <TouchableOpacity style={localStyles.loadVideoButton} onPress={handleLoadVideo}>
              <Text style={localStyles.loadVideoText}>Load Video</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </View>
  );
};

const localStyles = StyleSheet.create({
  recordingButton: {
    backgroundColor: '#c0392b',
    borderColor: '#fff',
  },
  statusBar: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    backgroundColor: 'rgba(0,0,0,0.6)',
    borderRadius: 8,
    marginTop: 12,
  },
  statusText: {
    color: '#fff',
    fontSize: 15,
    textAlign: 'center',
  },
  progressOverlay: {
    alignItems: 'center',
    paddingVertical: 20,
    gap: 12,
  },
  progressText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 8,
  },
  stopButton: {
    paddingVertical: 10,
    paddingHorizontal: 20,
    backgroundColor: '#007AFF',
    borderRadius: 8,
  },
  stopText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  cancelButton: {
    paddingVertical: 10,
    paddingHorizontal: 20,
    backgroundColor: '#c0392b',
    borderRadius: 8,
  },
  cancelText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  loadVideoButton: {
    marginTop: 16,
    paddingVertical: 12,
    paddingHorizontal: 28,
    backgroundColor: 'rgba(255,255,255,0.15)',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.3)',
  },
  loadVideoText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
