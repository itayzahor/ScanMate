import React, {useRef, useState} from 'react';
import {Text, View, TouchableOpacity, StyleSheet, ActivityIndicator, Alert, Image, Dimensions} from 'react-native';
import {Camera, useCameraDevice, useCameraFormat} from 'react-native-vision-camera';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {useIsFocused} from '@react-navigation/native';
import ImageEditor from '@react-native-community/image-editor';

import {styles} from '../../ui/styles/ScanBoard.styles';
import type {RootStackParamList} from '../../../App';
import {ScreenHeader} from '../../ui/components/ScreenHeader';
import {getBoardSize, HEADER_HEIGHT} from '../../shared/constants/layout';

const BOARD_TOP_GAP = 24;
const SCAN_TIPS = [
  'Keep the phone steady directly above the board',
  'Make sure all four corners sit inside the green frame',
  'Avoid harsh shadows or glare on the pieces',
];

type ScanBoardProps = NativeStackScreenProps<RootStackParamList, 'ScanBoard'>;

export const ScanBoard = ({navigation}: ScanBoardProps) => {
  const device = useCameraDevice('back');
  const cameraRef = useRef<Camera>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const isScreenFocused = useIsFocused();
  const boardSize = getBoardSize();
  const windowDimensions = Dimensions.get('window');
  const windowWidth = windowDimensions.width;
  const windowHeight = windowDimensions.height;
  const overlayTopPx = HEADER_HEIGHT + BOARD_TOP_GAP;
  const boardOffsetX = (windowWidth - boardSize) / 2;

  // Defines a valid camera format with photo capabilities and 30fps
  const format = useCameraFormat(device, [
    {photoResolution: 'max'},
    {fps: 30},
  ]);

  // Camera is active only when the screen is focused.
  const isActive = isScreenFocused;

  const capturePhoto = async () => {
    if (cameraRef.current == null || isCapturing) {
      return;
    }

    setIsCapturing(true); 
    let photoPath = null;
    let resizedPath = null;
    
    try {
      // 1. CAPTURE PHOTO (Full sensor image)
      const photo = await cameraRef.current.takePhoto({ flash: 'off' });
      photoPath = photo.path;
      const photoUri = photoPath.startsWith('file://') ? photoPath : `file://${photoPath}`;

      if (!photo.width || !photo.height) {
        throw new Error('Captured photo is missing size information');
      }

      // 2. CROP THE CENTER SQUARE AND SCALE to 640x640 to match the overlay
      const {width: actualWidth, height: actualHeight} = await new Promise<{width: number; height: number}>(
        (resolve, reject) => {
          Image.getSize(photoUri, (width, height) => resolve({width, height}), reject);
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
        offset: {
          x: offsetX,
          y: offsetY,
        },
        size: {width: squareSize, height: squareSize},
        displaySize: {width: 640, height: 640},
        resizeMode: 'contain' as const,
      };

      const croppedResult = await ImageEditor.cropImage(photoUri, cropData);
      resizedPath = croppedResult.uri.replace('file://', '');

    } catch (error) {
      console.error('Capture/Resize FAILED:', error);
      Alert.alert('Capture Failed!', 'There was an issue saving the photo.');
    } finally {
      setIsCapturing(false); 
    }

    // 3. NAVIGATE with the NEW, RESIZED path
    if (resizedPath) { 
      navigation.navigate('Result', { photoPath: resizedPath });
    }
  };
  if (device == null) {
    return (
      <View style={styles.errorContainer}>
        <Text style={styles.errorText}>No camera device found.</Text>
      </View>
    );
  }
  
  return (
    <View style={styles.container}>
      <Camera
        ref={cameraRef}
        style={StyleSheet.absoluteFill}
        device={device}
        isActive={isActive}
        format={format} 
        photo={true}
        resizeMode="cover"
      />
      
      {/* 1. OPAQUE BLACK MASK (Masks the area outside the board square) */}
      <View style={styles.viewfinderContainer}>
        <View style={[styles.viewfinderTopMask, {height: overlayTopPx}]} />
          <View style={styles.viewfinderMiddleRow}>
            <View style={styles.viewfinderSideMask} />
            {/* The transparent square cutout */}
            <View style={styles.viewfinderGuide} />
            <View style={styles.viewfinderSideMask} />
          </View>
          <View style={styles.viewfinderBottomMask} />
      </View>
      
      {/* 2. CONTROLS OVERLAY (The UI Layer) */}
      <View style={styles.overlayControls}>
        
        {/* Top instructions text */}
        <View style={styles.instructionBox}>
          <ScreenHeader
            title="Scan Board"
            onBack={() => navigation.goBack()}
            style={styles.screenHeader}
          />
        </View>

        <View style={styles.viewfinderSpacer} />

        <View style={[styles.tipsList, { width: boardSize }]}>
          {SCAN_TIPS.map((tip) => (
            <Text key={tip} style={styles.tipText}>
              {`• ${tip}`}
            </Text>
          ))}
        </View>
        
        <View style={styles.captureButtonContainer}>
          <TouchableOpacity 
            style={[styles.captureButton, isCapturing && styles.captureButtonDisabled]}
            onPress={capturePhoto}
            disabled={isCapturing}
          >
            {isCapturing ? (
              <ActivityIndicator size="small" color="#FFF" />
            ) : (
              <Text style={styles.buttonText}>Capture</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
};