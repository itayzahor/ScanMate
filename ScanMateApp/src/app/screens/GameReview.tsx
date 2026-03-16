import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  ImageSourcePropType,
  SafeAreaView,
  Text,
  TouchableOpacity,
  View,
  Alert,
} from 'react-native';
import Chessboard, { ChessboardRef } from 'react-native-chessboard';
import { Chess, Move, Square, PieceSymbol, Color } from 'chess.js';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';

import { styles } from '../../ui/styles/GameReview.styles';
import type { RootStackParamList } from '../../../App';
import { ScreenHeader } from '../../ui/components/ScreenHeader';
import { BestMoveArrow } from '../../ui/components/BestMoveArrow';
import { FlipToggle } from '../../ui/components/FlipToggle';
import { MoveStrip } from '../../ui/components/MoveStrip';
import { GameNavRow } from '../../ui/components/GameNavRow';
import { AnalysisPanel } from '../../ui/components/AnalysisPanel';
import { analyzePosition, AnalyzePositionResponse } from '../../services/api';
import { getBoardSize } from '../../shared/constants/layout';
import { normalizeFen } from '../../shared/utils/fen';

/* ── piece assets (same as Analysis) ── */

const PIECE_ASSETS: Record<`${Color}${PieceSymbol}`, ImageSourcePropType> = {
  wp: require('react-native-chessboard/src/assets/wp.png'),
  wn: require('react-native-chessboard/src/assets/wn.png'),
  wb: require('react-native-chessboard/src/assets/wb.png'),
  wr: require('react-native-chessboard/src/assets/wr.png'),
  wq: require('react-native-chessboard/src/assets/wq.png'),
  wk: require('react-native-chessboard/src/assets/wk.png'),
  bp: require('react-native-chessboard/src/assets/bp.png'),
  bn: require('react-native-chessboard/src/assets/bn.png'),
  bb: require('react-native-chessboard/src/assets/bb.png'),
  br: require('react-native-chessboard/src/assets/br.png'),
  bq: require('react-native-chessboard/src/assets/bq.png'),
  bk: require('react-native-chessboard/src/assets/bk.png'),
};

/* ── helpers ── */

const deriveMoveSan = (previous: string, next: string): string => {
  if (!previous) { return 'Start Position'; }
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

/* ── types ── */

type GameReviewProps = NativeStackScreenProps<RootStackParamList, 'GameReview'>;

/* ── component ── */

export const GameReview = ({ route, navigation }: GameReviewProps) => {
  const rawSnapshots = route.params?.snapshots;
  const snapshots = useMemo(() => rawSnapshots ?? [], [rawSnapshots]);
  const passedMoves = route.params?.moves;
  const boardSize = getBoardSize();

  // Game navigation
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isBoardFlipped, setIsBoardFlipped] = useState(false);

  // Analysis state
  const [analysisResult, setAnalysisResult] = useState<AnalyzePositionResponse | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisMode, setAnalysisMode] = useState(false);
  const [analysisBaseFen, setAnalysisBaseFen] = useState<string | null>(null);
  const [analysisBaseIndex, setAnalysisBaseIndex] = useState(0);
  const [pvIndex, setPvIndex] = useState(0);
  const [displayFen, setDisplayFen] = useState<string | null>(null);

  const chessboardRef = useRef<ChessboardRef>(null);

  useEffect(() => {
    if (!snapshots.length) {
      Alert.alert('No Data', 'No frames were captured.');
      navigation.goBack();
    }
  }, [snapshots.length, navigation]);

  // Build SAN labels
  const moveLabels = useMemo<string[]>(() => {
    if (passedMoves && passedMoves.length === snapshots.length - 1) {
      return passedMoves;
    }
    return snapshots.slice(1).map((snap, i) => deriveMoveSan(snapshots[i].fen, snap.fen));
  }, [snapshots, passedMoves]);

  // Get SAN label for a given snapshot index (1-based move index)
  const getMoveLabel = useCallback((moveIdx: number): string => {
    if (moveIdx <= 0 || moveIdx > moveLabels.length) { return ''; }
    return moveLabels[moveIdx - 1];
  }, [moveLabels]);

  const gameFen = snapshots[currentIndex]?.fen;
  const currentFen = displayFen ?? gameFen;
  const totalMoves = snapshots.length - 1;

  // PV playback data
  const primaryLine = analysisResult?.lines?.[0];

  const playbackData = useMemo(() => {
    if (!analysisBaseFen || !primaryLine) { return null; }
    const pvMoves = primaryLine.pv ?? [];
    const chess = new Chess(analysisBaseFen);
    const states: string[] = [analysisBaseFen];
    const moves: Array<{ from: Square; to: Square; san: string }> = [];

    for (const san of pvMoves) {
      try {
        const move = chess.move(san);
        if (!move) { break; }
        moves.push({ from: move.from as Square, to: move.to as Square, san });
        states.push(chess.fen());
      } catch {
        break;
      }
    }
    return { states, moves };
  }, [analysisBaseFen, primaryLine]);

  const playbackMoveCount = playbackData?.moves.length ?? 0;
  const canStepForward = playbackMoveCount > 0 && pvIndex < playbackMoveCount;
  const canStepBackward = playbackMoveCount > 0 && pvIndex > 0;

  // Arrow for upcoming PV move
  const upcomingMove = playbackData && pvIndex < playbackData.moves.length
    ? playbackData.moves[pvIndex]
    : null;
  const fallbackBestMove = useMemo(() => {
    const move = primaryLine?.best_move;
    if (!move || move.length < 4) { return { from: null, to: null }; }
    return { from: move.slice(0, 2) as Square, to: move.slice(2, 4) as Square };
  }, [primaryLine]);

  const arrowFrom = analysisMode ? (upcomingMove?.from ?? fallbackBestMove.from) : null;
  const arrowTo = analysisMode ? (upcomingMove?.to ?? fallbackBestMove.to) : null;

  // Navigation — animates pieces via resetBoard
  const goTo = useCallback((idx: number) => {
    const targetFen = snapshots[idx]?.fen;
    setCurrentIndex(idx);
    // Exit analysis mode when navigating game moves
    setAnalysisMode(false);
    setAnalysisResult(null);
    setAnalysisError(null);
    setAnalysisBaseFen(null);
    setDisplayFen(null);
    setPvIndex(0);
    if (targetFen) {
      chessboardRef.current?.resetBoard(targetFen);
    }
  }, [snapshots]);

  // PV stepping — also animates
  const stepToIndex = useCallback((targetIndex: number) => {
    if (!playbackData) { return; }
    const maxIndex = playbackData.states.length - 1;
    const nextIndex = Math.min(Math.max(targetIndex, 0), maxIndex);
    if (nextIndex === pvIndex) { return; }
    const nextFen = playbackData.states[nextIndex];
    setDisplayFen(nextFen);
    setPvIndex(nextIndex);
    chessboardRef.current?.resetBoard(nextFen);
  }, [playbackData, pvIndex]);

  const handlePlaybackForward = useCallback(() => stepToIndex(pvIndex + 1), [pvIndex, stepToIndex]);
  const handlePlaybackBackward = useCallback(() => stepToIndex(pvIndex - 1), [pvIndex, stepToIndex]);
  const handlePlaybackReset = useCallback(() => stepToIndex(0), [stepToIndex]);

  // Analyze current position → enter analysis mode
  const handleAnalyze = useCallback(async () => {
    if (!gameFen) { return; }
    try {
      setIsAnalyzing(true);
      setAnalysisError(null);
      const response = await analyzePosition(gameFen, { depth: 18, multipv: 1 });
      setAnalysisResult(response);
      setAnalysisBaseFen(gameFen);
      setAnalysisBaseIndex(currentIndex);
      setAnalysisMode(true);
      setPvIndex(0);
      setDisplayFen(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to run engine analysis.';
      setAnalysisError(message);
      Alert.alert('Analysis failed', message);
    } finally {
      setIsAnalyzing(false);
    }
  }, [gameFen, currentIndex]);

  // Return to game from analysis mode
  const handleReturnToGame = useCallback(() => {
    setAnalysisMode(false);
    setAnalysisResult(null);
    setAnalysisError(null);
    setAnalysisBaseFen(null);
    setDisplayFen(null);
    setPvIndex(0);
    // Restore the game position on the board
    if (gameFen) {
      chessboardRef.current?.resetBoard(gameFen);
    }
  }, [gameFen]);

  // Flip board (pieces stay upright via renderPiece counter-rotation)
  const boardTransformStyle = useMemo(
    () => ({ transform: [{ rotate: isBoardFlipped ? '180deg' : '0deg' }] }),
    [isBoardFlipped],
  );

  const renderChessPiece = useCallback(
    (piece: `${string}${PieceSymbol}`) => {
      const assetKey = (piece as keyof typeof PIECE_ASSETS) ?? 'wp';
      const source = PIECE_ASSETS[assetKey] ?? PIECE_ASSETS.wp;
      return (
        <Image
          source={source}
          style={{
            width: boardSize / 8,
            height: boardSize / 8,
            transform: [{ rotate: isBoardFlipped ? '180deg' : '0deg' }],
          }}
          resizeMode="contain"
        />
      );
    },
    [boardSize, isBoardFlipped],
  );

  // 3-move strip: prev / current / next
  const prevLabel = currentIndex >= 2 ? getMoveLabel(currentIndex - 1) : null;
  const currLabel = currentIndex >= 1 ? getMoveLabel(currentIndex) : null;
  const nextLabel = currentIndex < totalMoves ? getMoveLabel(currentIndex + 1) : null;

  return (
    <SafeAreaView style={styles.container}>
      <ScreenHeader
        title="Game Review"
        subtitle={
          analysisMode
            ? `Analyzing move ${analysisBaseIndex}/${totalMoves}`
            : `${totalMoves} move${totalMoves !== 1 ? 's' : ''} detected`
        }
        onBack={() => navigation.goBack()}
        style={styles.header}
      />

      {/* Board */}
      {currentFen && (
        <View style={[styles.boardWrapper, { width: boardSize, height: boardSize }, boardTransformStyle]}>
          <Chessboard
            ref={chessboardRef}
            fen={currentFen}
            boardSize={boardSize}
            renderPiece={renderChessPiece}
          />
          <BestMoveArrow from={arrowFrom} to={arrowTo} boardSize={boardSize} />
        </View>
      )}

      {/* Toolbar: flip toggle + analyze/return */}
      <View style={styles.toolbarRow}>
        <FlipToggle isFlipped={isBoardFlipped} onChange={setIsBoardFlipped} />

        {analysisMode ? (
          <TouchableOpacity style={[styles.toolbarButton, styles.returnButton]} onPress={handleReturnToGame}>
            <Text style={styles.toolbarButtonText}>↩ Back to Game</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity
            style={[styles.toolbarButton, styles.analyzeToolbarButton, (!gameFen || isAnalyzing) && styles.analyzeButtonDisabled]}
            disabled={!gameFen || isAnalyzing}
            onPress={handleAnalyze}
          >
            {isAnalyzing ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.toolbarButtonText}>🚀 Analyze</Text>
            )}
          </TouchableOpacity>
        )}
      </View>

      {/* Analysis PV panel (shown in analysis mode) */}
      {analysisMode && primaryLine && (
        <AnalysisPanel
          primaryLine={primaryLine}
          pvIndex={pvIndex}
          playbackMoveCount={playbackMoveCount}
          canStepForward={canStepForward}
          canStepBackward={canStepBackward}
          onForward={handlePlaybackForward}
          onBackward={handlePlaybackBackward}
          onReset={handlePlaybackReset}
        />
      )}

      {analysisError && <Text style={styles.analysisError}>{analysisError}</Text>}

      {/* Move strip: prev ◁  ·  current  ·  ▷ next */}
      {!analysisMode && (
        <MoveStrip
          prevLabel={prevLabel}
          currLabel={currLabel}
          nextLabel={nextLabel}
          currentIndex={currentIndex}
          totalMoves={totalMoves}
          onGoTo={goTo}
        />
      )}

      {/* Navigation arrows (game mode) */}
      {!analysisMode && (
        <GameNavRow
          currentIndex={currentIndex}
          totalMoves={snapshots.length - 1}
          onGoTo={goTo}
        />
      )}
    </SafeAreaView>
  );
};
