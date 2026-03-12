import { StyleSheet } from 'react-native';
import { colors } from '../theme';

export const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundDark,
    paddingHorizontal: 16,
  },
  header: {
    marginBottom: 8,
  },
  boardWrapper: {
    alignSelf: 'center',
    borderWidth: 2,
    borderColor: colors.secondary,
    borderRadius: 8,
    overflow: 'hidden',
    marginBottom: 12,
  },

  /* Navigation row */
  navRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    marginBottom: 12,
  },
  navButton: {
    width: 40,
    height: 36,
    borderRadius: 6,
    backgroundColor: '#1f1f1f',
    alignItems: 'center',
    justifyContent: 'center',
  },
  navButtonDisabled: {
    opacity: 0.3,
  },
  navButtonText: {
    color: colors.textLight,
    fontSize: 16,
    fontWeight: '700',
  },
  navLabel: {
    color: '#b5b5b5',
    fontSize: 14,
    minWidth: 90,
    textAlign: 'center',
  },

  /* Move list */
  moveListScroll: {
    flex: 1,
    marginBottom: 8,
  },
  moveListContent: {
    paddingBottom: 8,
  },
  moveRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 2,
  },
  moveNumber: {
    width: 32,
    color: '#777',
    fontSize: 14,
    textAlign: 'right',
    marginRight: 6,
  },
  moveCell: {
    flex: 1,
    paddingVertical: 6,
    paddingHorizontal: 8,
    borderRadius: 4,
  },
  moveCellActive: {
    backgroundColor: colors.secondary,
  },
  moveSan: {
    color: colors.textLight,
    fontSize: 15,
    fontWeight: '500',
  },
  moveSanActive: {
    color: colors.backgroundDark,
    fontWeight: '700',
  },

  /* Analysis */
  analysisSection: {
    paddingVertical: 12,
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
