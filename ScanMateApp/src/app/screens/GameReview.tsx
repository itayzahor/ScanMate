import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  SafeAreaView,
  ScrollView,
  Text,
  TouchableOpacity,
  View,
  Alert,
} from 'react-native';
import Chessboard from 'react-native-chessboard';
import { Chess, Move } from 'chess.js';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';

import { styles } from '../../ui/styles/GameReview.styles';
import type { RootStackParamList } from '../../../App';
import { ScreenHeader } from '../../ui/components/ScreenHeader';
import { analyzePosition, AnalyzePositionResponse } from '../../services/api';
import type { GameSnapshot } from '../../shared/types/game';
import { getBoardSize } from '../../shared/constants/layout';
import { normalizeFen } from '../../shared/utils/fen';

const deriveMoveSan = (previous: string, next: string): string => {
  if (!previous) {
    return 'Start Position';
  }

  try {
    const chess = new Chess(previous);
    const moves = chess.moves({ verbose: true }) as Move[];
    for (const move of moves) {
      const cloned = new Chess(previous);
      const result = cloned.move({ from: move.from, to: move.to, promotion: move.promotion });
      if (result && normalizeFen(cloned.fen()) === normalizeFen(next)) {
        return result.san;
      }
    }
  } catch (error) {
    console.warn('[GameReview] Failed to derive SAN', error);
  }
  return '…';
};

type GameReviewProps = NativeStackScreenProps<RootStackParamList, 'GameReview'>;

type MovePair = {
  number: number;
  white: { san: string; index: number };
  black?: { san: string; index: number };
};

export const GameReview = ({ route, navigation }: GameReviewProps) => {
  const snapshots = route.params?.snapshots ?? [];
  const passedMoves = route.params?.moves;
  const boardSize = getBoardSize();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [analysisResult, setAnalysisResult] = useState<AnalyzePositionResponse | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  useEffect(() => {
    if (!snapshots.length) {
      Alert.alert('No Data', 'No frames were captured.');
      navigation.goBack();
    }
  }, [snapshots.length, navigation]);

  // Build SAN labels — use passed moves if available, otherwise derive from FENs
  const moveLabels = useMemo<string[]>(() => {
    if (passedMoves && passedMoves.length === snapshots.length - 1) {
      return passedMoves;
    }
    return snapshots.slice(1).map((snap, i) => deriveMoveSan(snapshots[i].fen, snap.fen));
  }, [snapshots, passedMoves]);

  // Group moves into pairs (1. e4 e5, 2. Nf3 Nc6, …)
  const movePairs = useMemo<MovePair[]>(() => {
    const pairs: MovePair[] = [];
    for (let i = 0; i < moveLabels.length; i += 2) {
      pairs.push({
        number: Math.floor(i / 2) + 1,
        white: { san: moveLabels[i], index: i + 1 },
        black: i + 1 < moveLabels.length
          ? { san: moveLabels[i + 1], index: i + 2 }
          : undefined,
      });
    }
    return pairs;
  }, [moveLabels]);

  const currentFen = snapshots[currentIndex]?.fen;
  const totalMoves = snapshots.length - 1;

  const goTo = useCallback((idx: number) => {
    setCurrentIndex(idx);
    setAnalysisResult(null);
    setAnalysisError(null);
  }, []);

  const handleAnalyze = async () => {
    if (!currentFen) {
      return;
    }

    try {
      setIsAnalyzing(true);
      setAnalysisError(null);
      const response = await analyzePosition(currentFen, { depth: 16, multipv: 1 });
      setAnalysisResult(response);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to run engine analysis.';
      setAnalysisError(message);
      Alert.alert('Analysis failed', message);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScreenHeader
        title="Game Review"
        subtitle={`${totalMoves} move${totalMoves !== 1 ? 's' : ''} detected`}
        onBack={() => navigation.goBack()}
        style={styles.header}
      />

      {/* Board */}
      {currentFen && (
        <View style={[styles.boardWrapper, { width: boardSize, height: boardSize }]}>
          <Chessboard fen={currentFen} boardSize={boardSize} />
        </View>
      )}

      {/* Navigation arrows */}
      <View style={styles.navRow}>
        <TouchableOpacity
          style={[styles.navButton, currentIndex === 0 && styles.navButtonDisabled]}
          disabled={currentIndex === 0}
          onPress={() => goTo(0)}
        >
          <Text style={styles.navButtonText}>{'|◁'}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.navButton, currentIndex === 0 && styles.navButtonDisabled]}
          disabled={currentIndex === 0}
          onPress={() => goTo(currentIndex - 1)}
        >
          <Text style={styles.navButtonText}>{'◁'}</Text>
        </TouchableOpacity>

        <Text style={styles.navLabel}>
          {currentIndex === 0 ? 'Start' : `Move ${currentIndex}/${totalMoves}`}
        </Text>

        <TouchableOpacity
          style={[styles.navButton, currentIndex >= snapshots.length - 1 && styles.navButtonDisabled]}
          disabled={currentIndex >= snapshots.length - 1}
          onPress={() => goTo(currentIndex + 1)}
        >
          <Text style={styles.navButtonText}>{'▷'}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.navButton, currentIndex >= snapshots.length - 1 && styles.navButtonDisabled]}
          disabled={currentIndex >= snapshots.length - 1}
          onPress={() => goTo(snapshots.length - 1)}
        >
          <Text style={styles.navButtonText}>{'▷|'}</Text>
        </TouchableOpacity>
      </View>

      {/* Move list */}
      <ScrollView style={styles.moveListScroll} contentContainerStyle={styles.moveListContent}>
        {movePairs.map((pair) => (
          <View key={pair.number} style={styles.moveRow}>
            <Text style={styles.moveNumber}>{pair.number}.</Text>
            <TouchableOpacity
              style={[
                styles.moveCell,
                currentIndex === pair.white.index && styles.moveCellActive,
              ]}
              onPress={() => goTo(pair.white.index)}
            >
              <Text
                style={[
                  styles.moveSan,
                  currentIndex === pair.white.index && styles.moveSanActive,
                ]}
              >
                {pair.white.san}
              </Text>
            </TouchableOpacity>
            {pair.black ? (
              <TouchableOpacity
                style={[
                  styles.moveCell,
                  currentIndex === pair.black.index && styles.moveCellActive,
                ]}
                onPress={() => goTo(pair.black.index)}
              >
                <Text
                  style={[
                    styles.moveSan,
                    currentIndex === pair.black.index && styles.moveSanActive,
                  ]}
                >
                  {pair.black.san}
                </Text>
              </TouchableOpacity>
            ) : (
              <View style={styles.moveCell} />
            )}
          </View>
        ))}
      </ScrollView>

      {/* Analysis */}
      <View style={styles.analysisSection}>
        <TouchableOpacity
          style={[styles.analyzeButton, (!currentFen || isAnalyzing) && styles.analyzeButtonDisabled]}
          disabled={!currentFen || isAnalyzing}
          onPress={handleAnalyze}
        >
          {isAnalyzing ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.analyzeButtonText}>Analyze Position</Text>
          )}
        </TouchableOpacity>

        {analysisResult && (
          <View style={styles.analysisCard}>
            <Text style={styles.analysisTitle}>Best Move</Text>
            <Text style={styles.analysisMove}>{analysisResult.lines[0]?.best_move_san ?? '—'}</Text>
            <Text style={styles.analysisEval}>
              {analysisResult.lines[0]?.evaluation?.value ?? '—'} {analysisResult.lines[0]?.evaluation?.type ?? ''}
            </Text>
          </View>
        )}

        {analysisError && <Text style={styles.analysisError}>{analysisError}</Text>}
      </View>
    </SafeAreaView>
  );
};
