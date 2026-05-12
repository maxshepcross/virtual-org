import Link from "next/link";
import { listAllEntrants, listEntrantPicks } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default function AdminEntrantsPage() {
  const entrants = listAllEntrants();

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Entrants</h1>
        <p className="mt-1 text-sm text-stone-600">{entrants.length} total.</p>
      </header>

      {entrants.length === 0 ? (
        <p className="rounded border border-stone-200 bg-white p-4 text-sm text-stone-600">
          No entries yet.
        </p>
      ) : (
        <ul className="space-y-2">
          {entrants.map((e) => {
            const picks = listEntrantPicks(e.id);
            return (
              <li
                key={e.id}
                className="rounded-lg border border-stone-200 bg-white p-4 text-sm"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <span className="font-semibold">{e.name}</span>{" "}
                    <span className="text-stone-500">{e.email}</span>
                  </div>
                  <span className="text-xs text-stone-500">
                    {new Date(e.createdAt).toLocaleString("en-GB")}
                  </span>
                </div>
                <ul className="mt-2 flex flex-wrap gap-1 text-xs">
                  {picks.map((p) => (
                    <li
                      key={p.id}
                      className="rounded bg-stone-100 px-2 py-0.5"
                    >
                      <Link href={`/horses/${p.slug}`} className="hover:underline">
                        {p.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
