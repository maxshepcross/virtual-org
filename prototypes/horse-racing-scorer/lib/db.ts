import Database from "better-sqlite3";
import path from "node:path";
import fs from "node:fs";
import { STARTER_HORSES } from "./starter-horses";

const DB_PATH = process.env.DB_PATH
  ? path.resolve(process.env.DB_PATH)
  : path.join(process.cwd(), "data", "comp.db");

fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });

const globalForDb = globalThis as unknown as { __db?: Database.Database };

export const db: Database.Database =
  globalForDb.__db ?? new Database(DB_PATH);

db.pragma("busy_timeout = 5000");
db.pragma("journal_mode = WAL");
db.pragma("foreign_keys = ON");

if (!globalForDb.__db) {
  initSchema(db);
  migrate(db);
  autoSeedIfEmpty(db);
  globalForDb.__db = db;
}

function initSchema(d: Database.Database) {
  d.exec(`
    CREATE TABLE IF NOT EXISTS horse (
      id          TEXT PRIMARY KEY,
      name        TEXT NOT NULL UNIQUE,
      slug        TEXT NOT NULL UNIQUE,
      created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS entrant (
      id          TEXT PRIMARY KEY,
      name        TEXT NOT NULL,
      email       TEXT NOT NULL UNIQUE,
      created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS pick (
      entrant_id  TEXT NOT NULL REFERENCES entrant(id) ON DELETE CASCADE,
      horse_id    TEXT NOT NULL REFERENCES horse(id)   ON DELETE CASCADE,
      created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (entrant_id, horse_id)
    );

    CREATE TABLE IF NOT EXISTS race (
      id              TEXT PRIMARY KEY,
      name            TEXT NOT NULL,
      meeting         TEXT,
      date            TEXT NOT NULL,
      completed_at    TEXT,
      external_source TEXT,
      external_id     TEXT,
      created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS result (
      id          TEXT PRIMARY KEY,
      race_id     TEXT NOT NULL REFERENCES race(id)  ON DELETE CASCADE,
      horse_id    TEXT NOT NULL REFERENCES horse(id) ON DELETE CASCADE,
      position    INTEGER NOT NULL CHECK (position BETWEEN 1 AND 3),
      created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE (race_id, position),
      UNIQUE (race_id, horse_id)
    );

    CREATE TABLE IF NOT EXISTS settings (
      key   TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sync_run (
      id               TEXT PRIMARY KEY,
      source           TEXT NOT NULL,
      requested_date   TEXT NOT NULL,
      triggered_by     TEXT NOT NULL,
      started_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      finished_at      TEXT,
      status           TEXT NOT NULL,
      races_seen       INTEGER NOT NULL DEFAULT 0,
      results_applied  INTEGER NOT NULL DEFAULT 0,
      unmatched_count  INTEGER NOT NULL DEFAULT 0,
      error            TEXT
    );

    CREATE INDEX IF NOT EXISTS sync_run_started_at
      ON sync_run (started_at DESC);

    CREATE TABLE IF NOT EXISTS sync_unmatched (
      id              TEXT PRIMARY KEY,
      sync_run_id     TEXT NOT NULL REFERENCES sync_run(id) ON DELETE CASCADE,
      race_external_id TEXT,
      race_name       TEXT NOT NULL,
      meeting         TEXT,
      race_date       TEXT NOT NULL,
      position        INTEGER NOT NULL CHECK (position BETWEEN 1 AND 3),
      api_horse_name  TEXT NOT NULL,
      api_horse_id    TEXT,
      suggestion_horse_id TEXT REFERENCES horse(id) ON DELETE SET NULL,
      suggestion_score    REAL,
      resolved_at     TEXT,
      resolved_horse_id TEXT REFERENCES horse(id) ON DELETE SET NULL,
      ignored_at      TEXT,
      created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS sync_unmatched_pending
      ON sync_unmatched (resolved_at, ignored_at);
  `);
}

function migrate(d: Database.Database) {
  // Backfill columns on the race table for DBs created before the sync feature.
  const cols = d.prepare(`PRAGMA table_info(race)`).all() as Array<{ name: string }>;
  const has = (name: string) => cols.some((c) => c.name === name);
  if (!has("external_source")) {
    d.exec(`ALTER TABLE race ADD COLUMN external_source TEXT`);
  }
  if (!has("external_id")) {
    d.exec(`ALTER TABLE race ADD COLUMN external_id TEXT`);
  }
  d.exec(`
    CREATE UNIQUE INDEX IF NOT EXISTS race_external_uniq
      ON race (external_source, external_id)
      WHERE external_source IS NOT NULL AND external_id IS NOT NULL;
  `);
}

function autoSeedIfEmpty(d: Database.Database) {
  if (process.env.SKIP_AUTOSEED === "1") return;
  const { c } = d.prepare(`SELECT COUNT(*) AS c FROM horse`).get() as { c: number };
  if (c > 0) return;
  const insert = d.prepare(
    `INSERT OR IGNORE INTO horse (id, name, slug) VALUES (?, ?, ?)`,
  );
  const tx = d.transaction(() => {
    for (const name of STARTER_HORSES) {
      insert.run(genId(), name, slugify(name));
    }
  });
  tx();
}

export function genId(): string {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 24);
}

export function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}
