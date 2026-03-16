// src/screens/Main.tsx
import React from 'react';
import {View, Text, TouchableOpacity, StyleSheet} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import type {RootStackParamList} from '../../../App';
import {STARTING_FEN} from '../../shared/utils/fen';
import {Chess} from 'chess.js';
import type {GameSnapshot} from '../../shared/types/game';

// Bobby Fischer vs Donald Byrne, 1956 — "Game of the Century"
const FISCHER_GAME_SAN = [
  'Nf3','Nf6','c4','g6','Nc3','Bg7','d4','O-O','Bf4','d5',
  'Qb3','dxc4','Qxc4','c6','e4','Nbd7','Rd1','Nb6','Qc5','Bg4',
  'Bg5','Na4','Qa3','Nxc3','bxc3','Nxe4','Bxe7','Qb6','Bc4','Nxc3',
  'Bc5','Rfe8+','Kf1','Be6','Bxb6','Bxc4+','Kg1','Ne2+','Kf1','Nxd4+',
  'Kg1','Ne2+','Kf1','Nc3+','Kg1','axb6','Qb4','Ra4','Qxb6','Nxd1',
  'h3','Rxa2','Kh2','Nxf2','Re1','Rxe1','Qd8+','Bf8','Nxe1','Bd5',
  'Nf3','Ne4','Qb8','b5','h4','h5','Ne5','Kg7','Kg1','Bc5+',
  'Kf1','Ng3+','Ke1','Bb4+','Kd1','Bb3+','Kc1','Ne2+','Kb1','Nc3+',
  'Kc1','Rc2#',
];

const sanMovesToSnapshots = (sanMoves: string[]): { snapshots: GameSnapshot[]; moves: string[] } => {
  const chess = new Chess();
  const snapshots: GameSnapshot[] = [{ fen: chess.fen(), timestamp: 0 }];
  const validMoves: string[] = [];

  for (const san of sanMoves) {
    const result = chess.move(san);
    if (!result) { break; }
    validMoves.push(result.san);
    snapshots.push({ fen: chess.fen(), timestamp: snapshots.length });
  }

  return { snapshots, moves: validMoves };
};

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

  const onRecordGamePress = () => {
    navigation.navigate('ScanGame');
  };

  const onFamousGamePress = () => {
    const { snapshots, moves } = sanMovesToSnapshots(FISCHER_GAME_SAN);
    navigation.navigate('GameReview', { snapshots, moves });
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

        <TouchableOpacity style={styles.secondaryButton} onPress={onRecordGamePress} activeOpacity={0.85}>
          <View style={styles.buttonIconContainer}>
            <Text style={styles.buttonIcon}>🎥</Text>
          </View>
          <View style={styles.buttonTextWrapper}>
            <Text style={styles.buttonTitle}>Record Full Game</Text>
            <Text style={styles.buttonSubtitle}>Hands-free capture with automatic move timeline</Text>
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

        <TouchableOpacity style={[styles.secondaryButton, { marginTop: 16 }]} onPress={onFamousGamePress} activeOpacity={0.85}>
          <View style={styles.buttonIconContainer}>
            <Text style={styles.buttonIcon}>🏆</Text>
          </View>
          <View style={styles.buttonTextWrapper}>
            <Text style={styles.buttonTitle}>Famous Game</Text>
            <Text style={styles.buttonSubtitle}>Fischer vs Byrne 1956 — Game of the Century</Text>
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