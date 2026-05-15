export type HorseLite = { id: string; name: string };

export type MatchResult =
  | { kind: "exact"; horse: HorseLite }
  | { kind: "fuzzy"; horse: HorseLite; score: number }
  | { kind: "miss"; bestCandidate?: HorseLite; bestScore?: number };

// Drop country suffixes "(IRE)", "(GB)", "(USA)" etc and strip everything that
// isn't a letter/number. Lowercase. Apostrophes and "the" prefix go too — both
// are common sources of mismatch between data sources.
export function normalizeHorseName(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/\([^)]*\)/g, " ")
    .replace(/^the\s+/, "")
    .replace(/[^a-z0-9]+/g, "")
    .trim();
}

// Damerau-Levenshtein distance, iterative.
function distance(a: string, b: string): number {
  if (a === b) return 0;
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;

  const m = a.length;
  const n = b.length;
  const prev = new Array<number>(n + 1);
  const curr = new Array<number>(n + 1);
  for (let j = 0; j <= n; j++) prev[j] = j;

  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(
        prev[j] + 1,
        curr[j - 1] + 1,
        prev[j - 1] + cost,
      );
    }
    for (let j = 0; j <= n; j++) prev[j] = curr[j];
  }
  return prev[n];
}

function similarity(a: string, b: string): number {
  if (a.length === 0 && b.length === 0) return 1;
  const d = distance(a, b);
  return 1 - d / Math.max(a.length, b.length);
}

export function matchHorse(
  apiName: string,
  pool: ReadonlyArray<HorseLite>,
  options: { fuzzyThreshold?: number } = {},
): MatchResult {
  const fuzzyThreshold = options.fuzzyThreshold ?? 0.9;
  const target = normalizeHorseName(apiName);
  if (!target) return { kind: "miss" };

  let exact: HorseLite | undefined;
  let best: { horse: HorseLite; score: number } | undefined;

  for (const h of pool) {
    const norm = normalizeHorseName(h.name);
    if (norm === target) {
      exact = h;
      break;
    }
    const score = similarity(target, norm);
    if (!best || score > best.score) {
      best = { horse: h, score };
    }
  }

  if (exact) return { kind: "exact", horse: exact };

  if (best && best.score >= fuzzyThreshold) {
    return { kind: "fuzzy", horse: best.horse, score: best.score };
  }

  return best
    ? { kind: "miss", bestCandidate: best.horse, bestScore: best.score }
    : { kind: "miss" };
}
