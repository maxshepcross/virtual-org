import Link from "next/link";
import { listRaces } from "@/lib/queries";
import { positionLabel } from "@/lib/scoring";
import { createRaceAction, deleteRaceAction } from "./actions";

export const dynamic = "force-dynamic";

export default function AdminRacesPage() {
  const races = listRaces();
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold">Races &amp; results</h1>
        <p className="mt-1 text-sm text-stone-600">
          Add a race, then click into it to enter 1st/2nd/3rd. Adding results updates the
          leaderboard immediately.
        </p>
      </header>

      <form
        action={createRaceAction}
        className="rounded-lg border border-stone-200 bg-white p-4"
      >
        <h2 className="text-sm font-semibold">Add a race</h2>
        <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="block text-sm">
            <span className="font-medium">Race</span>
            <input
              name="name"
              required
              placeholder="Gold Cup"
              className="mt-1 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">Meeting (optional)</span>
            <input
              name="meeting"
              placeholder="Royal Ascot"
              className="mt-1 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">Date</span>
            <input
              type="date"
              name="date"
              required
              defaultValue={today}
              className="mt-1 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
            />
          </label>
        </div>
        <button
          type="submit"
          className="mt-3 rounded-md bg-stone-900 px-3 py-2 text-sm font-semibold text-white hover:bg-stone-700"
        >
          Add race
        </button>
      </form>

      <section>
        <h2 className="text-lg font-semibold">All races</h2>
        {races.length === 0 ? (
          <p className="mt-2 rounded border border-stone-200 bg-white p-4 text-sm text-stone-600">
            None yet.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {races.map((race) => (
              <li
                key={race.id}
                className="rounded-md border border-stone-200 bg-white p-3 text-sm"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <Link
                      href={`/admin/races/${race.id}`}
                      className="font-medium hover:underline"
                    >
                      {race.name}
                    </Link>
                    {race.meeting && (
                      <span className="text-stone-500"> · {race.meeting}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-stone-500">
                      {new Date(race.date).toLocaleDateString("en-GB")}
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs ${
                        race.completedAt
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-stone-100 text-stone-600"
                      }`}
                    >
                      {race.completedAt ? "Scored" : "Pending"}
                    </span>
                    <form action={deleteRaceAction}>
                      <input type="hidden" name="id" value={race.id} />
                      <button
                        type="submit"
                        className="rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-600 hover:border-red-300 hover:bg-red-50 hover:text-red-700"
                      >
                        Delete
                      </button>
                    </form>
                  </div>
                </div>
                {race.results.length > 0 && (
                  <ol className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-stone-600">
                    {race.results.map((r) => (
                      <li key={r.position}>
                        <span className="font-mono text-stone-500">
                          {positionLabel(r.position)}
                        </span>{" "}
                        {r.horseName}
                      </li>
                    ))}
                  </ol>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
