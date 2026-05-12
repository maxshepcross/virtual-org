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
