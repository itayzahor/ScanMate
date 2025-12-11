import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Switch,
  Modal,
  SafeAreaView,
  ScrollView,
  Alert,
  Pressable,
  Image,
  ImageSourcePropType,
  ActivityIndicator,
} from 'react-native';
import Chessboard, { ChessboardRef } from 'react-native-chessboard';
import { Chess, Square, PieceSymbol, Color, Move } from 'chess.js';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../../../App';
import { styles } from '../../ui/styles/Analysis.styles';
import { analyzePosition, AnalyzePositionResponse, AnalysisLine } from '../../services/api';
import { ScreenHeader } from '../../ui/components/ScreenHeader';
import { normalizeFen, STARTING_FEN } from '../../shared/utils/fen';
import { getBoardSize } from '../../shared/constants/layout';

// --- TYPES ---
type PieceOption = { type: PieceSymbol; color: Color; label: string; asset: ImageSourcePropType };
type LogicMove = { from: Square; to: Square; promotion?: PieceSymbol; isFree?: boolean };
type CandidateMove = {
  from: Square;
  to: Square;
  logicFrom: Square;
  logicTo: Square;
  promotion?: PieceSymbol;
  isFree?: boolean;
};

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] as const;
const PIECE_ASSETS: Record<`${Color}${PieceSymbol}`, ImageSourcePropType> = {
  wp: require('react-native-chessboard/src/assets/wp.png'),
  wn: require('react-native-chessboard/src/assets/wn.png'),
  wb: require('react-native-chessboard/src/assets/wb.png'),
  wr: require('react-native-chessboard/src/assets/wr.png'),
  wq: require('react-native-chessboard/src/assets/wq.png'),
  wk: require('react-native-chessboard/src/assets/wk.png'),
  bp: require('react-native-chessboard/src/assets/bp.png'),
  bn: require('react-native-chessboard/src/assets/bn.png'),
  bb: require('react-native-chessboard/src/assets/bb.png'),
  br: require('react-native-chessboard/src/assets/br.png'),
  bq: require('react-native-chessboard/src/assets/bq.png'),
  bk: require('react-native-chessboard/src/assets/bk.png'),
};
const BOARD_SQUARE_ROWS: Square[][] = Array.from({ length: 8 }, (_, rowIndex) => {
  const rank = 8 - rowIndex;
  return FILES.map((file) => `${file}${rank}` as Square);
});

const squareToIndices = (square: Square) => {
  const file = square[0];
  const rank = Number(square[1]);
  const col = FILES.indexOf(file as typeof FILES[number]);
  const row = 8 - rank;
  return { row, col };
};

const indicesToSquare = (row: number, col: number): Square | null => {
  if (row < 0 || row > 7 || col < 0 || col > 7) {
    return null;
  }
  const file = FILES[col];
  const rank = 8 - row;
  return `${file}${rank}` as Square;
};

const reverseSquare = (square: Square): Square => {
  const { row, col } = squareToIndices(square);
  const reversedRow = 7 - row;
  const reversedCol = 7 - col;
  return indicesToSquare(reversedRow, reversedCol)!;
};

const getSquareCenter = (square: Square, boardPixels: number) => {
  const { row, col } = squareToIndices(square);
  const squareSize = boardPixels / 8;
  return {
    x: col * squareSize + squareSize / 2,
    y: row * squareSize + squareSize / 2,
  };
};

const PIECE_OPTIONS: PieceOption[] = [
  { type: 'p', color: 'w', label: 'W Pawn', asset: PIECE_ASSETS.wp },
  { type: 'n', color: 'w', label: 'W Knight', asset: PIECE_ASSETS.wn },
  { type: 'b', color: 'w', label: 'W Bishop', asset: PIECE_ASSETS.wb },
  { type: 'r', color: 'w', label: 'W Rook', asset: PIECE_ASSETS.wr },
  { type: 'q', color: 'w', label: 'W Queen', asset: PIECE_ASSETS.wq },
  { type: 'k', color: 'w', label: 'W King', asset: PIECE_ASSETS.wk },
  { type: 'p', color: 'b', label: 'B Pawn', asset: PIECE_ASSETS.bp },
  { type: 'n', color: 'b', label: 'B Knight', asset: PIECE_ASSETS.bn },
  { type: 'b', color: 'b', label: 'B Bishop', asset: PIECE_ASSETS.bb },
  { type: 'r', color: 'b', label: 'B Rook', asset: PIECE_ASSETS.br },
  { type: 'q', color: 'b', label: 'B Queen', asset: PIECE_ASSETS.bq },
  { type: 'k', color: 'b', label: 'B King', asset: PIECE_ASSETS.bk },
];

const PROMOTION_CHOICES: PieceSymbol[] = ['q', 'r', 'b', 'n'];

// --- LOGIC HELPERS ---
const emptyBoard = () =>
  Array.from({ length: 8 }, () => Array(8).fill(null) as Array<string | null>);

const placementToBoard = (placement: string) => {
  const rows = placement.split('/');
  const board = emptyBoard();

  rows.forEach((row, rowIndex) => {
    if (rowIndex >= 8) {
      return;
    }
    let colIndex = 0;
    row.split('').forEach((char) => {
      if (colIndex >= 8) {
        return;
      }
      if (/\d/.test(char)) {
        colIndex += Number(char);
        return;
      }
      board[rowIndex][colIndex] = char;
      colIndex += 1;
    });
  });

  return board;
};

const boardToPlacement = (board: Array<Array<string | null>>) =>
  board
    .map((row) => {
      let result = '';
      let emptyCount = 0;

      row.forEach((cell) => {
        if (!cell) {
          emptyCount += 1;
        } else {
          if (emptyCount > 0) {
            result += String(emptyCount);
            emptyCount = 0;
          }
          result += cell;
        }
      });

      if (emptyCount > 0) {
        result += String(emptyCount);
      }

      return result || '8';
    })
    .join('/');

const charToPiece = (char: string): { type: PieceSymbol; color: Color } => ({
  type: char.toLowerCase() as PieceSymbol,
  color: char === char.toUpperCase() ? 'w' : 'b',
});

const pieceToChar = (piece: { type: PieceSymbol; color: Color }) =>
  piece.color === 'w' ? piece.type.toUpperCase() : piece.type;

const loadChess = (fen: string): Chess | null => {
  try {
    return new Chess(fen);
  } catch {
    return null;
  }
};

const getBoardAndPiece = (fen: string, square: Square) => {
  const normalized = normalizeFen(fen);
  const [placement] = normalized.split(' ');
  const board = placementToBoard(placement);
  const { row, col } = squareToIndices(square);
  const cell = board[row]?.[col] ?? null;
  if (!cell) {
    return null;
  }
  return {
    board,
    pieceChar: cell,
    piece: charToPiece(cell),
    position: { row, col },
  };
};

const collectSlidingMoves = (
  moves: CandidateMove[],
  board: Array<Array<string | null>>,
  start: { row: number; col: number },
  deltas: Array<[number, number]>,
  piece: { color: Color },
) => {
  deltas.forEach(([dr, dc]) => {
    let row = start.row + dr;
    let col = start.col + dc;
    while (row >= 0 && row < 8 && col >= 0 && col < 8) {
      const occupant = board[row][col];
      if (occupant) {
        const targetPiece = charToPiece(occupant);
        if (targetPiece.color !== piece.color) {
          const square = indicesToSquare(row, col);
          if (square) {
            moves.push({ from: indicesToSquare(start.row, start.col)!, to: square, isFree: true });
          }
        }
        break;
      }
      const square = indicesToSquare(row, col);
      if (square) {
        moves.push({ from: indicesToSquare(start.row, start.col)!, to: square, isFree: true });
      }
      row += dr;
      col += dc;
    }
  });
};

const generatePseudoMoves = (fen: string, square: Square): LogicMove[] => {
  const info = getBoardAndPiece(fen, square);
  if (!info) {
    return [];
  }
  const { board, piece, position } = info;
  const fromSquare = indicesToSquare(position.row, position.col)!;
  const moves: LogicMove[] = [];

  const addMove = (row: number, col: number) => {
    const targetSquare = indicesToSquare(row, col);
    if (!targetSquare) {
      return;
    }
    const occupant = board[row]?.[col] ?? null;
    if (occupant) {
      const targetPiece = charToPiece(occupant);
      if (targetPiece.color === piece.color) {
        return;
      }
    }
    moves.push({ from: fromSquare, to: targetSquare, isFree: true });
  };

  switch (piece.type) {
    case 'p': {
      const dir = piece.color === 'w' ? -1 : 1;
      const startRow = piece.color === 'w' ? 6 : 1;
      const nextRow = position.row + dir;
      if (nextRow >= 0 && nextRow < 8 && !board[nextRow][position.col]) {
        addMove(nextRow, position.col);
        const doubleRow = position.row === startRow ? position.row + dir * 2 : null;
        if (doubleRow !== null && doubleRow >= 0 && doubleRow < 8 && !board[doubleRow][position.col]) {
          addMove(doubleRow, position.col);
        }
      }
      [-1, 1].forEach((dc) => {
        const targetCol = position.col + dc;
        const targetRow = position.row + dir;
        if (targetRow < 0 || targetRow >= 8 || targetCol < 0 || targetCol >= 8) {
          return;
        }
        const occupant = board[targetRow][targetCol];
        if (occupant && charToPiece(occupant).color !== piece.color) {
          addMove(targetRow, targetCol);
        }
      });
      break;
    }
    case 'n': {
      const offsets = [
        [2, 1],
        [2, -1],
        [-2, 1],
        [-2, -1],
        [1, 2],
        [1, -2],
        [-1, 2],
        [-1, -2],
      ];
      offsets.forEach(([dr, dc]) => {
        const row = position.row + dr;
        const col = position.col + dc;
        if (row >= 0 && row < 8 && col >= 0 && col < 8) {
          addMove(row, col);
        }
      });
      break;
    }
    case 'b': {
      collectSlidingMoves(moves, board, position, [[1, 1], [1, -1], [-1, 1], [-1, -1]], piece);
      break;
    }
    case 'r': {
      collectSlidingMoves(moves, board, position, [[1, 0], [-1, 0], [0, 1], [0, -1]], piece);
      break;
    }
    case 'q': {
      collectSlidingMoves(
        moves,
        board,
        position,
        [[1, 1], [1, -1], [-1, 1], [-1, -1], [1, 0], [-1, 0], [0, 1], [0, -1]],
        piece,
      );
      break;
    }
    case 'k': {
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          if (dr === 0 && dc === 0) {
            continue;
          }
          const row = position.row + dr;
          const col = position.col + dc;
          if (row >= 0 && row < 8 && col >= 0 && col < 8) {
            addMove(row, col);
          }
        }
      }
      break;
    }
    default:
      break;
  }

  return moves;
};

const FenUtils = {
  // Rotate the board 180 degrees (The "Direction" fix)
  reverseFen: (fen: string): string => {
    const [placement, activeColor, castling, enPassant, halfMove, fullMove] = fen.split(' ');
    
    const reversedPlacement = placement
      .split('/')
      .reverse()
      .map((row) => row.split('').reverse().join(''))
      .join('/');

    const reversedEnPassant = enPassant !== '-' ? reverseSquare(enPassant as Square) : '-';

    return `${reversedPlacement} ${activeColor} ${castling} ${reversedEnPassant} ${halfMove} ${fullMove}`;
  },

  // Toggle whose turn it is (White/Black)
  toggleTurn: (fen: string): string => {
    const parts = fen.split(' ');
    parts[1] = parts[1] === 'w' ? 'b' : 'w';
    return parts.join(' ');
  },

  // Update a single square with a new piece (or empty it)
  updateSquare: (currentFen: string, square: Square, newPiece: { type: PieceSymbol; color: Color } | null): string => {
    const normalized = normalizeFen(currentFen);
    const [placement, ...rest] = normalized.split(' ');
    const board = placementToBoard(placement);
    const { row, col } = squareToIndices(square);

    if (!board[row]) {
      board[row] = Array(8).fill(null);
    }

    board[row][col] = newPiece ? pieceToChar(newPiece) : null;
    const newPlacement = boardToPlacement(board);
    const updatedFen = [newPlacement, ...rest].slice(0, 6).join(' ');
    return updatedFen;
  },
  getPieceAt: (currentFen: string, square: Square) => {
    const normalized = normalizeFen(currentFen);
    const [placement] = normalized.split(' ');
    const board = placementToBoard(placement);
    const { row, col } = squareToIndices(square);
    const cell = board[row]?.[col] ?? null;
    if (!cell) {
      return null;
    }
    return charToPiece(cell);
  },
  movePieceFreely: (
    currentFen: string,
    from: Square,
    to: Square,
    promotion?: PieceSymbol,
  ): string => {
    if (from === to) {
      return normalizeFen(currentFen);
    }

    const normalized = normalizeFen(currentFen);
    const [placement, ...rest] = normalized.split(' ');
    const board = placementToBoard(placement);
    const fromIdx = squareToIndices(from);
    const toIdx = squareToIndices(to);
    const piece = board[fromIdx.row]?.[fromIdx.col];

    if (!piece) {
      return normalized;
    }

    const pieceColor: Color = piece === piece.toUpperCase() ? 'w' : 'b';

    if (!board[toIdx.row]) {
      board[toIdx.row] = Array(8).fill(null);
    }

    board[fromIdx.row][fromIdx.col] = null;
    const destinationPiece = promotion
      ? pieceToChar({ type: promotion, color: pieceColor })
      : piece;
    board[toIdx.row][toIdx.col] = destinationPiece;

    const newPlacement = boardToPlacement(board);
    return [newPlacement, ...rest].slice(0, 6).join(' ');
  },
};

const formatEvaluation = (evaluation: AnalysisLine['evaluation']) => {
  if (!evaluation) {
    return '—';
  }
  if (evaluation.type === 'mate' && typeof evaluation.value === 'number') {
    return `#${evaluation.value}`;
  }
  if (evaluation.type === 'cp' && typeof evaluation.value === 'number') {
    const score = evaluation.value / 100;
    return `${score >= 0 ? '+' : ''}${score.toFixed(2)}`;
  }
  return '—';
};

// --- COMPONENTS ---

/**
 * The "Window" that pops up to select a piece
 */
const PieceSelectorModal = ({
  visible,
  onClose,
  onSelect,
}: {
  visible: boolean;
  onClose: () => void;
  onSelect: (piece: { type: PieceSymbol; color: Color } | null) => void;
}) => {
  return (
    <Modal animationType="fade" transparent={true} visible={visible} onRequestClose={onClose}>
      <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={onClose}>
        <View style={styles.modalContent}>
          <Text style={styles.modalTitle}>Edit Square</Text>
          
          <View style={styles.gridContainer}>
            {PIECE_OPTIONS.map((p) => (
              <TouchableOpacity
                key={`${p.color}-${p.type}`}
                style={styles.gridItem}
                onPress={() => {
                  onSelect({ type: p.type, color: p.color });
                }}
              >
                <Image source={p.asset} style={styles.pieceImage} />
              </TouchableOpacity>
            ))}
            
            <TouchableOpacity
              style={[styles.gridItem, styles.trashOption]}
              onPress={() => onSelect(null)}
            >
              <Text style={styles.trashLabel}>🗑️ Empty</Text>
            </TouchableOpacity>
          </View>
        </View>
      </TouchableOpacity>
    </Modal>
  );
};

type PromotionModalProps = {
  visible: boolean;
  color: Color;
  onSelect: (piece: PieceSymbol) => void;
  onCancel: () => void;
};

const PromotionModal: React.FC<PromotionModalProps> = ({ visible, color, onSelect, onCancel }) => {
  return (
    <Modal animationType="fade" transparent visible={visible} onRequestClose={onCancel}>
      <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={onCancel}>
        <View style={styles.modalContent}>
          <Text style={styles.modalTitle}>Promote Pawn</Text>
          <View style={styles.gridContainer}>
            {PROMOTION_CHOICES.map((type) => (
              <TouchableOpacity
                key={`${color}-${type}`}
                style={styles.gridItem}
                onPress={() => onSelect(type)}
              >
                <Image
                  source={PIECE_ASSETS[`${color}${type}` as `${Color}${PieceSymbol}`]}
                  style={styles.pieceImage}
                />
              </TouchableOpacity>
            ))}
          </View>
          <TouchableOpacity style={[styles.gridItem, styles.trashOption]} onPress={onCancel}>
            <Text style={styles.trashLabel}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    </Modal>
  );
};

type OverlayRowProps = {
  squares: Square[];
  onSquarePress: (square: Square) => void;
  onSquareLongPress: (square: Square) => void;
};

const OverlayRowComponent: React.FC<OverlayRowProps> = ({ squares, onSquarePress, onSquareLongPress }) => (
  <View style={styles.overlayRow}>
    {squares.map((square) => (
      <Pressable
        key={square}
        style={styles.overlaySquare}
        android_ripple={{ color: 'transparent' }}
        delayLongPress={250}
        onPress={() => onSquarePress(square)}
        onLongPress={() => onSquareLongPress(square)}
      />
    ))}
  </View>
);

const OverlayRow = React.memo(OverlayRowComponent);
OverlayRow.displayName = 'OverlayRow';

type BestMoveArrowProps = {
  from?: Square | null;
  to?: Square | null;
  boardPixels: number | null;
};

const BestMoveArrow: React.FC<BestMoveArrowProps> = ({ from, to, boardPixels }) => {
  if (!from || !to || !boardPixels) {
    return null;
  }

  const fromCenter = getSquareCenter(from, boardPixels);
  const toCenter = getSquareCenter(to, boardPixels);
  const dx = toCenter.x - fromCenter.x;
  const dy = toCenter.y - fromCenter.y;
  const distance = Math.sqrt(dx * dx + dy * dy);
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
  const thickness = Math.max(4, boardPixels * 0.01);
  const headSize = Math.max(12, boardPixels * 0.04);
  const bodyLength = Math.max(0, distance - headSize * 0.8);

  return (
    <View pointerEvents="none" style={styles.arrowLayer}>
      <View
        style={[
          styles.arrowWrapper,
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
            styles.arrowBody,
            {
              width: bodyLength,
              height: thickness,
              top: -thickness / 2,
            },
          ]}
        />
      </View>
      <View
        style={[
          styles.arrowHead,
          {
            width: headSize,
            height: headSize,
            left: toCenter.x - headSize / 2,
            top: toCenter.y - headSize / 2,
            transform: [{ rotate: `${angle + 45}deg` }],
          },
        ]}
      />
    </View>
  );
};

// --- MAIN SCREEN ---

type AnalysisScreenProps = NativeStackScreenProps<RootStackParamList, 'Analysis'>;

export default function AnalysisScreen({ route, navigation }: AnalysisScreenProps) {
  const initialFen = normalizeFen(route.params?.fen ?? STARTING_FEN);
  
  const [fen, setFen] = useState<string>(initialFen);
  const [modalVisible, setModalVisible] = useState(false);
  const [selectedSquare, setSelectedSquare] = useState<Square | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalyzePositionResponse | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisBaseFen, setAnalysisBaseFen] = useState<string | null>(null);
  const [pvIndex, setPvIndex] = useState(0);
  const [overlayPixels, setOverlayPixels] = useState<number | null>(null);
  const [isBoardFlipped, setIsBoardFlipped] = useState(false);
  const [isMovementReversed, setIsMovementReversed] = useState(false);
  const [promotionContext, setPromotionContext] = useState<{ move: CandidateMove; color: Color } | null>(null);
  const chessboardRef = useRef<ChessboardRef>(null);
  const navigationFen = route.params?.fen;
  const selectedMoveFromRef = useRef<Square | null>(null);
  const candidateMovesRef = useRef<CandidateMove[]>([]);

  const transformFenForMovement = useCallback(
    (value: string) => (isMovementReversed ? FenUtils.reverseFen(value) : value),
    [isMovementReversed],
  );

  const mapSquareForMovement = useCallback(
    (square: Square) => (isMovementReversed ? reverseSquare(square) : square),
    [isMovementReversed],
  );

  const getPromotionColor = useCallback(
    (move: CandidateMove): Color | null => {
      const movingPiece = FenUtils.getPieceAt(fen, move.from);
      if (!movingPiece || movingPiece.type !== 'p') {
        return null;
      }
      const targetRank = Number(move.to[1]);
      const whitePromotionRank = isMovementReversed ? 1 : 8;
      const blackPromotionRank = isMovementReversed ? 8 : 1;
      if (
        (movingPiece.color === 'w' && targetRank === whitePromotionRank) ||
        (movingPiece.color === 'b' && targetRank === blackPromotionRank)
      ) {
        return movingPiece.color;
      }
      return null;
    },
    [fen, isMovementReversed],
  );

  const executeCandidateMove = useCallback(
    (move: CandidateMove, promotionOverride?: PieceSymbol) => {
      const resolvedPromotion = promotionOverride ?? move.promotion;
      if (move.isFree) {
        const logicFen = transformFenForMovement(fen);
        const nextLogicFen = FenUtils.movePieceFreely(
          logicFen,
          move.logicFrom,
          move.logicTo,
          resolvedPromotion,
        );
        const nextFen = transformFenForMovement(nextLogicFen);
        clearAnalysisState();
        applyFenUpdate(nextFen);
        clearMoveSelection();
        return;
      }

      const logicFen = transformFenForMovement(fen);
      const chess = loadChess(logicFen);
      if (!chess) {
        clearMoveSelection();
        return;
      }

      const moveResult = chess.move({
        from: move.logicFrom,
        to: move.logicTo,
        promotion: resolvedPromotion,
      });

      if (moveResult) {
        const updatedFen = transformFenForMovement(chess.fen());
        clearAnalysisState();
        applyFenUpdate(updatedFen);
      }

      clearMoveSelection();
    },
    [
      fen,
      applyFenUpdate,
      clearAnalysisState,
      clearMoveSelection,
      transformFenForMovement,
    ],
  );

  const runOnNextFrame = useCallback((fn: () => void) => {
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(fn);
      return;
    }
    setTimeout(fn, 0);
  }, []);

  const resetHighlights = useCallback(() => {
    chessboardRef.current?.resetAllHighlightedSquares();
  }, []);

  const highlightSquare = useCallback(
    (square: Square, color: string) => {
      runOnNextFrame(() => {
        chessboardRef.current?.highlight({ square, color });
      });
    },
    [runOnNextFrame],
  );

  const clearMoveSelection = useCallback(() => {
    selectedMoveFromRef.current = null;
    candidateMovesRef.current = [];
    resetHighlights();
  }, [resetHighlights]);

  const applyFenUpdate = useCallback((nextFen: string) => {
    const normalized = normalizeFen(nextFen);
    setFen(normalized);
    chessboardRef.current?.resetBoard(normalized);
  }, []);

  const clearAnalysisState = useCallback(() => {
    setAnalysisResult(null);
    setAnalysisError(null);
    setAnalysisBaseFen(null);
    setPvIndex(0);
  }, []);

  useEffect(() => {
    clearMoveSelection();
  }, [fen, clearMoveSelection]);

  useEffect(() => {
    if (!navigationFen) {
      return;
    }
    const normalized = normalizeFen(navigationFen);
    clearAnalysisState();
    applyFenUpdate(normalized);
  }, [navigationFen, clearAnalysisState, applyFenUpdate]);

  const primaryLine = analysisResult?.lines?.[0];

  const playbackData = useMemo(() => {
    if (!analysisBaseFen || !primaryLine) {
      return null;
    }

    const pvMoves = primaryLine.pv ?? [];
    const chess = new Chess(analysisBaseFen);
    const states: string[] = [analysisBaseFen];
    const moves: Array<{ from: Square; to: Square; san: string; resultingFen: string }> = [];

    for (const san of pvMoves) {
      try {
        const move = chess.move(san);
        if (!move) {
          break;
        }
        moves.push({
          from: move.from as Square,
          to: move.to as Square,
          san,
          resultingFen: chess.fen(),
        });
        states.push(chess.fen());
      } catch (error) {
        console.warn('[analysis playback] Failed to parse SAN move', san, error);
        break;
      }
    }

    return { states, moves };
  }, [analysisBaseFen, primaryLine]);

  const fallbackBestMove = useMemo(() => {
    const move = primaryLine?.best_move;
    if (!move || move.length < 4) {
      return { from: null, to: null };
    }
    return {
      from: move.slice(0, 2) as Square,
      to: move.slice(2, 4) as Square,
    };
  }, [primaryLine]);

  const upcomingMove = playbackData && pvIndex < playbackData.moves.length
    ? playbackData.moves[pvIndex]
    : null;

  const arrowFrom = upcomingMove?.from ?? fallbackBestMove.from;
  const arrowTo = upcomingMove?.to ?? fallbackBestMove.to;

  const stepToIndex = useCallback((targetIndex: number) => {
    if (!playbackData) {
      return;
    }
    const maxIndex = playbackData.states.length - 1;
    const nextIndex = Math.min(Math.max(targetIndex, 0), maxIndex);
    if (nextIndex === pvIndex) {
      return;
    }
    applyFenUpdate(playbackData.states[nextIndex]);
    setPvIndex(nextIndex);
  }, [playbackData, pvIndex, applyFenUpdate]);

  const handlePlaybackForward = useCallback(() => {
    stepToIndex(pvIndex + 1);
  }, [pvIndex, stepToIndex]);

  const handlePlaybackBackward = useCallback(() => {
    stepToIndex(pvIndex - 1);
  }, [pvIndex, stepToIndex]);

  const handlePlaybackReset = useCallback(() => {
    stepToIndex(0);
  }, [stepToIndex]);

  const playbackMoveCount = playbackData?.moves.length ?? 0;
  const canStepForward = playbackMoveCount > 0 && pvIndex < playbackMoveCount;
  const canStepBackward = playbackMoveCount > 0 && pvIndex > 0;
  const canResetPlayback = canStepBackward;

  const highlightMovesFromSquare = useCallback(
    (square: Square) => {
      const logicFen = transformFenForMovement(fen);
      const logicSquare = mapSquareForMovement(square);
      resetHighlights();
      highlightSquare(square, 'rgba(255, 214, 0, 0.35)');

      const chess = loadChess(logicFen);
      if (!chess) {
        const pseudoMoves = generatePseudoMoves(logicFen, logicSquare).map((move) => ({
          from: square,
          to: mapSquareForMovement(move.to),
          logicFrom: move.from,
          logicTo: move.to,
          promotion: move.promotion,
          isFree: move.isFree,
        }));
        pseudoMoves.forEach((move) => {
          highlightSquare(move.to, 'rgba(30, 136, 229, 0.35)');
        });
        selectedMoveFromRef.current = square;
        candidateMovesRef.current = pseudoMoves;
        return;
      }

      const moves = chess.moves({ square: logicSquare, verbose: true }) as Move[];
      moves.forEach((move) => {
        const uiTarget = mapSquareForMovement(move.to as Square);
        highlightSquare(uiTarget, 'rgba(30, 136, 229, 0.35)');
      });
      selectedMoveFromRef.current = square;
      candidateMovesRef.current = moves.map((move) => ({
        from: square,
        to: mapSquareForMovement(move.to as Square),
        logicFrom: move.from as Square,
        logicTo: move.to as Square,
        promotion: move.promotion,
      }));
    },
    [fen, highlightSquare, resetHighlights, mapSquareForMovement, transformFenForMovement]
  );

  const isBlackTurn = fen.split(' ')[1] === 'b';
  const boardSize = getBoardSize();
  const boardTransformStyle = useMemo(
    () => ({ transform: [{ rotate: isBoardFlipped ? '180deg' : '0deg' }] }),
    [isBoardFlipped],
  );
  const renderChessPiece = useCallback(
    (id: `${Color}${PieceSymbol}`) => (
      <Image
        source={PIECE_ASSETS[id]}
        style={{
          width: boardSize / 8,
          height: boardSize / 8,
          transform: [{ rotate: isBoardFlipped ? '180deg' : '0deg' }],
        }}
        resizeMode="contain"
      />
    ),
    [boardSize, isBoardFlipped],
  );

  // --- HANDLERS ---

  const handleToggleTurn = () => {
    clearAnalysisState();
    const newFen = FenUtils.toggleTurn(fen);
    applyFenUpdate(newFen);
  };

  const handleToggleBoardPerspective = () => {
    clearMoveSelection();
    setIsBoardFlipped((prev) => !prev);
  };

  const handleFlipDirection = () => {
    Alert.alert(
      isMovementReversed ? "Restore Piece Direction?" : "Flip Piece Direction?",
      "This toggles how moves are interpreted without moving the pieces. Use it if captures and pawn pushes go the wrong way.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: isMovementReversed ? "Restore" : "Flip",
          onPress: () => {
            clearAnalysisState();
            clearMoveSelection();
            setIsMovementReversed((prev) => !prev);
          }
        }
      ]
    );
  };

  const handlePromotionSelect = useCallback(
    (pieceType: PieceSymbol) => {
      if (!promotionContext) {
        return;
      }
      executeCandidateMove(promotionContext.move, pieceType);
      setPromotionContext(null);
    },
    [executeCandidateMove, promotionContext],
  );

  const handlePromotionCancel = useCallback(() => {
    setPromotionContext(null);
    clearMoveSelection();
  }, [clearMoveSelection]);

  const handleSquarePress = useCallback(
    (square: Square) => {
      const selectedMoveFrom = selectedMoveFromRef.current;
      const candidateMoves = candidateMovesRef.current;

      if (selectedMoveFrom) {
        const move = candidateMoves.find((m) => m.to === square);
        if (move) {
          const promotionColor = getPromotionColor(move);
          if (promotionColor) {
            setPromotionContext({ move, color: promotionColor });
          } else {
            executeCandidateMove(move);
          }
          return;
        }

        if (selectedMoveFrom === square) {
          clearMoveSelection();
          return;
        }
      }

      const piece = FenUtils.getPieceAt(fen, square);
      if (piece) {
        highlightMovesFromSquare(square);
      } else if (selectedMoveFromRef.current) {
        clearMoveSelection();
      }
    },
    [
      fen,
      executeCandidateMove,
      highlightMovesFromSquare,
      clearMoveSelection,
      getPromotionColor,
      setPromotionContext,
    ]
  );

  const handleSquareLongPress = useCallback(
    (square: Square) => {
      clearMoveSelection();
      setSelectedSquare(square);
      setModalVisible(true);
    },
    [clearMoveSelection]
  );

  const handleSelectPiece = useCallback(
    (piece: { type: PieceSymbol; color: Color } | null) => {
      if (selectedSquare) {
        const newFen = FenUtils.updateSquare(fen, selectedSquare, piece);
        clearAnalysisState();
        applyFenUpdate(newFen);
      }
      clearMoveSelection();
      setModalVisible(false);
      setSelectedSquare(null);
    },
    [selectedSquare, fen, clearAnalysisState, applyFenUpdate, clearMoveSelection]
  );

  const handleAnalyze = useCallback(async () => {
    try {
      setIsAnalyzing(true);
      setAnalysisError(null);
      const baseFen = fen;
      const result = await analyzePosition(baseFen, { depth: 18, multipv: 1 });
      setAnalysisBaseFen(baseFen);
      setPvIndex(0);
      setAnalysisResult(result);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Something went wrong while analyzing the position.';
      setAnalysisResult(null);
      setAnalysisError(message);
      Alert.alert('Analysis failed', message);
    } finally {
      setIsAnalyzing(false);
    }
  }, [fen]);

  const onMove = useCallback(
    (info: { state?: { fen?: string } }) => {
      const nextFen = info?.state?.fen;
      if (nextFen) {
        clearAnalysisState();
        clearMoveSelection();
        applyFenUpdate(nextFen);
      }
    },
    [applyFenUpdate, clearAnalysisState, clearMoveSelection]
  );

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <ScreenHeader
          title="Current Position"
          subtitle="Tap a piece to show moves, tap and hold to edit"
          onBack={() => navigation.goBack()}
          style={styles.header}
        />

        <View
          style={[
            styles.boardWrapper,
            { width: boardSize, height: boardSize },
            boardTransformStyle,
          ]}
        >
          <Chessboard
            ref={chessboardRef}
            fen={fen}
            onMove={onMove}
            boardSize={boardSize}
            renderPiece={renderChessPiece}
          />
          <View
            style={styles.boardOverlay}
            onLayout={(event) => {
              const { width: layoutWidth } = event.nativeEvent.layout;
              setOverlayPixels(layoutWidth);
            }}
          >
            {BOARD_SQUARE_ROWS.map((row, rowIndex) => (
              <OverlayRow
                key={`row-${rowIndex}`}
                squares={row}
                onSquarePress={handleSquarePress}
                onSquareLongPress={handleSquareLongPress}
              />
            ))}
            <BestMoveArrow
              from={arrowFrom}
              to={arrowTo}
              boardPixels={overlayPixels ?? boardSize}
            />
          </View>
        </View>

        <View style={styles.controlsContainer}>
        <View style={styles.controlRow}>
          <Text style={styles.label}>Side to Move:</Text>
          <View style={styles.switchWrapper}>
            <Text style={[styles.switchLabel, !isBlackTurn && styles.activeLabel]}>White</Text>
            <Switch
              trackColor={{ false: "#767577", true: "#81b0ff" }}
              thumbColor={isBlackTurn ? "#f5dd4b" : "#f4f3f4"}
              onValueChange={handleToggleTurn}
              value={isBlackTurn}
            />
            <Text style={[styles.switchLabel, isBlackTurn && styles.activeLabel]}>Black</Text>
          </View>
        </View>

        <View style={styles.buttonRow}>
          <TouchableOpacity style={styles.actionButton} onPress={handleToggleBoardPerspective}>
            <Text style={styles.buttonText}>
              {isBoardFlipped ? '♖ View as White' : '♜ View as Black'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.actionButton} onPress={handleFlipDirection}>
            <Text style={styles.buttonText}>
              {isMovementReversed ? '↩ Restore Piece Direction' : '🔁 Flip Piece Direction'}
            </Text>
          </TouchableOpacity>
        </View>

        <View style={[styles.buttonRow, { marginTop: 12 }]}>
          <TouchableOpacity
            style={[styles.actionButton, styles.analyzeButton, isAnalyzing && styles.analyzeButtonDisabled]}
            onPress={handleAnalyze}
            disabled={isAnalyzing}
          >
            {isAnalyzing ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={[styles.buttonText, styles.analyzeText]}>🚀 Analyze</Text>
            )}
          </TouchableOpacity>
        </View>

        {analysisError && (
          <View style={styles.analysisCard}>
            <Text style={styles.analysisErrorText}>{analysisError}</Text>
          </View>
        )}

        {isAnalyzing && !analysisResult && !analysisError && (
          <View style={styles.analysisCard}>
            <ActivityIndicator color="#fff" />
            <Text style={styles.analysisInfoText}>Analyzing position...</Text>
          </View>
        )}

        <View style={[styles.analysisCard, { width: boardSize }]}>
          {primaryLine ? (
            <>
              <View style={styles.analysisLine}>
                <View style={styles.analysisLineHeader}>
                  <Text style={styles.analysisLineIndex}>#1</Text>
                  <Text style={styles.analysisMove}>{primaryLine.best_move_san || primaryLine.best_move}</Text>
                  <Text style={styles.analysisEval}>{formatEvaluation(primaryLine.evaluation)}</Text>
                </View>
                <Text style={styles.analysisPv} numberOfLines={2}>
                  {primaryLine.pv.join(' ')}
                </Text>
              </View>
              {playbackMoveCount > 0 && (
                <View style={styles.playbackControls}>
                  <TouchableOpacity
                    style={[styles.playbackButton, !canStepBackward && styles.playbackButtonDisabled]}
                    onPress={handlePlaybackBackward}
                    disabled={!canStepBackward}
                  >
                    <Text style={styles.playbackButtonText}>◀</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.playbackButton, !canResetPlayback && styles.playbackButtonDisabled]}
                    onPress={handlePlaybackReset}
                    disabled={!canResetPlayback}
                  >
                    <Text style={styles.playbackButtonText}>⟲</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.playbackButton, !canStepForward && styles.playbackButtonDisabled]}
                    onPress={handlePlaybackForward}
                    disabled={!canStepForward}
                  >
                    <Text style={styles.playbackButtonText}>▶</Text>
                  </TouchableOpacity>
                </View>
              )}
              {playbackMoveCount > 0 && (
                <Text style={styles.playbackStatus}>Move {pvIndex} / {playbackMoveCount}</Text>
              )}
            </>
          ) : (
            <View style={styles.analysisPlaceholder}>
              <Text style={styles.analysisInfoText}>Press Analyze to see Stockfish's best line.</Text>
            </View>
          )}
        </View>
        </View>
      </ScrollView>

      <PieceSelectorModal
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        onSelect={handleSelectPiece}
      />

      <PromotionModal
        visible={!!promotionContext}
        color={promotionContext?.color ?? 'w'}
        onSelect={handlePromotionSelect}
        onCancel={handlePromotionCancel}
      />

    </SafeAreaView>
  );
}