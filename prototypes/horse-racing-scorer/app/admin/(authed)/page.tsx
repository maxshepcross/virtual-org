import Link from "next/link";
import {
  countEntrants,
  countHorses,
  countPendingUnmatched,
  countRaces,
} from "@/lib/queries";

export const dynamic = "force-dynamic";

export default function AdminHome() {
  const horses = countHorses();
  const entrants = countEntrants();
  const { total: races, completed } = countRaces();
  const pending = countPendingUnmatched();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Admin</h1>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card href="/admin/horses" label="Horses" value={horses} sub="manage the pool" />
        <Card href="/admin/races" label="Races" value={`${completed} / ${races}`} sub="manage and score" />
        <Card href="/admin/entrants" label="Entrants" value={entrants} sub="view all entries" />
        <Card
          href="/admin/sync"
          label="Sync queue"
          value={pending}
          sub={pending === 0 ? "all matched" : "needs your attention"}
          highlight={pending > 0}
        />
      </div>
    </div>
  );
}

function Card({
  href,
  label,
  value,
  sub,
  highlight,
}: {
  href: string;
  label: string;
  value: number | string;
  sub: string;
  highlight?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`block rounded-lg border p-4 hover:bg-stone-50 ${
        highlight
          ? "border-amber-300 bg-amber-50 hover:bg-amber-100"
          : "border-stone-200 bg-white"
      }`}
    >
      <div className="text-xs uppercase tracking-wide text-stone-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-xs text-stone-500">{sub}</div>
    </Link>
  );
}
