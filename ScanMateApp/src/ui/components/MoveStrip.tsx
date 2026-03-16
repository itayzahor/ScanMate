import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

type MoveStripProps = {
  prevLabel: string | null;
  currLabel: string | null;
  nextLabel: string | null;
  currentIndex: number;
  totalMoves: number;
  onGoTo: (index: number) => void;
};

export const MoveStrip: React.FC<MoveStripProps> = ({
  prevLabel, currLabel, nextLabel, currentIndex, totalMoves, onGoTo,
}) => (
  <View style={stripStyles.container}>
    <TouchableOpacity
      style={stripStyles.side}
      disabled={currentIndex < 2}
      onPress={() => onGoTo(currentIndex - 1)}
      activeOpacity={0.6}
    >
      {prevLabel ? (
        <>
          <Text style={stripStyles.sideText}>{prevLabel}</Text>
          <Text style={stripStyles.arrow}>◁</Text>
        </>
      ) : <View />}
    </TouchableOpacity>

    <View style={stripStyles.center}>
      <Text style={stripStyles.current}>{currLabel ?? 'Start'}</Text>
      <Text style={stripStyles.counter}>
        {currentIndex === 0 ? 'Start' : `${currentIndex} / ${totalMoves}`}
      </Text>
    </View>

    <TouchableOpacity
      style={stripStyles.side}
      disabled={currentIndex >= totalMoves}
      onPress={() => onGoTo(currentIndex + 1)}
      activeOpacity={0.6}
    >
      {nextLabel ? (
        <>
          <Text style={stripStyles.sideText}>{nextLabel}</Text>
          <Text style={stripStyles.arrow}>▷</Text>
        </>
      ) : <View />}
    </TouchableOpacity>
  </View>
);

const stripStyles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#1a1a1a',
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 8,
    marginBottom: 10,
  },
  side: {
    flex: 1,
    alignItems: 'center',
    opacity: 0.7,
  },
  sideText: {
    color: '#888',
    fontSize: 13,
    fontWeight: '400',
  },
  arrow: {
    color: '#666',
    fontSize: 16,
    marginTop: 2,
  },
  center: {
    flex: 1.4,
    alignItems: 'center',
  },
  current: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
  counter: {
    color: '#999',
    fontSize: 11,
    marginTop: 2,
  },
});
