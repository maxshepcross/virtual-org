import Link from "next/link";
import { listEntrantPicks } from "@/lib/queries";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

type Props = { searchParams: Promise<{ id?: string }> };

export default async function ThanksPage({ searchParams }: Props) {
  const { id } = await searchParams;
  const entrant = id
    ? (db
        .prepare(`SELECT id, name, email FROM entrant WHERE id = ?`)
        .get(id) as { id: string; name: string; email: string } | undefined)
    : undefined;
  const picks = id ? listEntrantPicks(id) : [];

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6">
        <h1 className="text-2xl font-bold text-emerald-900">Entry submitted</h1>
        {entrant ? (
          <p className="mt-1 text-sm text-emerald-900">
            Thanks {entrant.name} — your 15 picks are locked in. You can re-submit with the same
            email ({entrant.email}) at any time to update them.
          </p>
        ) : (
          <p className="mt-1 text-sm text-emerald-900">Thanks — your picks are saved.</p>
        )}
      </div>

      {picks.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold">Your picks</h2>
          <ul className="mt-2 grid grid-cols-1 gap-1 text-sm sm:grid-cols-2">
            {picks.map((p) => (
              <li key={p.id} className="rounded border border-stone-200 bg-white px-3 py-1.5">
                {p.name}
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="flex gap-3">
        <Link
          href="/leaderboard"
          className="rounded-md bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-700"
        >
          See leaderboard
        </Link>
        <Link
          href="/"
          className="rounded-md border border-stone-300 bg-white px-4 py-2 text-sm font-semibold hover:bg-stone-100"
        >
          Home
        </Link>
      </div>
    </div>
  );
}
