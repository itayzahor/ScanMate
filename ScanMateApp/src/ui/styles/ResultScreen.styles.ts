// src/styles/ResultScreen.styles.ts
import {StyleSheet} from 'react-native';
import {colors} from '../theme';

const BOARD_MARGIN = 16;

export const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundDark, 
  },
  content: {
    flex: 1,
    paddingHorizontal: BOARD_MARGIN,
    paddingBottom: 20,
  },
  headerContainer: {
    paddingTop: 20,
    width: '100%',
    marginBottom: 20,
  },
  imageDisplayArea: {
    marginTop: 0,
    alignSelf: 'center',
    borderWidth: 3,
    borderColor: colors.secondary,
    borderRadius: 6,
    overflow: 'hidden',
  },
  tipsList: {
    width: '100%',
    marginTop: 16,
    gap: 6,
  },
  tipText: {
    color: '#b5b5b5',
    fontSize: 14,
    lineHeight: 20,
  },
  image: {
    width: '100%', 
    height: '100%',
    // We use cover because the image is already cropped to 1:1 by ImageResizer
    resizeMode: 'cover', 
  },
  spacer: {
    flex: 1,
  },
  buttonRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    width: '100%',
    paddingTop: 24,
  },
  
  // Styles for the V/X Buttons
  button: {
    width: 80,
    height: 80,
    borderRadius: 40,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 5,
    borderColor: colors.textLight,
  },
  buttonText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: colors.text, // Black text for contrast
  },
  // We use the same color logic as ScanBoard for consistency
  retakeButton: {
    backgroundColor: colors.background, // White background for Retake (X)
  },
  acceptButton: {
    backgroundColor: colors.primary, // Red background for Accept (V)
  },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 12,
    color: colors.textLight,
    fontSize: 16,
  },
});