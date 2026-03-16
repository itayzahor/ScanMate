import React from 'react';
import { StyleSheet, View } from 'react-native';
import type { Square } from 'chess.js';

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] as const;

const getSquareCenter = (square: Square, boardSize: number) => {
  const col = FILES.indexOf(square[0] as (typeof FILES)[number]);
  const row = 8 - Number(square[1]);
  const cell = boardSize / 8;
  return { x: col * cell + cell / 2, y: row * cell + cell / 2 };
};

type BestMoveArrowProps = {
  from?: Square | null;
  to?: Square | null;
  boardSize: number;
  color?: string;
};

export const BestMoveArrow: React.FC<BestMoveArrowProps> = ({ from, to, boardSize, color = '#ffb347' }) => {
  if (!from || !to || !boardSize) { return null; }

  const fromCenter = getSquareCenter(from, boardSize);
  const toCenter = getSquareCenter(to, boardSize);
  const dx = toCenter.x - fromCenter.x;
  const dy = toCenter.y - fromCenter.y;
  const distance = Math.sqrt(dx * dx + dy * dy);
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
  const thickness = Math.max(4, boardSize * 0.01);
  const headSize = Math.max(12, boardSize * 0.04);
  const bodyLength = Math.max(0, distance - headSize * 0.8);

  return (
    <View pointerEvents="none" style={arrowStyles.layer}>
      <View
        style={[
          arrowStyles.wrapper,
          {
            transform: [
              { translateX: fromCenter.x },
              { translateY: fromCenter.y },
              { rotate: `${angle}deg` },
            ],
          },
        ]}
      >
        <View
          style={[
            arrowStyles.body,
            {
              width: bodyLength,
              height: thickness,
              top: -thickness / 2,
              backgroundColor: color,
            },
          ]}
        />
      </View>
      <View
        style={[
          arrowStyles.head,
          {
            width: headSize,
            height: headSize,
            left: toCenter.x - headSize / 2,
            top: toCenter.y - headSize / 2,
            transform: [{ rotate: `${angle + 45}deg` }],
            backgroundColor: color,
          },
        ]}
      />
    </View>
  );
};

const arrowStyles = StyleSheet.create({
  layer: {
    ...StyleSheet.absoluteFillObject,
  },
  wrapper: {
    position: 'absolute',
    left: 0,
    top: 0,
  },
  body: {
    position: 'absolute',
    left: 0,
    backgroundColor: '#ffb347',
    borderRadius: 999,
    opacity: 0.9,
  },
  head: {
    position: 'absolute',
    backgroundColor: '#ffb347',
    opacity: 0.9,
  },
});
