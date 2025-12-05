// src/screens/ResultScreen.tsx

import React, {useState} from 'react';
import {View, Image, TouchableOpacity, Alert, ActivityIndicator, Text} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';

import {styles} from '../styles/ResultScreen.styles';
import {uploadBoardPhoto} from '../services/api';
import {normalizeFen} from '../utils/fen';
import {ScreenHeader} from '../components/ScreenHeader';
import {getBoardSize} from '../constants/layout';

const RESULT_TIPS = [
  'Confirm every square is visible edge to edge',
  'Retake if pieces look blurry or cut off',
];

// Import RootStackParamList from App.tsx
import type {RootStackParamList} from '../../App'; 

// Define the Props for this screen
type ResultScreenProps = NativeStackScreenProps<RootStackParamList, 'Result'>;

export const ResultScreen = ({route, navigation}: ResultScreenProps) => {
  // Use the 'route' object to access the parameter passed from ScanBoard
  const {photoPath} = route.params;
  const [isProcessing, setIsProcessing] = useState(false);
  const boardSize = getBoardSize();

  const onAccept = async () => {
    try {
      setIsProcessing(true);
      const fen = await uploadBoardPhoto(photoPath);
      const normalizedFen = normalizeFen(fen);
      navigation.navigate('Analysis', {fen: normalizedFen});
    } catch (error) {
      console.error('Upload failed', error);
      Alert.alert('Upload failed', error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setIsProcessing(false);
    }
  };

  const onRetake = () => {
    // Logic for RETAKE: Go back to the ScanBoard screen
    navigation.goBack(); 
  };
  
  // The 'photoPath' contains the local file path on the device (e.g., 'file:///data/...')

  return (
    <View style={styles.container}>
      <View style={styles.content}>
        <View style={styles.headerContainer}>
          <ScreenHeader
            title="Confirm Photo"
            onBack={() => navigation.goBack()}
          />
        </View>

        <View style={[styles.imageDisplayArea, {width: boardSize, height: boardSize}]}> 
          <Image 
            source={{ uri: `file://${photoPath}` }} 
            style={styles.image} 
          />
        </View>

        <View style={styles.tipsList}>
          {RESULT_TIPS.map((tip) => (
            <Text key={tip} style={styles.tipText}>
              {`• ${tip}`}
            </Text>
          ))}
        </View>

        <View style={styles.spacer} />

        <View style={styles.buttonRow}>
          <TouchableOpacity 
            style={[styles.button, styles.retakeButton]}
            onPress={onRetake}
            disabled={isProcessing}
          >
            <Text style={styles.buttonText}>❌</Text>
          </TouchableOpacity>
          
          <TouchableOpacity 
            style={[styles.button, styles.acceptButton]}
            onPress={onAccept}
            disabled={isProcessing}
          >
            {isProcessing ? (
              <ActivityIndicator size="small" color="#FFF" />
            ) : (
              <Text style={styles.buttonText}>✅</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>

      {isProcessing && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#FFF" />
          <Text style={styles.loadingText}>Analyzing board...</Text>
        </View>
      )}
    </View>
  );
};