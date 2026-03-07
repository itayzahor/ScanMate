import { StyleSheet } from 'react-native';
import { colors } from '../theme';

export const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundDark,
    paddingHorizontal: 16,
  },
  header: {
    marginBottom: 12,
  },
  boardWrapper: {
    alignSelf: 'center',
    borderWidth: 2,
    borderColor: colors.secondary,
    borderRadius: 8,
    overflow: 'hidden',
    marginBottom: 20,
  },
  timelineHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  timelineTitle: {
    color: colors.textLight,
    fontSize: 18,
    fontWeight: '600',
  },
  timelineCount: {
    color: '#b5b5b5',
  },
  timelineList: {
    paddingVertical: 12,
  },
  timelineItem: {
    backgroundColor: '#1f1f1f',
    borderRadius: 8,
    padding: 12,
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  timelineItemActive: {
    borderWidth: 1,
    borderColor: colors.secondary,
  },
  timelineIndex: {
    width: 30,
    color: colors.textLight,
    fontWeight: '700',
  },
  timelineTextGroup: {
    flex: 1,
  },
  timelineLabel: {
    color: colors.textLight,
    fontSize: 16,
  },
  timelineLabelActive: {
    color: colors.secondary,
  },
  timelineFen: {
    color: '#9c9c9c',
    fontSize: 12,
  },
  timelineTime: {
    color: '#9c9c9c',
    fontSize: 12,
    marginLeft: 8,
  },
  analysisSection: {
    paddingVertical: 16,
  },
  analyzeButton: {
    backgroundColor: colors.primary,
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginBottom: 12,
  },
  analyzeButtonDisabled: {
    opacity: 0.6,
  },
  analyzeButtonText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 16,
  },
  analysisCard: {
    backgroundColor: '#1f1f1f',
    borderRadius: 8,
    padding: 16,
    gap: 6,
  },
  analysisTitle: {
    color: '#b5b5b5',
    textTransform: 'uppercase',
    fontSize: 12,
  },
  analysisMove: {
    color: colors.textLight,
    fontSize: 20,
    fontWeight: '600',
  },
  analysisEval: {
    color: colors.secondary,
    fontSize: 16,
  },
  analysisError: {
    color: '#e74c3c',
    marginTop: 8,
  },
});
