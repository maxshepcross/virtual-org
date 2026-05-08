import { getLeaderboard, listRaces } from "@/lib/queries";
import { positionLabel, pointsFor } from "@/lib/scoring";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function LeaderboardPage() {
  const rows = getLeaderboard();
  const races = listRaces();
  const completed = races.filter((r) => r.completedAt);

  let lastPoints = -1;
  let lastRank = 0;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold">Leaderboard</h1>
        <p className="mt-1 text-sm text-stone-600">
          {rows.length} entrants · {completed.length} of {races.length} races scored
        </p>
      </header>

      {rows.length === 0 ? (
        <p className="rounded-md border border-stone-200 bg-white p-6 text-sm text-stone-600">
          No entries yet.{" "}
          <Link href="/enter" className="font-medium underline">Submit yours.</Link>
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-stone-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-left text-xs uppercase tracking-wide text-stone-500">
              <tr>
                <th className="px-4 py-2 w-12">#</th>
                <th className="px-4 py-2">Entrant</th>
                <th className="px-4 py-2 text-right">Hits</th>
                <th className="px-4 py-2 text-right">Points</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                if (row.points !== lastPoints) {
                  lastRank = i + 1;
                  lastPoints = row.points;
                }
                return (
                  <tr
                    key={row.entrantId}
                    className="border-t border-stone-100 hover:bg-stone-50"
                  >
                    <td className="px-4 py-2 tabular-nums text-stone-500">{lastRank}</td>
                    <td className="px-4 py-2 font-medium">{row.entrantName}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{row.scoringHits}</td>
                    <td className="px-4 py-2 text-right font-semibold tabular-nums">
                      {row.points}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <section>
        <h2 className="text-lg font-semibold">Recent results</h2>
        {completed.length === 0 ? (
          <p className="mt-2 rounded-md border border-stone-200 bg-white p-4 text-sm text-stone-600">
            No race results entered yet.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {completed.slice(0, 10).map((race) => (
              <li
                key={race.id}
                className="rounded-md border border-stone-200 bg-white p-3 text-sm"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <span className="font-medium">{race.name}</span>
                    {race.meeting && (
                      <span className="text-stone-500"> · {race.meeting}</span>
                    )}
                  </div>
                  <span className="text-xs text-stone-500">
                    {new Date(race.date).toLocaleDateString("en-GB")}
                  </span>
                </div>
                <ol className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-stone-700">
                  {race.results.map((r) => (
                    <li key={r.position}>
                      <span className="font-mono text-xs text-stone-500">
                        {positionLabel(r.position)}
                      </span>{" "}
                      <Link
                        href={`/horses/${r.horseSlug}`}
                        className="font-medium hover:underline"
                      >
                        {r.horseName}
                      </Link>{" "}
                      <span className="text-xs text-stone-500">
                        ({pointsFor(r.position)}pts)
                      </span>
                    </li>
                  ))}
                </ol>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
