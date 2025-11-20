// src/styles/ResultScreen.styles.ts
import {StyleSheet, Dimensions} from 'react-native';
import {colors} from '../theme';

const {width} = Dimensions.get('window');
const IMAGE_DISPLAY_SIZE = width * 0.8; // Match the 80% viewfinder size

export const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundDark, 
    // Do NOT center content here; we will use specific containers
  },
  
  // ----------------------------------------------------
  // IMAGE DISPLAY AREA (Matches ScanBoard Viewfinder)
  // ----------------------------------------------------
  imageDisplayArea: {
    // This view ensures the image is displayed in the same 80% square space
    position: 'absolute',
    top: (width - IMAGE_DISPLAY_SIZE) / 2, // Centering logic
    left: (width - IMAGE_DISPLAY_SIZE) / 2, // Centering logic
    width: IMAGE_DISPLAY_SIZE,
    height: IMAGE_DISPLAY_SIZE,
    backgroundColor: colors.backgroundDark, 
    overflow: 'hidden',
  },
  image: {
    width: '100%', 
    height: '100%',
    // We use cover because the image is already cropped to 1:1 by ImageResizer
    resizeMode: 'cover', 
  },
  
  // ----------------------------------------------------
  // CONFIRMATION CONTROLS (V/X Buttons & Text)
  // ----------------------------------------------------
  // Main control container that floats over the entire screen
  confirmationOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  
  // Top text instruction box
  instructionBox: {
    paddingTop: 50,
    paddingHorizontal: 20,
    backgroundColor: 'rgba(0,0,0,0.5)',
    width: '100%',
    alignItems: 'center',
  },
  instructionText: {
    fontSize: 16,
    color: colors.textLight,
    paddingBottom: 10,
    textAlign: 'center',
  },

  // Spacer to push button row down, aligning with the bottom edge
  spacer: {
    flex: 1, 
  },
  
  // Button Row at the bottom
  buttonRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    width: '100%',
    paddingHorizontal: 30,
    paddingBottom: 20,
    backgroundColor: colors.backgroundDark, // Ensure the background is black
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