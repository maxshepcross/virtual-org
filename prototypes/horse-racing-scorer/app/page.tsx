import Link from "next/link";
import { countEntrants, countHorses, countRaces } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default function Home() {
  const horses = countHorses();
  const entrants = countEntrants();
  const { total: races, completed } = countRaces();

  return (
    <div className="space-y-8">
      <section className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
        <h1 className="text-3xl font-bold tracking-tight">15 To Follow</h1>
        <p className="mt-2 max-w-2xl text-stone-600">
          Pick 15 horses for the UK racing season. Earn 10/5/3 points every time
          one of your picks finishes 1st, 2nd or 3rd in a qualifying race. The
          leaderboard updates as results are entered.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link
            href="/enter"
            className="rounded-md bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-700"
          >
            Submit your 15
          </Link>
          <Link
            href="/leaderboard"
            className="rounded-md border border-stone-300 bg-white px-4 py-2 text-sm font-semibold hover:bg-stone-100"
          >
            See leaderboard
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Stat label="Horses in pool" value={horses} />
        <Stat label="Entrants" value={entrants} />
        <Stat label="Races scored" value={`${completed} / ${races}`} />
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <div className="text-xs uppercase tracking-wide text-stone-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}
