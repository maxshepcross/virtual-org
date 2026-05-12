import { notFound } from "next/navigation";
import Link from "next/link";
import { getRace, listHorses } from "@/lib/queries";
import { saveResultsAction, clearResultsAction } from "../actions";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ saved?: string; error?: string }>;
};

export default async function RaceResultsPage({ params, searchParams }: Props) {
  const { id } = await params;
  const { saved, error } = await searchParams;
  const race = getRace(id);
  if (!race) notFound();

  const horses = listHorses();
  const placedBy = (pos: number) =>
    race.results.find((r) => r.position === pos)?.horseId ?? "";

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-wide text-stone-500">
          <Link href="/admin/races" className="hover:underline">All races</Link>
        </p>
        <h1 className="mt-1 text-2xl font-bold">{race.name}</h1>
        <p className="text-sm text-stone-600">
          {race.meeting && <span>{race.meeting} · </span>}
          {new Date(race.date).toLocaleDateString("en-GB")}
        </p>
      </header>

      {saved && (
        <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          Results saved.
        </p>
      )}
      {error === "duplicate" && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
          Same horse picked twice. Pick a different horse for each position.
        </p>
      )}

      <form
        action={saveResultsAction}
        className="rounded-lg border border-stone-200 bg-white p-4"
      >
        <input type="hidden" name="raceId" value={race.id} />
        <h2 className="text-sm font-semibold">Enter the placings</h2>
        <p className="text-xs text-stone-500">
          Leave blank if a position wasn&apos;t filled (e.g. only 2 finishers paid).
        </p>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <PositionSelect
            label="1st (10 pts)"
            name="first"
            horses={horses}
            defaultValue={placedBy(1)}
          />
          <PositionSelect
            label="2nd (5 pts)"
            name="second"
            horses={horses}
            defaultValue={placedBy(2)}
          />
          <PositionSelect
            label="3rd (3 pts)"
            name="third"
            horses={horses}
            defaultValue={placedBy(3)}
          />
        </div>
        <div className="mt-4 flex gap-2">
          <button
            type="submit"
            className="rounded-md bg-stone-900 px-3 py-2 text-sm font-semibold text-white hover:bg-stone-700"
          >
            Save results
          </button>
        </div>
      </form>

      {race.results.length > 0 && (
        <form action={clearResultsAction}>
          <input type="hidden" name="raceId" value={race.id} />
          <button
            type="submit"
            className="rounded border border-stone-300 px-3 py-1.5 text-xs text-stone-600 hover:border-red-300 hover:bg-red-50 hover:text-red-700"
          >
            Clear results
          </button>
        </form>
      )}
    </div>
  );
}

function PositionSelect({
  label,
  name,
  horses,
  defaultValue,
}: {
  label: string;
  name: string;
  horses: Array<{ id: string; name: string }>;
  defaultValue: string;
}) {
  return (
    <label className="block text-sm">
      <span className="font-medium">{label}</span>
      <select
        name={name}
        defaultValue={defaultValue}
        className="mt-1 block w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm"
      >
        <option value="">— not filled —</option>
        {horses.map((h) => (
          <option key={h.id} value={h.id}>
            {h.name}
          </option>
        ))}
      </select>
    </label>
  );
}
