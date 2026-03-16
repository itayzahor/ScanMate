import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { colors } from '../theme';
import type { AnalysisLine } from '../../services/api';

const formatEvaluation = (evaluation: AnalysisLine['evaluation']) => {
  if (!evaluation) { return '—'; }
  if (evaluation.type === 'mate' && typeof evaluation.value === 'number') {
    return `#${evaluation.value}`;
  }
  if (evaluation.type === 'cp' && typeof evaluation.value === 'number') {
    const score = evaluation.value / 100;
    return `${score >= 0 ? '+' : ''}${score.toFixed(2)}`;
  }
  return '—';
};

type AnalysisPanelProps = {
  primaryLine: AnalysisLine;
  pvIndex: number;
  playbackMoveCount: number;
  canStepForward: boolean;
  canStepBackward: boolean;
  onForward: () => void;
  onBackward: () => void;
  onReset: () => void;
};

export const AnalysisPanel: React.FC<AnalysisPanelProps> = ({
  primaryLine, pvIndex, playbackMoveCount,
  canStepForward, canStepBackward,
  onForward, onBackward, onReset,
}) => (
  <View style={panelStyles.card}>
    <View style={panelStyles.lineHeader}>
      <Text style={panelStyles.move}>{primaryLine.best_move_san || primaryLine.best_move}</Text>
      <Text style={panelStyles.eval}>{formatEvaluation(primaryLine.evaluation)}</Text>
    </View>
    <Text style={panelStyles.pv} numberOfLines={2}>
      {primaryLine.pv.join(' ')}
    </Text>

    {playbackMoveCount > 0 && (
      <View style={panelStyles.playbackControls}>
        <TouchableOpacity
          style={[panelStyles.playbackButton, !canStepBackward && panelStyles.playbackDisabled]}
          disabled={!canStepBackward}
          onPress={onBackward}
        >
          <Text style={panelStyles.playbackText}>◀</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[panelStyles.playbackButton, pvIndex === 0 && panelStyles.playbackDisabled]}
          disabled={pvIndex === 0}
          onPress={onReset}
        >
          <Text style={panelStyles.playbackText}>⟲</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[panelStyles.playbackButton, !canStepForward && panelStyles.playbackDisabled]}
          disabled={!canStepForward}
          onPress={onForward}
        >
          <Text style={panelStyles.playbackText}>▶</Text>
        </TouchableOpacity>
        <Text style={panelStyles.playbackStatus}>
          {pvIndex} / {playbackMoveCount}
        </Text>
      </View>
    )}
  </View>
);

const panelStyles = StyleSheet.create({
  card: {
    backgroundColor: '#1f1f1f',
    borderRadius: 8,
    padding: 16,
    marginBottom: 8,
  },
  lineHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  move: {
    color: colors.textLight,
    fontSize: 20,
    fontWeight: '600',
  },
  eval: {
    color: colors.secondary,
    fontSize: 16,
    fontWeight: '700',
  },
  pv: {
    color: '#bbbbbb',
    fontSize: 13,
    marginBottom: 4,
  },
  playbackControls: {
    marginTop: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  playbackButton: {
    backgroundColor: '#2d2d2d',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 8,
  },
  playbackDisabled: {
    opacity: 0.4,
  },
  playbackText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 16,
  },
  playbackStatus: {
    color: '#bbbbbb',
    fontWeight: '600',
    marginLeft: 'auto',
  },
});
