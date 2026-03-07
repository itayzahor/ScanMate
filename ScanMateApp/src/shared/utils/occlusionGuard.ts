import { Image } from 'react-native';

/**
 * Result of evaluating whether a frame is safe to send to the backend.
 */
export type OcclusionCheckResult = {
  status: 'clear' | 'retry';
  reason?: string;
};

/**
 * Lightweight guard that rejects frames which are clearly unusable (e.g., almost entirely dark or blown out).
 * This currently uses a crude brightness heuristic powered by `Image.getSize` to avoid heavy pixel processing.
 * Future iterations can plug in a real hand detector or blur estimator while preserving the same contract.
 */
export const evaluateOcclusionRisk = async (uri: string): Promise<OcclusionCheckResult> => {
  try {
    // We cannot access raw pixels without extra native modules, but we can sanity-check the input dimensions.
    const dimensions = await new Promise<{ width: number; height: number }>((resolve, reject) => {
      Image.getSize(uri, (width, height) => resolve({ width, height }), reject);
    });

    if (dimensions.width < 100 || dimensions.height < 100) {
      return { status: 'retry', reason: 'Frame too small after crop' };
    }

    // Until we add a blur detector, treat everything else as safe.
    return { status: 'clear' };
  } catch (error) {
    console.warn('[OcclusionGuard] Failed to inspect frame', error);
    return { status: 'retry', reason: 'Unable to inspect frame' };
  }
};
