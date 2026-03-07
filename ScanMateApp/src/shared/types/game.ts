export type GameSnapshot = {
  fen: string;
  /** Epoch timestamp in milliseconds when the frame was captured */
  timestamp: number;
  /** Optional cropped board path for future debugging or export */
  photoPath?: string;
};
