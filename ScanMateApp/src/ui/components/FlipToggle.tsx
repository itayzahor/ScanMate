import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

type FlipToggleProps = {
  isFlipped: boolean;
  onChange: (flipped: boolean) => void;
};

export const FlipToggle: React.FC<FlipToggleProps> = ({ isFlipped, onChange }) => (
  <View style={toggleStyles.container}>
    <TouchableOpacity
      style={[toggleStyles.half, !isFlipped && toggleStyles.active]}
      onPress={() => onChange(false)}
      activeOpacity={0.7}
    >
      <Text style={[toggleStyles.text, !isFlipped && toggleStyles.textActive]}>♖ White</Text>
    </TouchableOpacity>
    <TouchableOpacity
      style={[toggleStyles.half, isFlipped && toggleStyles.active]}
      onPress={() => onChange(true)}
      activeOpacity={0.7}
    >
      <Text style={[toggleStyles.text, isFlipped && toggleStyles.textActive]}>♜ Black</Text>
    </TouchableOpacity>
  </View>
);

const toggleStyles = StyleSheet.create({
  container: {
    flex: 1,
    flexDirection: 'row',
    backgroundColor: '#1f1f1f',
    borderRadius: 8,
    overflow: 'hidden',
  },
  half: {
    flex: 1,
    paddingVertical: 9,
    alignItems: 'center',
  },
  active: {
    backgroundColor: '#333',
    borderRadius: 8,
  },
  text: {
    color: '#777',
    fontWeight: '600',
    fontSize: 13,
  },
  textActive: {
    color: '#fff',
  },
});
