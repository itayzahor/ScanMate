// src/theme/colors.ts

// Define a core set of semantic colors
export const palette = {
  white: '#FFFFFF',
  black: '#000000',
  grey50: '#F7F7F7',
  grey200: '#CCCCCC',
  red500: '#D60000', // Our primary capture color
  blue500: '#007AFF', // Standard interactive color
};

// Define the colors used by your application (Theme)
export const colors = {
  // Backgrounds
  background: palette.white,
  backgroundDark: palette.black,

  // Text
  text: palette.black,
  textLight: palette.white,

  // Actions/Buttons
  primary: palette.red500, // Used for the capture button
  secondary: palette.blue500,

  // Borders/Dividers
  border: palette.grey200,
};