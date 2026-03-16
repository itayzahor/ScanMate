import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { colors } from '../theme';

type GameNavRowProps = {
  currentIndex: number;
  totalMoves: number;
  onGoTo: (index: number) => void;
};

export const GameNavRow: React.FC<GameNavRowProps> = ({ currentIndex, totalMoves, onGoTo }) => (
  <View style={navStyles.row}>
    <TouchableOpacity
      style={[navStyles.button, currentIndex === 0 && navStyles.disabled]}
      disabled={currentIndex === 0}
      onPress={() => onGoTo(0)}
    >
      <Text style={navStyles.text}>{'|◁'}</Text>
    </TouchableOpacity>
    <TouchableOpacity
      style={[navStyles.button, currentIndex === 0 && navStyles.disabled]}
      disabled={currentIndex === 0}
      onPress={() => onGoTo(currentIndex - 1)}
    >
      <Text style={navStyles.text}>{'◁'}</Text>
    </TouchableOpacity>
    <TouchableOpacity
      style={[navStyles.button, currentIndex >= totalMoves && navStyles.disabled]}
      disabled={currentIndex >= totalMoves}
      onPress={() => onGoTo(currentIndex + 1)}
    >
      <Text style={navStyles.text}>{'▷'}</Text>
    </TouchableOpacity>
    <TouchableOpacity
      style={[navStyles.button, currentIndex >= totalMoves && navStyles.disabled]}
      disabled={currentIndex >= totalMoves}
      onPress={() => onGoTo(totalMoves)}
    >
      <Text style={navStyles.text}>{'▷|'}</Text>
    </TouchableOpacity>
  </View>
);

const navStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    marginBottom: 12,
  },
  button: {
    width: 48,
    height: 40,
    borderRadius: 8,
    backgroundColor: '#1f1f1f',
    alignItems: 'center',
    justifyContent: 'center',
  },
  disabled: {
    opacity: 0.3,
  },
  text: {
    color: colors.textLight,
    fontSize: 16,
    fontWeight: '700',
  },
});
