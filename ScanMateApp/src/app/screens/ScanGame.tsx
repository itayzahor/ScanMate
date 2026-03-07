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

import { styles } from '../../ui/styles/ScanBoard.styles';
import type { RootStackParamList } from '../../../App';
import { ScreenHeader } from '../../ui/components/ScreenHeader';
import { getBoardSize, HEADER_HEIGHT } from '../../shared/constants/layout';
import { uploadBoardPhoto } from '../../services/api';
import { evaluateOcclusionRisk } from '../../shared/utils/occlusionGuard';
import type { GameSnapshot } from '../../shared/types/game';
import { normalizeFen } from '../../shared/utils/fen';

const BOARD_TOP_GAP = 24;
const CAPTURE_INTERVAL_MS = 3500;
const RECORD_TIPS = [
  'Mount the phone so the board stays centered',
  'Keep hands outside the green frame between moves',
  'Pause recording any time play stops',
];

type ScanGameProps = NativeStackScreenProps<RootStackParamList, 'ScanGame'>;

type CaptureState = 'idle' | 'recording' | 'waiting';

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
  const [snapshots, setSnapshots] = useState<GameSnapshot[]>([]);
  const [isProcessingFrame, setIsProcessingFrame] = useState(false);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const lastFenRef = useRef<string | null>(null);
  const pendingReviewRef = useRef(false);

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

  const scheduleNextFrame = useCallback(
    (delay: number, task: () => void) => {
      clearTimer();
      timerRef.current = setTimeout(task, delay);
    },
    [clearTimer],
  );

  const stopRecording = useCallback(
    (options?: { showReview?: boolean }) => {
      clearTimer();
      setCaptureStateSafe('idle');
      if (options?.showReview) {
        if (snapshots.length > 0) {
          navigation.navigate('GameReview', {
            snapshots,
          });
        } else if (isProcessingFrame) {
          pendingReviewRef.current = true;
        } else {
          Alert.alert(
            'No positions captured',
            'We could not detect any board snapshots. Keep the board steady until the square fills with pieces, then try again.',
          );
        }
      }
    },
    [clearTimer, navigation, snapshots, setCaptureStateSafe, isProcessingFrame],
  );

  const handleRecordToggle = () => {
    if (captureState === 'recording') {
      stopRecording({ showReview: true });
      return;
    }

    setSnapshots([]);
    lastFenRef.current = null;
    setCaptureStateSafe('recording');
    captureFrame();
  };

  const captureFrame = useCallback(async () => {
    if (
      captureStateRef.current !== 'recording' ||
      cameraRef.current == null ||
      isProcessingFrame
    ) {
      return;
    }

    setIsProcessingFrame(true);
    let resizedPath: string | null = null;

    try {
      const photo = await cameraRef.current.takePhoto({ flash: 'off' });
      const photoPath = photo.path;
      const photoUri = photoPath.startsWith('file://') ? photoPath : `file://${photoPath}`;

      if (!photo.width || !photo.height) {
        throw new Error('Captured photo missing size info');
      }

      const { width: actualWidth, height: actualHeight } = await new Promise<{ width: number; height: number }>(
        (resolve, reject) => {
          Image.getSize(photoUri, (width, height) => resolve({ width, height }), reject);
        },
      );

      const displayScale = Math.max(windowWidth / actualWidth, windowHeight / actualHeight);
      const displayedWidth = actualWidth * displayScale;
      const displayedHeight = actualHeight * displayScale;
      const horizontalOverflow = Math.max(displayedWidth - windowWidth, 0) / 2;
      const verticalOverflow = Math.max(displayedHeight - windowHeight, 0) / 2;

      const boardPixelWidth = Math.floor(boardSize / displayScale);
      const squareSize = Math.min(boardPixelWidth, actualWidth, actualHeight);

      let offsetX = Math.floor((boardOffsetX + horizontalOverflow) / displayScale);
      offsetX = Math.max(0, Math.min(offsetX, actualWidth - squareSize));

      let offsetY = Math.floor((overlayTopPx + verticalOverflow) / displayScale);
      offsetY = Math.max(0, Math.min(offsetY, actualHeight - squareSize));

      const cropData = {
        offset: { x: offsetX, y: offsetY },
        size: { width: squareSize, height: squareSize },
        displaySize: { width: 640, height: 640 },
        resizeMode: 'contain' as const,
      };

      const croppedResult = await ImageEditor.cropImage(photoUri, cropData);
      resizedPath = croppedResult.uri.replace('file://', '');

      const guardResult = await evaluateOcclusionRisk(croppedResult.uri);
      if (guardResult.status === 'retry') {
        console.log('[ScanGame] Frame rejected by occlusion guard', guardResult.reason);
        return;
      }

      const fen = await uploadBoardPhoto(resizedPath);
      const normalizedFen = normalizeFen(fen);
      if (normalizedFen === lastFenRef.current) {
        console.log('[ScanGame] Skipping duplicate fen');
        return;
      }

      lastFenRef.current = normalizedFen;
      setSnapshots((prev) => {
        const next = [
          ...prev,
          {
            fen: normalizedFen,
            timestamp: Date.now(),
            photoPath: resizedPath ?? undefined,
          },
        ];
        console.log('[ScanGame] Snapshot stored. Total =', next.length);
        return next;
      });
    } catch (error) {
      console.error('[ScanGame] Capture loop failed', error);
      Alert.alert('Capture Failed', error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setIsProcessingFrame(false);
      if (captureStateRef.current === 'recording') {
        scheduleNextFrame(CAPTURE_INTERVAL_MS, () => {
          captureFrame();
        });
      }
    }
  }, [boardOffsetX, boardSize, overlayTopPx, scheduleNextFrame, windowHeight, windowWidth, isProcessingFrame]);

  useEffect(() => {
    return () => {
      clearTimer();
      setCaptureStateSafe('idle');
    };
  }, [clearTimer, setCaptureStateSafe]);

  useEffect(() => {
    if (pendingReviewRef.current && snapshots.length > 0) {
      pendingReviewRef.current = false;
      navigation.navigate('GameReview', { snapshots });
    }
  }, [navigation, snapshots]);

  if (device == null) {
    return (
      <View style={styles.errorContainer}>
        <Text style={styles.errorText}>No camera device found.</Text>
      </View>
    );
  }

  const recordButtonLabel = captureState === 'recording' ? 'Stop' : 'Record';
  const showSpinner = captureState === 'recording' && isProcessingFrame;

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
              stopRecording();
              navigation.goBack();
            }}
            style={styles.screenHeader}
          />
        </View>

        <View style={styles.viewfinderSpacer} />

        <View style={[styles.tipsList, { width: boardSize }]}>
          {RECORD_TIPS.map((tip) => (
            <Text key={tip} style={styles.tipText}>
              {`• ${tip}`}
            </Text>
          ))}
        </View>

        <View style={styles.captureButtonContainer}>
          <TouchableOpacity
            style={[styles.captureButton, captureState === 'recording' && localStyles.recordingButton]}
            onPress={handleRecordToggle}
          >
            {showSpinner ? (
              <ActivityIndicator size="small" color="#FFF" />
            ) : (
              <Text style={styles.buttonText}>{recordButtonLabel}</Text>
            )}
          </TouchableOpacity>
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
});
