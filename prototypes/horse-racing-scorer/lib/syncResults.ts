// Orchestrates a single "pull yesterday's results" run.
// - Calls the Racing API for a date.
// - For every result, looks up each top-3 finisher in our horse pool.
// - Exact + high-confidence fuzzy matches are applied directly.
// - Anything below the fuzzy threshold gets logged to sync_unmatched so the
//   admin can resolve it from /admin/sync.
// - Idempotent: re-running the same date won't double-count thanks to the
//   race_external_uniq index + the UNIQUE (race_id, position) constraint.

import {
  createSyncRun,
  finishSyncRun,
  findRaceByExternal,
  createRaceFromExternal,
  upsertResult,
  markRaceCompleted,
  listHorsesLite,
  recordUnmatched,
} from "./queries";
import {
  fetchResultsForDate,
  credentialsFromEnv,
  type ApiRaceResult,
  type RacingApiCredentials,
} from "./racingApi";
import { matchHorse } from "./horseMatch";

export const SYNC_SOURCE = "theracingapi";
export const DEFAULT_REGIONS = ["gb", "ire"];

export type SyncOutcome = {
  syncRunId: string;
  status: "ok" | "error";
  racesSeen: number;
  resultsApplied: number;
  unmatchedCount: number;
  error: string | null;
};

function isQualifyingPosition(p: number | null): p is 1 | 2 | 3 {
  return p === 1 || p === 2 || p === 3;
}

export async function runSync(input: {
  date: string;
  triggeredBy: "cron" | "manual" | "cli";
  credentials?: RacingApiCredentials;
  regions?: string[];
  dryRun?: boolean;
}): Promise<SyncOutcome> {
  const creds = input.credentials ?? credentialsFromEnv();
  if (!creds) {
    throw new Error(
      "Racing API credentials missing. Set RACING_API_USERNAME and RACING_API_PASSWORD.",
    );
  }

  const syncRunId = createSyncRun({
    source: SYNC_SOURCE,
    requestedDate: input.date,
    triggeredBy: input.triggeredBy,
  });

  let racesSeen = 0;
  let resultsApplied = 0;
  let unmatchedCount = 0;
  let errorMessage: string | null = null;

  try {
    const results = await fetchResultsForDate(input.date, creds, {
      regions: input.regions ?? DEFAULT_REGIONS,
    });
    racesSeen = results.length;
    const pool = listHorsesLite();

    for (const race of results) {
      const { applied, unmatched } = processRace(syncRunId, race, pool, input.dryRun);
      resultsApplied += applied;
      unmatchedCount += unmatched;
    }
  } catch (err) {
    errorMessage = err instanceof Error ? err.message : String(err);
    finishSyncRun(syncRunId, {
      status: "error",
      racesSeen,
      resultsApplied,
      unmatchedCount,
      error: errorMessage,
    });
    return {
      syncRunId,
      status: "error",
      racesSeen,
      resultsApplied,
      unmatchedCount,
      error: errorMessage,
    };
  }

  finishSyncRun(syncRunId, {
    status: "ok",
    racesSeen,
    resultsApplied,
    unmatchedCount,
    error: null,
  });
  return {
    syncRunId,
    status: "ok",
    racesSeen,
    resultsApplied,
    unmatchedCount,
    error: null,
  };
}

function processRace(
  syncRunId: string,
  race: ApiRaceResult,
  pool: ReadonlyArray<{ id: string; name: string }>,
  dryRun?: boolean,
): { applied: number; unmatched: number } {
  let applied = 0;
  let unmatched = 0;

  const externalId = race.externalId;
  const topThree = race.runners.filter((r) => isQualifyingPosition(r.position));
  if (topThree.length === 0) return { applied, unmatched };

  let raceId: string | null = null;
  if (!dryRun && externalId) {
    raceId = findRaceByExternal(SYNC_SOURCE, externalId)?.id ?? null;
    if (!raceId) {
      raceId = createRaceFromExternal({
        source: SYNC_SOURCE,
        externalId,
        name: race.raceName,
        meeting: race.course,
        date: race.date,
      });
    }
  }

  for (const runner of topThree) {
    if (!isQualifyingPosition(runner.position)) continue;
    const m = matchHorse(runner.horseName, pool);
    if (m.kind === "exact" || m.kind === "fuzzy") {
      if (!dryRun && raceId) {
        const status = upsertResult(raceId, m.horse.id, runner.position);
        if (status !== "skipped") applied++;
      } else {
        applied++;
      }
    } else {
      unmatched++;
      if (!dryRun) {
        recordUnmatched({
          syncRunId,
          raceExternalId: externalId,
          raceName: race.raceName,
          meeting: race.course,
          raceDate: race.date,
          position: runner.position,
          apiHorseName: runner.horseName,
          apiHorseId: runner.horseId,
          suggestionHorseId: m.bestCandidate?.id ?? null,
          suggestionScore: m.bestScore ?? null,
        });
      }
    }
  }

  if (!dryRun && raceId && applied > 0) {
    markRaceCompleted(raceId);
  }

  return { applied, unmatched };
}

export function yesterdayIso(now: Date = new Date()): string {
  const d = new Date(now);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}
