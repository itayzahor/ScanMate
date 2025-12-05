import {Dimensions} from 'react-native';

export const BOARD_HORIZONTAL_MARGIN = 16;
export const HEADER_HEIGHT = 96;

export const getBoardSize = () => {
  const {width} = Dimensions.get('window');
  return width - BOARD_HORIZONTAL_MARGIN * 2;
};
