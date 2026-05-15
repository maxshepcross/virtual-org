import { db, genId, slugify } from "./db";
import { pointsFor } from "./scoring";

export type Horse = {
  id: string;
  name: string;
  slug: string;
};

export type Entrant = {
  id: string;
  name: string;
  email: string;
  createdAt: string;
};

export type Race = {
  id: string;
  name: string;
  meeting: string | null;
  date: string;
  completedAt: string | null;
};

export type RaceWithResults = Race & {
  results: Array<{ position: number; horseId: string; horseName: string; horseSlug: string }>;
};

export type LeaderboardRow = {
  entrantId: string;
  entrantName: string;
  points: number;
  scoringHits: number;
};

export type HorseWithPickCount = Horse & { pickCount: number };

export function listHorses(): HorseWithPickCount[] {
  return db
    .prepare(
      `SELECT h.id, h.name, h.slug, COUNT(p.entrant_id) AS pickCount
       FROM horse h
       LEFT JOIN pick p ON p.horse_id = h.id
       GROUP BY h.id
       ORDER BY h.name COLLATE NOCASE ASC`,
    )
    .all() as HorseWithPickCount[];
}

export function getHorseBySlug(slug: string): Horse | null {
  return (db
    .prepare(`SELECT id, name, slug FROM horse WHERE slug = ?`)
    .get(slug) as Horse | undefined) ?? null;
}

export function listEntrantsForHorse(horseId: string): Entrant[] {
  return db
    .prepare(
      `SELECT e.id, e.name, e.email, e.created_at AS createdAt
       FROM entrant e
       JOIN pick p ON p.entrant_id = e.id
       WHERE p.horse_id = ?
       ORDER BY e.name COLLATE NOCASE ASC`,
    )
    .all(horseId) as Entrant[];
}

export function createOrReplaceEntrant(
  name: string,
  email: string,
  horseIds: string[],
): { entrantId: string; replaced: boolean } {
  const normalisedEmail = email.trim().toLowerCase();
  const trimmedName = name.trim();

  return db.transaction(() => {
    const existing = db
      .prepare(`SELECT id FROM entrant WHERE email = ?`)
      .get(normalisedEmail) as { id: string } | undefined;

    let entrantId: string;
    let replaced = false;

    if (existing) {
      entrantId = existing.id;
      db.prepare(`UPDATE entrant SET name = ? WHERE id = ?`).run(trimmedName, entrantId);
      db.prepare(`DELETE FROM pick WHERE entrant_id = ?`).run(entrantId);
      replaced = true;
    } else {
      entrantId = genId();
      db.prepare(
        `INSERT INTO entrant (id, name, email) VALUES (?, ?, ?)`,
      ).run(entrantId, trimmedName, normalisedEmail);
    }

    const insertPick = db.prepare(
      `INSERT INTO pick (entrant_id, horse_id) VALUES (?, ?)`,
    );
    for (const horseId of horseIds) {
      insertPick.run(entrantId, horseId);
    }

    return { entrantId, replaced };
  })();
}

export function findEntrantByEmail(email: string): Entrant | null {
  return (db
    .prepare(
      `SELECT id, name, email, created_at AS createdAt
       FROM entrant WHERE email = ?`,
    )
    .get(email.trim().toLowerCase()) as Entrant | undefined) ?? null;
}

export function listEntrantPicks(entrantId: string): Horse[] {
  return db
    .prepare(
      `SELECT h.id, h.name, h.slug
       FROM horse h
       JOIN pick p ON p.horse_id = h.id
       WHERE p.entrant_id = ?
       ORDER BY h.name COLLATE NOCASE ASC`,
    )
    .all(entrantId) as Horse[];
}

export function getLeaderboard(): LeaderboardRow[] {
  const rows = db
    .prepare(
      `SELECT
         e.id    AS entrantId,
         e.name  AS entrantName,
         r.position
       FROM entrant e
       JOIN pick p   ON p.entrant_id = e.id
       JOIN result r ON r.horse_id   = p.horse_id`,
    )
    .all() as Array<{ entrantId: string; entrantName: string; position: number }>;

  const byEntrant = new Map<string, LeaderboardRow>();
  const allEntrants = db
    .prepare(`SELECT id, name FROM entrant ORDER BY name COLLATE NOCASE ASC`)
    .all() as Array<{ id: string; name: string }>;
  for (const e of allEntrants) {
    byEntrant.set(e.id, {
      entrantId: e.id,
      entrantName: e.name,
      points: 0,
      scoringHits: 0,
    });
  }

  for (const row of rows) {
    const entry = byEntrant.get(row.entrantId);
    if (!entry) continue;
    entry.points += pointsFor(row.position);
    entry.scoringHits += 1;
  }

  return Array.from(byEntrant.values()).sort((a, b) => {
    if (b.points !== a.points) return b.points - a.points;
    return a.entrantName.localeCompare(b.entrantName);
  });
}

export function listRaces(): RaceWithResults[] {
  const races = db
    .prepare(
      `SELECT id, name, meeting, date, completed_at AS completedAt
       FROM race
       ORDER BY date DESC, name ASC`,
    )
    .all() as Race[];

  const resultsStmt = db.prepare(
    `SELECT r.position, r.horse_id AS horseId, h.name AS horseName, h.slug AS horseSlug
     FROM result r
     JOIN horse h ON h.id = r.horse_id
     WHERE r.race_id = ?
     ORDER BY r.position ASC`,
  );

  return races.map((race) => ({
    ...race,
    results: resultsStmt.all(race.id) as RaceWithResults["results"],
  }));
}

export function getRace(raceId: string): RaceWithResults | null {
  const race = db
    .prepare(
      `SELECT id, name, meeting, date, completed_at AS completedAt
       FROM race WHERE id = ?`,
    )
    .get(raceId) as Race | undefined;
  if (!race) return null;

  const results = db
    .prepare(
      `SELECT r.position, r.horse_id AS horseId, h.name AS horseName, h.slug AS horseSlug
       FROM result r
       JOIN horse h ON h.id = r.horse_id
       WHERE r.race_id = ?
       ORDER BY r.position ASC`,
    )
    .all(raceId) as RaceWithResults["results"];

  return { ...race, results };
}

export function createRace(input: { name: string; meeting?: string; date: string }): string {
  const id = genId();
  db.prepare(
    `INSERT INTO race (id, name, meeting, date) VALUES (?, ?, ?, ?)`,
  ).run(id, input.name.trim(), input.meeting?.trim() || null, input.date);
  return id;
}

export function deleteRace(raceId: string): void {
  db.prepare(`DELETE FROM race WHERE id = ?`).run(raceId);
}

export function setRaceResults(
  raceId: string,
  results: Array<{ position: 1 | 2 | 3; horseId: string }>,
): void {
  db.transaction(() => {
    db.prepare(`DELETE FROM result WHERE race_id = ?`).run(raceId);
    const insert = db.prepare(
      `INSERT INTO result (id, race_id, horse_id, position) VALUES (?, ?, ?, ?)`,
    );
    for (const r of results) {
      insert.run(genId(), raceId, r.horseId, r.position);
    }
    db.prepare(
      `UPDATE race SET completed_at = CURRENT_TIMESTAMP WHERE id = ?`,
    ).run(raceId);
  })();
}

export function clearRaceResults(raceId: string): void {
  db.transaction(() => {
    db.prepare(`DELETE FROM result WHERE race_id = ?`).run(raceId);
    db.prepare(`UPDATE race SET completed_at = NULL WHERE id = ?`).run(raceId);
  })();
}

export function addHorse(name: string): { id: string; slug: string } {
  const id = genId();
  const slug = slugify(name);
  db.prepare(`INSERT INTO horse (id, name, slug) VALUES (?, ?, ?)`).run(id, name.trim(), slug);
  return { id, slug };
}

export function deleteHorse(horseId: string): void {
  db.prepare(`DELETE FROM horse WHERE id = ?`).run(horseId);
}

export function bulkAddHorses(names: string[]): { added: number; skipped: number } {
  let added = 0;
  let skipped = 0;
  const insert = db.prepare(
    `INSERT OR IGNORE INTO horse (id, name, slug) VALUES (?, ?, ?)`,
  );
  db.transaction(() => {
    for (const raw of names) {
      const name = raw.trim();
      if (!name) continue;
      const result = insert.run(genId(), name, slugify(name));
      if (result.changes > 0) added++;
      else skipped++;
    }
  })();
  return { added, skipped };
}

export function countHorses(): number {
  return (db.prepare(`SELECT COUNT(*) AS c FROM horse`).get() as { c: number }).c;
}

export function countEntrants(): number {
  return (db.prepare(`SELECT COUNT(*) AS c FROM entrant`).get() as { c: number }).c;
}

export function countRaces(): { total: number; completed: number } {
  const r = db
    .prepare(
      `SELECT
         COUNT(*) AS total,
         COUNT(completed_at) AS completed
       FROM race`,
    )
    .get() as { total: number; completed: number };
  return r;
}

export function listAllEntrants(): Entrant[] {
  return db
    .prepare(
      `SELECT id, name, email, created_at AS createdAt
       FROM entrant ORDER BY name COLLATE NOCASE ASC`,
    )
    .all() as Entrant[];
}

export function listHorsesLite(): Array<{ id: string; name: string }> {
  return db
    .prepare(`SELECT id, name FROM horse ORDER BY name COLLATE NOCASE ASC`)
    .all() as Array<{ id: string; name: string }>;
}

export function findRaceByExternal(
  source: string,
  externalId: string,
): { id: string } | null {
  return (db
    .prepare(
      `SELECT id FROM race WHERE external_source = ? AND external_id = ?`,
    )
    .get(source, externalId) as { id: string } | undefined) ?? null;
}

export function createRaceFromExternal(input: {
  source: string;
  externalId: string;
  name: string;
  meeting: string | null;
  date: string;
}): string {
  const id = genId();
  db.prepare(
    `INSERT INTO race (id, name, meeting, date, external_source, external_id)
     VALUES (?, ?, ?, ?, ?, ?)`,
  ).run(id, input.name, input.meeting, input.date, input.source, input.externalId);
  return id;
}

export function upsertResult(
  raceId: string,
  horseId: string,
  position: 1 | 2 | 3,
): "inserted" | "updated" | "skipped" {
  const existing = db
    .prepare(
      `SELECT id, horse_id FROM result WHERE race_id = ? AND position = ?`,
    )
    .get(raceId, position) as { id: string; horse_id: string } | undefined;
  if (existing) {
    if (existing.horse_id === horseId) return "skipped";
    db.prepare(`UPDATE result SET horse_id = ? WHERE id = ?`).run(horseId, existing.id);
    return "updated";
  }
  try {
    db.prepare(
      `INSERT INTO result (id, race_id, horse_id, position) VALUES (?, ?, ?, ?)`,
    ).run(genId(), raceId, horseId, position);
    return "inserted";
  } catch (err) {
    // Likely UNIQUE (race_id, horse_id) — same horse already recorded for
    // another position in this race. Treat as a skip; sync will surface it via
    // the unmatched flow if it really is wrong.
    if (err instanceof Error && /UNIQUE/i.test(err.message)) return "skipped";
    throw err;
  }
}

export function markRaceCompleted(raceId: string): void {
  db.prepare(
    `UPDATE race SET completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP) WHERE id = ?`,
  ).run(raceId);
}

export type SyncRun = {
  id: string;
  source: string;
  requestedDate: string;
  triggeredBy: string;
  startedAt: string;
  finishedAt: string | null;
  status: "running" | "ok" | "error";
  racesSeen: number;
  resultsApplied: number;
  unmatchedCount: number;
  error: string | null;
};

export function createSyncRun(input: {
  source: string;
  requestedDate: string;
  triggeredBy: string;
}): string {
  const id = genId();
  db.prepare(
    `INSERT INTO sync_run (id, source, requested_date, triggered_by, status)
     VALUES (?, ?, ?, ?, 'running')`,
  ).run(id, input.source, input.requestedDate, input.triggeredBy);
  return id;
}

export function finishSyncRun(
  id: string,
  result: {
    status: "ok" | "error";
    racesSeen: number;
    resultsApplied: number;
    unmatchedCount: number;
    error?: string | null;
  },
): void {
  db.prepare(
    `UPDATE sync_run
       SET finished_at = CURRENT_TIMESTAMP,
           status = ?,
           races_seen = ?,
           results_applied = ?,
           unmatched_count = ?,
           error = ?
     WHERE id = ?`,
  ).run(
    result.status,
    result.racesSeen,
    result.resultsApplied,
    result.unmatchedCount,
    result.error ?? null,
    id,
  );
}

export function listRecentSyncRuns(limit = 20): SyncRun[] {
  return db
    .prepare(
      `SELECT id, source, requested_date AS requestedDate,
              triggered_by AS triggeredBy, started_at AS startedAt,
              finished_at AS finishedAt, status,
              races_seen AS racesSeen, results_applied AS resultsApplied,
              unmatched_count AS unmatchedCount, error
       FROM sync_run
       ORDER BY started_at DESC
       LIMIT ?`,
    )
    .all(limit) as SyncRun[];
}

export type UnmatchedRow = {
  id: string;
  syncRunId: string;
  raceExternalId: string | null;
  raceName: string;
  meeting: string | null;
  raceDate: string;
  position: number;
  apiHorseName: string;
  apiHorseId: string | null;
  suggestionHorseId: string | null;
  suggestionHorseName: string | null;
  suggestionScore: number | null;
  resolvedAt: string | null;
  resolvedHorseId: string | null;
  ignoredAt: string | null;
  createdAt: string;
};

export function recordUnmatched(input: {
  syncRunId: string;
  raceExternalId: string | null;
  raceName: string;
  meeting: string | null;
  raceDate: string;
  position: 1 | 2 | 3;
  apiHorseName: string;
  apiHorseId: string | null;
  suggestionHorseId: string | null;
  suggestionScore: number | null;
}): void {
  db.prepare(
    `INSERT INTO sync_unmatched
       (id, sync_run_id, race_external_id, race_name, meeting, race_date,
        position, api_horse_name, api_horse_id,
        suggestion_horse_id, suggestion_score)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    genId(),
    input.syncRunId,
    input.raceExternalId,
    input.raceName,
    input.meeting,
    input.raceDate,
    input.position,
    input.apiHorseName,
    input.apiHorseId,
    input.suggestionHorseId,
    input.suggestionScore,
  );
}

export function listPendingUnmatched(): UnmatchedRow[] {
  return db
    .prepare(
      `SELECT u.id, u.sync_run_id AS syncRunId, u.race_external_id AS raceExternalId,
              u.race_name AS raceName, u.meeting, u.race_date AS raceDate,
              u.position, u.api_horse_name AS apiHorseName, u.api_horse_id AS apiHorseId,
              u.suggestion_horse_id AS suggestionHorseId,
              h.name AS suggestionHorseName,
              u.suggestion_score AS suggestionScore,
              u.resolved_at AS resolvedAt, u.resolved_horse_id AS resolvedHorseId,
              u.ignored_at AS ignoredAt, u.created_at AS createdAt
       FROM sync_unmatched u
       LEFT JOIN horse h ON h.id = u.suggestion_horse_id
       WHERE u.resolved_at IS NULL AND u.ignored_at IS NULL
       ORDER BY u.race_date DESC, u.race_name ASC, u.position ASC`,
    )
    .all() as UnmatchedRow[];
}

export function resolveUnmatched(
  unmatchedId: string,
  horseId: string,
): { ok: boolean; reason?: string } {
  const row = db
    .prepare(
      `SELECT id, race_external_id, race_name, meeting, race_date, position,
              resolved_at, ignored_at
       FROM sync_unmatched WHERE id = ?`,
    )
    .get(unmatchedId) as
      | {
          id: string;
          race_external_id: string | null;
          race_name: string;
          meeting: string | null;
          race_date: string;
          position: 1 | 2 | 3;
          resolved_at: string | null;
          ignored_at: string | null;
        }
      | undefined;
  if (!row) return { ok: false, reason: "not_found" };
  if (row.resolved_at || row.ignored_at) return { ok: false, reason: "already_handled" };

  const horse = db.prepare(`SELECT id FROM horse WHERE id = ?`).get(horseId) as
    | { id: string }
    | undefined;
  if (!horse) return { ok: false, reason: "horse_not_found" };

  db.transaction(() => {
    let raceId: string | null = null;
    if (row.race_external_id) {
      const existing = findRaceByExternal("theracingapi", row.race_external_id);
      raceId = existing?.id ?? null;
    }
    if (!raceId) {
      raceId = createRaceFromExternal({
        source: "theracingapi",
        externalId: row.race_external_id ?? `manual-${row.id}`,
        name: row.race_name,
        meeting: row.meeting,
        date: row.race_date,
      });
    }
    upsertResult(raceId, horseId, row.position);
    markRaceCompleted(raceId);
    db.prepare(
      `UPDATE sync_unmatched
         SET resolved_at = CURRENT_TIMESTAMP, resolved_horse_id = ?
       WHERE id = ?`,
    ).run(horseId, row.id);
  })();
  return { ok: true };
}

export function ignoreUnmatched(unmatchedId: string): void {
  db.prepare(
    `UPDATE sync_unmatched
       SET ignored_at = CURRENT_TIMESTAMP
     WHERE id = ? AND resolved_at IS NULL AND ignored_at IS NULL`,
  ).run(unmatchedId);
}

export function countPendingUnmatched(): number {
  return (db
    .prepare(
      `SELECT COUNT(*) AS c FROM sync_unmatched
       WHERE resolved_at IS NULL AND ignored_at IS NULL`,
    )
    .get() as { c: number }).c;
}
