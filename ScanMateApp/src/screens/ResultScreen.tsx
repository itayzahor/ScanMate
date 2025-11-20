// src/screens/ResultScreen.tsx

import React, {useState} from 'react';
import {View, Text, Image, TouchableOpacity, Alert, ActivityIndicator} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';

import {styles} from '../styles/ResultScreen.styles';
import {uploadBoardPhoto} from '../services/api';

// Import RootStackParamList from App.tsx
import type {RootStackParamList} from '../../App'; 

// Define the Props for this screen
type ResultScreenProps = NativeStackScreenProps<RootStackParamList, 'Result'>;

export const ResultScreen = ({route, navigation}: ResultScreenProps) => {
  // Use the 'route' object to access the parameter passed from ScanBoard
  const {photoPath} = route.params;
  const [isProcessing, setIsProcessing] = useState(false);

  const onAccept = async () => {
    try {
      setIsProcessing(true);
      const fen = await uploadBoardPhoto(photoPath);
      navigation.navigate('Analysis', {fen});
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
      
      {/* 1. IMAGE DISPLAY AREA (Aligned to 80% square) */}
      <View style={styles.imageDisplayArea}>
        <Image 
          source={{ uri: `file://${photoPath}` }} 
          style={styles.image} 
        />
      </View>
      
      {/* 2. CONFIRMATION OVERLAY (Text and Buttons) */}
      <View style={styles.confirmationOverlay}>
        
        {/* Top Text Instruction Box */}
        <View style={styles.instructionBox}>
          <Text style={styles.instructionText}>
            Is the photo clear and is the entire chessboard visible?
          </Text>
        </View>

        {/* Spacer to push buttons to the bottom */}
        <View style={styles.spacer} /> 
        
        {/* Button Row */}
        <View style={styles.buttonRow}>
          {/* Retake Button (X) */}
          <TouchableOpacity 
            style={[styles.button, styles.retakeButton]}
            onPress={onRetake}
            disabled={isProcessing}
          >
            <Text style={styles.buttonText}>❌</Text>
          </TouchableOpacity>
          
          {/* Accept Button (V) */}
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