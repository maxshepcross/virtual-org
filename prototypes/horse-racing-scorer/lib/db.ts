import Database from "better-sqlite3";
import path from "node:path";
import fs from "node:fs";

const DB_PATH = process.env.DB_PATH
  ? path.resolve(process.env.DB_PATH)
  : path.join(process.cwd(), "data", "comp.db");

fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });

const globalForDb = globalThis as unknown as { __db?: Database.Database };

export const db: Database.Database =
  globalForDb.__db ?? new Database(DB_PATH);

db.pragma("journal_mode = WAL");
db.pragma("foreign_keys = ON");

if (!globalForDb.__db) {
  initSchema(db);
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
      id            TEXT PRIMARY KEY,
      name          TEXT NOT NULL,
      meeting       TEXT,
      date          TEXT NOT NULL,
      completed_at  TEXT,
      created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
  `);
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
