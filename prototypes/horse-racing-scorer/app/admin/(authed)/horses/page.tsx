import { listHorses } from "@/lib/queries";
import {
  addHorseAction,
  bulkAddHorsesAction,
  deleteHorseAction,
} from "./actions";

export const dynamic = "force-dynamic";

export default function AdminHorsesPage() {
  const horses = listHorses();

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold">Horses</h1>
        <p className="mt-1 text-sm text-stone-600">
          {horses.length} in the pool. Add one at a time, or paste a list to bulk-add.
        </p>
      </header>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <form
          action={addHorseAction}
          className="rounded-lg border border-stone-200 bg-white p-4"
        >
          <h2 className="text-sm font-semibold">Add one horse</h2>
          <div className="mt-2 flex gap-2">
            <input
              name="name"
              required
              placeholder="e.g. Dirty Tom"
              className="flex-1 rounded-md border border-stone-300 px-3 py-2 text-sm"
            />
            <button
              type="submit"
              className="rounded-md bg-stone-900 px-3 py-2 text-sm font-semibold text-white hover:bg-stone-700"
            >
              Add
            </button>
          </div>
        </form>

        <form
          action={bulkAddHorsesAction}
          className="rounded-lg border border-stone-200 bg-white p-4"
        >
          <h2 className="text-sm font-semibold">Bulk add (one name per line)</h2>
          <textarea
            name="names"
            rows={4}
            required
            placeholder={"Auguste Rodin\nCity Of Troy\nDirty Tom\n…"}
            className="mt-2 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm font-mono"
          />
          <button
            type="submit"
            className="mt-2 rounded-md bg-stone-900 px-3 py-2 text-sm font-semibold text-white hover:bg-stone-700"
          >
            Add all
          </button>
        </form>
      </section>

      <section>
        <h2 className="text-lg font-semibold">All horses</h2>
        {horses.length === 0 ? (
          <p className="mt-2 rounded border border-stone-200 bg-white p-4 text-sm text-stone-600">
            None yet.
          </p>
        ) : (
          <ul className="mt-2 divide-y divide-stone-100 rounded-lg border border-stone-200 bg-white">
            {horses.map((h) => (
              <li key={h.id} className="flex items-center gap-3 px-4 py-2 text-sm">
                <span className="flex-1 font-medium">{h.name}</span>
                <span className="text-xs text-stone-500 tabular-nums">
                  {h.pickCount} {h.pickCount === 1 ? "pick" : "picks"}
                </span>
                <form action={deleteHorseAction}>
                  <input type="hidden" name="id" value={h.id} />
                  <button
                    type="submit"
                    className="rounded border border-stone-300 px-2 py-1 text-xs text-stone-600 hover:bg-red-50 hover:border-red-300 hover:text-red-700"
                  >
                    Delete
                  </button>
                </form>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
