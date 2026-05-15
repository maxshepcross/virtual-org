// Pulls racing results for a given date and applies them.
//
// Usage:
//   npm run sync -- --date 2026-05-14
//   npm run sync -- --yesterday          # default if no date given
//   npm run sync -- --date 2026-05-14 --dry-run
//
// Reads credentials from RACING_API_USERNAME / RACING_API_PASSWORD.
// Designed to be called by Railway's scheduler nightly.

import { runSync, yesterdayIso, DEFAULT_REGIONS } from "../lib/syncResults";

type Args = { date: string; dryRun: boolean; regions: string[] };

function parseArgs(argv: string[]): Args {
  let date: string | null = null;
  let dryRun = false;
  let regions = DEFAULT_REGIONS;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--yesterday") date = yesterdayIso();
    else if (a === "--today") date = new Date().toISOString().slice(0, 10);
    else if (a === "--dry-run") dryRun = true;
    else if (a === "--date") {
      date = argv[++i] ?? null;
    } else if (a === "--regions") {
      regions = (argv[++i] ?? "").split(",").map((s) => s.trim()).filter(Boolean);
    }
  }
  if (!date) date = yesterdayIso();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    throw new Error(`--date must be YYYY-MM-DD, got "${date}"`);
  }
  return { date, dryRun, regions };
}

async function main() {
  const { date, dryRun, regions } = parseArgs(process.argv.slice(2));
  console.log(
    `[sync] date=${date} regions=${regions.join(",") || "(all)"} dryRun=${dryRun}`,
  );

  const outcome = await runSync({
    date,
    triggeredBy: "cli",
    regions,
    dryRun,
  });

  console.log(`[sync] status=${outcome.status} run_id=${outcome.syncRunId}`);
  console.log(`[sync] races_seen=${outcome.racesSeen}`);
  console.log(`[sync] results_applied=${outcome.resultsApplied}`);
  console.log(`[sync] unmatched=${outcome.unmatchedCount}`);
  if (outcome.error) {
    console.error(`[sync] error: ${outcome.error}`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
