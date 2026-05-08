import Link from "next/link";
import { notFound } from "next/navigation";
import { getHorseBySlug, listEntrantsForHorse } from "@/lib/queries";
import { db } from "@/lib/db";
import { positionLabel, pointsFor } from "@/lib/scoring";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ slug: string }> };

export default async function HorsePage({ params }: Props) {
  const { slug } = await params;
  const horse = getHorseBySlug(slug);
  if (!horse) notFound();

  const entrants = listEntrantsForHorse(horse.id);

  const results = db
    .prepare(
      `SELECT r.position, ra.id AS raceId, ra.name AS raceName, ra.meeting AS meeting, ra.date AS date
       FROM result r
       JOIN race ra ON ra.id = r.race_id
       WHERE r.horse_id = ?
       ORDER BY ra.date DESC`,
    )
    .all(horse.id) as Array<{
      position: number;
      raceId: string;
      raceName: string;
      meeting: string | null;
      date: string;
    }>;

  const totalPoints = results.reduce((sum, r) => sum + pointsFor(r.position), 0);

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-wide text-stone-500">
          <Link href="/horses" className="hover:underline">All horses</Link>
        </p>
        <h1 className="mt-1 text-3xl font-bold">{horse.name}</h1>
        <p className="mt-1 text-sm text-stone-600">
          Picked by {entrants.length} {entrants.length === 1 ? "entrant" : "entrants"} ·{" "}
          {totalPoints} pts scored across {results.length}{" "}
          {results.length === 1 ? "result" : "results"}
        </p>
      </header>

      {results.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold">Results</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {results.map((r) => (
              <li
                key={`${r.raceId}-${r.position}`}
                className="rounded border border-stone-200 bg-white px-3 py-2"
              >
                <span className="font-mono text-xs text-stone-500">
                  {positionLabel(r.position)}
                </span>{" "}
                in{" "}
                <span className="font-medium">{r.raceName}</span>
                {r.meeting && <span className="text-stone-500"> · {r.meeting}</span>}{" "}
                <span className="text-stone-500">
                  ({new Date(r.date).toLocaleDateString("en-GB")})
                </span>{" "}
                <span className="ml-1 rounded bg-stone-100 px-1.5 py-0.5 text-xs font-semibold">
                  +{pointsFor(r.position)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="text-lg font-semibold">
          Entrants who picked {horse.name}
        </h2>
        {entrants.length === 0 ? (
          <p className="mt-2 rounded-md border border-stone-200 bg-white p-4 text-sm text-stone-600">
            Nobody has picked this horse yet.
          </p>
        ) : (
          <ol className="mt-2 grid grid-cols-1 gap-1 text-sm sm:grid-cols-2 md:grid-cols-3">
            {entrants.map((e) => (
              <li
                key={e.id}
                className="rounded border border-stone-200 bg-white px-3 py-1.5"
              >
                {e.name}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
