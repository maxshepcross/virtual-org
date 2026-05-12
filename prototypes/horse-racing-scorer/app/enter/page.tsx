import { listHorses, countHorses } from "@/lib/queries";
import { EntryForm } from "./EntryForm";
import { PICK_COUNT } from "./constants";

export const dynamic = "force-dynamic";

export default function EnterPage() {
  const horses = listHorses();
  const total = countHorses();

  if (total === 0) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
        <h1 className="text-xl font-semibold">No horses in the pool yet</h1>
        <p className="mt-2 text-sm">
          An admin needs to seed horses before entries can be taken. Run{" "}
          <code className="rounded bg-amber-100 px-1 py-0.5">npm run seed</code> or add them via the admin page.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Pick your {PICK_COUNT} horses</h1>
        <p className="mt-1 text-sm text-stone-600">
          Choose exactly {PICK_COUNT} horses from the {total} in the pool. You score 10/5/3 points
          every time one of them finishes 1st/2nd/3rd in a qualifying race.
        </p>
      </header>
      <EntryForm horses={horses.map((h) => ({ id: h.id, name: h.name }))} />
    </div>
  );
}
