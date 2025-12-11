export const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

const FEN_DEFAULT_FIELDS = ['w', '-', '-', '0', '1'] as const;

export const normalizeFen = (rawFen?: string | null): string => {
  const fallback = STARTING_FEN;
  if (!rawFen) {
    return fallback;
  }

  const trimmed = rawFen.trim();
  if (!trimmed) {
    return fallback;
  }

  const segments = trimmed.split(/\s+/);
  if (segments.length >= 6) {
    return segments.slice(0, 6).join(' ');
  }

  const missing = 6 - segments.length;
  const filler = FEN_DEFAULT_FIELDS.slice(0, missing);
  return [...segments, ...filler].join(' ');
};
