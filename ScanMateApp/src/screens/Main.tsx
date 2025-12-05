// src/screens/Main.tsx
import React from 'react';
import {View, Text, TouchableOpacity, StyleSheet} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import type {RootStackParamList} from '../../App';
import {STARTING_FEN} from '../utils/fen';

// This component receives a 'navigation' prop from the navigator
// Define the prop types for this screen
type Props = NativeStackScreenProps<RootStackParamList, 'Main'>;

export const Main = ({navigation}: Props) => {

  const onScanPress = () => {
    // This tells the navigator to go to the "ScanBoard" screen
    navigation.navigate('ScanBoard');
  };

  const onAnalysisPress = () => {
    navigation.navigate('Analysis', {fen: STARTING_FEN});
  };

  return (
    <View style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.appName}>ScanMate</Text>
        <Text style={styles.subtitle}>Computer vision tools for chess training</Text>

        <TouchableOpacity style={styles.primaryButton} onPress={onScanPress} activeOpacity={0.85}>
          <View style={styles.buttonIconContainer}>
            <Text style={styles.buttonIcon}>📷</Text>
          </View>
          <View style={styles.buttonTextWrapper}>
            <Text style={styles.buttonTitle}>Scan Chessboard</Text>
            <Text style={styles.buttonSubtitle}>Capture a board and get instant recognition</Text>
          </View>
        </TouchableOpacity>

        <TouchableOpacity style={styles.secondaryButton} onPress={onAnalysisPress} activeOpacity={0.85}>
          <View style={styles.buttonIconContainer}>
            <Text style={styles.buttonIcon}>♘</Text>
          </View>
          <View style={styles.buttonTextWrapper}>
            <Text style={styles.buttonTitle}>Open Analysis</Text>
            <Text style={styles.buttonSubtitle}>Edit positions and run engine evaluations</Text>
          </View>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0c111d',
    paddingHorizontal: 24,
    paddingTop: 72,
    paddingBottom: 40,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
  },
  appName: {
    color: '#f5f7ff',
    fontSize: 40,
    fontWeight: '800',
    textAlign: 'center',
    marginBottom: 8,
  },
  subtitle: {
    color: '#91a0c7',
    textAlign: 'center',
    fontSize: 16,
    marginBottom: 48,
  },
  primaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 20,
    borderRadius: 20,
    backgroundColor: '#1c2b4b',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    marginBottom: 16,
  },
  secondaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 20,
    borderRadius: 20,
    backgroundColor: '#141b2d',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.04)',
  },
  buttonIconContainer: {
    width: 56,
    height: 56,
    borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.08)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  buttonIcon: {
    fontSize: 26,
  },
  buttonTextWrapper: {
    flex: 1,
  },
  buttonTitle: {
    color: '#f5f7ff',
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 4,
  },
  buttonSubtitle: {
    color: '#8b98c7',
    fontSize: 14,
  },
});