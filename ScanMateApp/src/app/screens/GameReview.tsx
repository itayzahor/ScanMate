import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  SafeAreaView,
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

type TimelineEntry = GameSnapshot & {
  label: string;
};

export const GameReview = ({ route, navigation }: GameReviewProps) => {
  const snapshots = route.params?.snapshots ?? [];
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

  const timeline = useMemo<TimelineEntry[]>(() => {
    return snapshots.map((snapshot, index) => ({
      ...snapshot,
      label: index === 0 ? 'Start' : deriveMoveSan(snapshots[index - 1].fen, snapshot.fen),
    }));
  }, [snapshots]);

  const currentSnapshot = timeline[currentIndex];
  const currentFen = currentSnapshot ? currentSnapshot.fen : undefined;

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

  const renderTimelineItem = ({ item, index }: { item: TimelineEntry; index: number }) => {
    const isActive = index === currentIndex;
    return (
      <TouchableOpacity
        style={[styles.timelineItem, isActive && styles.timelineItemActive]}
        onPress={() => {
          setCurrentIndex(index);
          setAnalysisResult(null);
        }}
      >
        <Text style={styles.timelineIndex}>{index}</Text>
        <View style={styles.timelineTextGroup}>
          <Text style={[styles.timelineLabel, isActive && styles.timelineLabelActive]}>{item.label}</Text>
          <Text style={styles.timelineFen}>{item.fen.split(' ')[0]}</Text>
        </View>
        <Text style={styles.timelineTime}>{new Date(item.timestamp).toLocaleTimeString()}</Text>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScreenHeader
        title="Game Review"
        subtitle="Tap a move to inspect it, then run analysis"
        onBack={() => navigation.goBack()}
        style={styles.header}
      />

      {currentFen && (
        <View style={[styles.boardWrapper, { width: boardSize, height: boardSize }]}> 
          <Chessboard fen={currentFen} boardSize={boardSize} />
        </View>
      )}

      <View style={styles.timelineHeader}>
        <Text style={styles.timelineTitle}>Captured Moves</Text>
        <Text style={styles.timelineCount}>{timeline.length} positions</Text>
      </View>

      <FlatList
        data={timeline}
        keyExtractor={(item, index) => `${item.timestamp}-${index}`}
        renderItem={renderTimelineItem}
        contentContainerStyle={styles.timelineList}
      />

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
