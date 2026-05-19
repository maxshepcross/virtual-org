// Thin wrapper around https://api.theracingapi.com/v1/results
//
// Endpoint reference is reverse-engineered from theracingapi's public gists
// (results_pull.py, racecards_first_run_gelded_report.py). Inner field names
// for a result/runner object are not officially documented, so this module
// reads them defensively (RaceResult.runners[].position handles both number
// and string forms like "1" or "1st"). If the API ever changes shape, adjust
// `parseResult` and friends in one place rather than touching consumers.

import { Buffer } from "node:buffer";

const BASE_URL = "https://api.theracingapi.com";
const RATE_LIMIT_DELAY_MS = 600; // API allows 2 req/s; stay comfortably under.

export type RacingApiCredentials = {
  username: string;
  password: string;
};

export type ApiRunner = {
  horseName: string;
  horseId: string | null;
  position: number | null;
  positionRaw: string | null;
  raw: Record<string, unknown>;
};

export type ApiRaceResult = {
  externalId: string | null;
  raceName: string;
  course: string | null;
  region: string | null;
  date: string;
  offTime: string | null;
  runners: ApiRunner[];
  raw: Record<string, unknown>;
};

export type ApiResultsPage = {
  total: number;
  results: ApiRaceResult[];
};

export function credentialsFromEnv(): RacingApiCredentials | null {
  const username = process.env.RACING_API_USERNAME;
  const password = process.env.RACING_API_PASSWORD;
  if (!username || !password) return null;
  return { username, password };
}

function authHeader(creds: RacingApiCredentials): string {
  const token = Buffer.from(`${creds.username}:${creds.password}`).toString("base64");
  return `Basic ${token}`;
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(
  url: string,
  creds: RacingApiCredentials,
): Promise<Record<string, unknown>> {
  const res = await fetch(url, {
    headers: {
      Authorization: authHeader(creds),
      Accept: "application/json",
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(
      `Racing API ${res.status} ${res.statusText} for ${url}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as Record<string, unknown>;
}

function asString(v: unknown): string | null {
  if (typeof v === "string") return v;
  if (typeof v === "number") return String(v);
  return null;
}

function parsePosition(v: unknown): { position: number | null; raw: string | null } {
  if (v === null || v === undefined) return { position: null, raw: null };
  const raw = typeof v === "string" ? v : String(v);
  const match = raw.trim().match(/^(\d+)/);
  return {
    position: match ? Number(match[1]) : null,
    raw,
  };
}

function parseRunner(r: Record<string, unknown>): ApiRunner {
  const name =
    asString(r.horse) ?? asString(r.horse_name) ?? asString(r.name) ?? "(unknown)";
  const horseId = asString(r.horse_id) ?? asString(r.id);
  const { position, raw } = parsePosition(r.position ?? r.finishing_position);
  return {
    horseName: name,
    horseId,
    position,
    positionRaw: raw,
    raw: r,
  };
}

function parseResult(r: Record<string, unknown>): ApiRaceResult {
  const runners = Array.isArray(r.runners)
    ? r.runners
        .filter((x): x is Record<string, unknown> => !!x && typeof x === "object")
        .map(parseRunner)
    : [];
  return {
    externalId:
      asString(r.race_id) ?? asString(r.id) ?? asString(r.race_instance_id),
    raceName:
      asString(r.race_name) ??
      asString(r.title) ??
      asString(r.name) ??
      "(unknown race)",
    course: asString(r.course),
    region: asString(r.region),
    date:
      asString(r.date) ?? asString(r.race_date) ?? asString(r.off_dt) ?? "",
    offTime: asString(r.off_time) ?? asString(r.off_dt),
    runners,
    raw: r,
  };
}

/**
 * Pull every result for a single calendar date, handling pagination.
 *
 * `regions`: optional filter (e.g. ["gb", "ire"]). The API accepts a comma
 *   separated list on the `region` query param. UK + IRE covers the friends
 *   comp's qualifying races on the free tier.
 */
export async function fetchResultsForDate(
  date: string,
  creds: RacingApiCredentials,
  options: { regions?: string[]; pageSize?: number } = {},
): Promise<ApiRaceResult[]> {
  const limit = options.pageSize ?? 50;
  const regionParam = options.regions?.length
    ? `&region=${encodeURIComponent(options.regions.join(","))}`
    : "";
  const out: ApiRaceResult[] = [];
  let skip = 0;

  while (true) {
    const url =
      `${BASE_URL}/v1/results?` +
      `start_date=${encodeURIComponent(date)}` +
      `&end_date=${encodeURIComponent(date)}` +
      `&limit=${limit}&skip=${skip}` +
      regionParam;

    const body = await fetchJson(url, creds);
    const rawResults = Array.isArray(body.results) ? body.results : [];
    for (const r of rawResults) {
      if (r && typeof r === "object") {
        out.push(parseResult(r as Record<string, unknown>));
      }
    }
    const total =
      typeof body.total === "number" ? body.total : out.length;
    skip += limit;
    if (skip >= total || rawResults.length === 0) break;
    await sleep(RATE_LIMIT_DELAY_MS);
  }

  return out;
}
