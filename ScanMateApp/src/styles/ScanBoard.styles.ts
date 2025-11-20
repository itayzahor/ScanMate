import {StyleSheet, Dimensions} from 'react-native';
import {colors} from '../theme'; 

const VIEWPORT_WIDTH = Dimensions.get('window').width;
const SQUARE_SIZE = VIEWPORT_WIDTH * 0.8; // 80% of screen width

export const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundDark,
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.backgroundDark,
  },
  errorText: {
    color: colors.textLight,
    fontSize: 18,
  },
  
  // ----------------------------------------------------
  // CONTROLS AND OVERLAY STYLES
  // ----------------------------------------------------
  
  // The UI Layer that sits on top of the mask
  overlayControls: {
    ...StyleSheet.absoluteFillObject,
    // We remove paddingBottom and let flex-end push the button to the edge
    justifyContent: 'space-between', 
    alignItems: 'center',
  },
  
  instructionBox: {
    paddingTop: 50,
    paddingHorizontal: 20,
    backgroundColor: 'rgba(0,0,0,0.5)',
    width: '100%',
    alignItems: 'center',
  },
  instructionText: {
    fontSize: 16,
    textAlign: 'center',
    color: colors.textLight,
    paddingBottom: 10,
  },

  // ----------------------------------------------------
  // BUTTON STYLES (White and at the absolute bottom)
  // ----------------------------------------------------
  captureButtonContainer: {
    // This container is pushed to the bottom by 'space-between' in overlayControls
    width: '100%',
    alignItems: 'center',
    paddingBottom: 20, // ⬅️ Adding a small padding here for spacing from the edge
  },
  captureButton: {
    backgroundColor: colors.background, // ⬅️ FIX: Changed from colors.primary (Red) to colors.background (White)
    width: 80,
    height: 80,
    borderRadius: 40,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 5,
    borderColor: colors.textLight,
  },
  captureButtonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: colors.text, // ⬅️ Changed color to contrast with the white background (should be black)
    fontWeight: 'bold',
  },

  // ----------------------------------------------------
  // FLEXBOX MASKING STYLES (The geometry that worked)
  // ----------------------------------------------------
  viewfinderContainer: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'transparent', 
    justifyContent: 'center',
    alignItems: 'center',
  },
  viewfinderTopBottomMask: {
    backgroundColor: colors.backgroundDark,
    flex: 1, 
    width: '100%',
  },
  viewfinderMiddleRow: {
    flexDirection: 'row',
    width: '100%',
    height: SQUARE_SIZE, 
  },
  viewfinderSideMask: {
    backgroundColor: colors.backgroundDark,
    flex: 1, 
  },
  viewfinderGuide: {
    width: SQUARE_SIZE,
    height: SQUARE_SIZE,
    backgroundColor: 'transparent', 
    borderWidth: 3,
    borderColor: colors.secondary, 
  },
  viewfinderSpacer: {
    // This spacer now sits between the Instruction box and the capture button
    height: SQUARE_SIZE, 
    width: '100%',
    backgroundColor: 'transparent', // The spacer is transparent
  },
});