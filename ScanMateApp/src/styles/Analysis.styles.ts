import { StyleSheet } from 'react-native';

export const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#121212', // Dark Theme
    alignItems: 'center',
  },
  scrollContent: {
    alignItems: 'center',
    paddingBottom: 32,
    width: '100%',
  },
  header: {
    marginTop: 20,
    marginBottom: 20,
    width: '100%',
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#ffffff',
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#aaaaaa',
    marginTop: 5,
  },
  boardWrapper: {
    borderWidth: 2,
    borderColor: '#333',
    borderRadius: 4,
    overflow: 'hidden',
    position: 'relative',
  },
  controlsContainer: {
    width: '100%',
    padding: 20,
    marginTop: 10,
  },
  controlRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
    backgroundColor: '#1e1e1e',
    padding: 15,
    borderRadius: 10,
  },
  label: {
    color: 'white',
    fontSize: 16,
    fontWeight: '600',
  },
  switchWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  switchLabel: {
    color: '#555',
    fontWeight: '600',
  },
  activeLabel: {
    color: 'white',
  },
  buttonRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
  },
  actionButton: {
    flex: 1,
    backgroundColor: '#333',
    padding: 15,
    borderRadius: 10,
    alignItems: 'center',
  },
  analyzeButton: {
    backgroundColor: '#27ae60', // Green
  },
  analyzeButtonDisabled: {
    opacity: 0.7,
  },
  buttonText: {
    color: 'white',
    fontWeight: 'bold',
  },
  analyzeText: {
    color: 'white',
  },
  // Modal Styles
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContent: {
    width: '90%',
    backgroundColor: '#2c2c2c',
    borderRadius: 15,
    padding: 20,
    alignItems: 'center',
  },
  modalTitle: {
    fontSize: 20,
    color: 'white',
    marginBottom: 20,
    fontWeight: 'bold',
  },
  gridContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 10,
  },
  gridItem: {
    width: 50,
    height: 50,
    backgroundColor: '#3e3e3e',
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 8,
  },
  pieceImage: {
    width: 32,
    height: 32,
    resizeMode: 'contain',
  },
  pieceIcon: {
    fontSize: 30,
    color: '#eee',
  },
  trashOption: {
    backgroundColor: '#c0392b',
    width: '100%',
    marginTop: 10,
    height: 40,
  },
  trashLabel: {
    color: 'white',
    fontWeight: 'bold',
  },
  boardOverlay: {
    ...StyleSheet.absoluteFillObject,
    flexDirection: 'column',
  },
  overlayRow: {
    flex: 1,
    flexDirection: 'row',
  },
  overlaySquare: {
    flex: 1,
  },
  arrowLayer: {
    ...StyleSheet.absoluteFillObject,
  },
  arrowWrapper: {
    position: 'absolute',
    left: 0,
    top: 0,
  },
  arrowBody: {
    position: 'absolute',
    left: 0,
    backgroundColor: '#ffb347',
    borderRadius: 999,
    opacity: 0.9,
  },
  arrowHead: {
    position: 'absolute',
    backgroundColor: '#ffb347',
    opacity: 0.9,
  },
  analysisCard: {
    marginTop: 16,
    backgroundColor: '#1f1f1f',
    padding: 16,
    borderRadius: 12,
  },
  analysisPlaceholder: {
    alignItems: 'center',
    paddingVertical: 12,
  },
  analysisLine: {
    marginBottom: 12,
  },
  analysisLineHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  analysisLineIndex: {
    color: '#bbbbbb',
    fontWeight: '600',
    width: 36,
  },
  analysisMove: {
    flex: 1,
    color: '#ffffff',
    fontWeight: '600',
    fontSize: 16,
  },
  analysisEval: {
    color: '#2ecc71',
    fontWeight: '700',
    minWidth: 60,
    textAlign: 'right',
  },
  analysisPv: {
    color: '#bbbbbb',
    fontSize: 13,
  },
  analysisErrorText: {
    color: '#ff7675',
    fontWeight: '600',
  },
  analysisInfoText: {
    color: '#ffffff',
    marginTop: 12,
    textAlign: 'center',
  },
  playbackControls: {
    marginTop: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  playbackButton: {
    backgroundColor: '#2d2d2d',
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 8,
  },
  playbackButtonDisabled: {
    opacity: 0.4,
  },
  playbackButtonText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 16,
  },
  playbackStatus: {
    marginTop: 8,
    color: '#bbbbbb',
    fontWeight: '600',
    textAlign: 'center',
  },
});