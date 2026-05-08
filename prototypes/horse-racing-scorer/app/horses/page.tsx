import Link from "next/link";
import { listHorses } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default function HorsesIndexPage() {
  const horses = listHorses();
  const grouped = new Map<string, typeof horses>();
  for (const h of horses) {
    const letter = h.name[0]?.toUpperCase() ?? "?";
    const bucket = grouped.get(letter) ?? [];
    bucket.push(h);
    grouped.set(letter, bucket);
  }
  const letters = Array.from(grouped.keys()).sort();

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Horses</h1>
        <p className="mt-1 text-sm text-stone-600">
          {horses.length} horses in the pool. Click any horse to see who picked it.
        </p>
      </header>

      {horses.length === 0 ? (
        <p className="rounded-md border border-stone-200 bg-white p-6 text-sm text-stone-600">
          No horses added yet.
        </p>
      ) : (
        <div className="space-y-6">
          {letters.map((letter) => (
            <section key={letter}>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
                {letter}
              </h2>
              <ul className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2 md:grid-cols-3">
                {grouped.get(letter)!.map((h) => (
                  <li key={h.id}>
                    <Link
                      href={`/horses/${h.slug}`}
                      className="flex items-center justify-between rounded border border-stone-200 bg-white px-3 py-1.5 text-sm hover:bg-stone-50"
                    >
                      <span>{h.name}</span>
                      <span className="text-xs text-stone-500 tabular-nums">
                        {h.pickCount} {h.pickCount === 1 ? "pick" : "picks"}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
