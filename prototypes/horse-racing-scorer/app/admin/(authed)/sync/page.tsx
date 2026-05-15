import Link from "next/link";
import {
  listHorses,
  listPendingUnmatched,
  listRecentSyncRuns,
} from "@/lib/queries";
import { positionLabel } from "@/lib/scoring";
import { yesterdayIso } from "@/lib/syncResults";
import {
  manualSyncAction,
  resolveUnmatchedAction,
  ignoreUnmatchedAction,
} from "./actions";

export const dynamic = "force-dynamic";

type Props = {
  searchParams: Promise<{ ran?: string; error?: string }>;
};

export default async function AdminSyncPage({ searchParams }: Props) {
  const { ran, error } = await searchParams;
  const credsSet =
    !!process.env.RACING_API_USERNAME && !!process.env.RACING_API_PASSWORD;
  const runs = listRecentSyncRuns();
  const unmatched = listPendingUnmatched();
  const horses = listHorses();
  const defaultDate = yesterdayIso();

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold">Results sync</h1>
        <p className="mt-1 text-sm text-stone-600">
          Pulls UK &amp; Irish results from{" "}
          <a
            className="underline"
            href="https://www.theracingapi.com/"
            target="_blank"
            rel="noreferrer"
          >
            The Racing API
          </a>
          . Auto-matches horses against your pool; anything we can&apos;t match goes
          into the unmatched list for you to resolve.
        </p>
      </header>

      {!credsSet && (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <strong>API credentials missing.</strong> Set{" "}
          <code className="rounded bg-amber-100 px-1">RACING_API_USERNAME</code> and{" "}
          <code className="rounded bg-amber-100 px-1">RACING_API_PASSWORD</code> in
          your environment, then restart the service. Sync will fail until then.
        </p>
      )}
      {ran && (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          Sync complete — see the run below.
        </p>
      )}
      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          Sync failed: {decodeURIComponent(error)}
        </p>
      )}

      <section>
        <form
          action={manualSyncAction}
          className="flex flex-wrap items-end gap-3 rounded-lg border border-stone-200 bg-white p-4"
        >
          <label className="block text-sm">
            <span className="font-medium">Date to pull</span>
            <input
              type="date"
              name="date"
              defaultValue={defaultDate}
              className="mt-1 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={!credsSet}
            className="rounded-md bg-stone-900 px-3 py-2 text-sm font-semibold text-white hover:bg-stone-700 disabled:cursor-not-allowed disabled:bg-stone-300"
          >
            Pull results
          </button>
          <span className="text-xs text-stone-500">
            Defaults to yesterday. Cron does this nightly.
          </span>
        </form>
      </section>

      <section>
        <h2 className="text-lg font-semibold">
          Unmatched horses{" "}
          {unmatched.length > 0 && (
            <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
              {unmatched.length}
            </span>
          )}
        </h2>
        {unmatched.length === 0 ? (
          <p className="mt-2 rounded border border-stone-200 bg-white p-4 text-sm text-stone-600">
            Nothing pending. All synced horses matched to a horse in your pool.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {unmatched.map((u) => {
              const scorePct =
                u.suggestionScore != null
                  ? `${Math.round(u.suggestionScore * 100)}%`
                  : null;
              return (
                <li
                  key={u.id}
                  className="rounded-lg border border-stone-200 bg-white p-3 text-sm"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <span className="font-mono text-xs text-stone-500">
                        {positionLabel(u.position)}
                      </span>{" "}
                      <span className="font-semibold">{u.apiHorseName}</span>{" "}
                      <span className="text-stone-500">
                        in {u.raceName}
                        {u.meeting && ` · ${u.meeting}`}
                      </span>
                    </div>
                    <span className="text-xs text-stone-500">
                      {new Date(u.raceDate).toLocaleDateString("en-GB")}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <form
                      action={resolveUnmatchedAction}
                      className="flex flex-1 min-w-[16rem] items-center gap-2"
                    >
                      <input type="hidden" name="unmatchedId" value={u.id} />
                      <select
                        name="horseId"
                        defaultValue={u.suggestionHorseId ?? ""}
                        className="flex-1 rounded-md border border-stone-300 bg-white px-2 py-1 text-sm"
                      >
                        <option value="">— pick a horse —</option>
                        {horses.map((h) => (
                          <option key={h.id} value={h.id}>
                            {h.name}
                          </option>
                        ))}
                      </select>
                      <button
                        type="submit"
                        className="rounded bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white hover:bg-stone-700"
                      >
                        Apply
                      </button>
                    </form>
                    <form action={ignoreUnmatchedAction}>
                      <input type="hidden" name="unmatchedId" value={u.id} />
                      <button
                        type="submit"
                        className="rounded border border-stone-300 px-2.5 py-1 text-xs text-stone-600 hover:border-red-300 hover:bg-red-50 hover:text-red-700"
                        title="Not in our pool — skip this finisher"
                      >
                        Ignore
                      </button>
                    </form>
                  </div>
                  {u.suggestionHorseName && (
                    <p className="mt-1 text-xs text-stone-500">
                      Best guess: <strong>{u.suggestionHorseName}</strong>
                      {scorePct && <> ({scorePct} similar)</>} — below the
                      auto-match threshold.
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold">Recent runs</h2>
        {runs.length === 0 ? (
          <p className="mt-2 rounded border border-stone-200 bg-white p-4 text-sm text-stone-600">
            No sync runs yet.
          </p>
        ) : (
          <div className="mt-2 overflow-hidden rounded-lg border border-stone-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-stone-50 text-left text-xs uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="px-3 py-2">When</th>
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Trigger</th>
                  <th className="px-3 py-2 text-right">Races</th>
                  <th className="px-3 py-2 text-right">Applied</th>
                  <th className="px-3 py-2 text-right">Unmatched</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr
                    key={r.id}
                    className="border-t border-stone-100 hover:bg-stone-50"
                  >
                    <td className="px-3 py-2 text-stone-600">
                      {new Date(r.startedAt).toLocaleString("en-GB")}
                    </td>
                    <td className="px-3 py-2">{r.requestedDate}</td>
                    <td className="px-3 py-2 text-stone-600">{r.triggeredBy}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {r.racesSeen}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {r.resultsApplied}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {r.unmatchedCount}
                    </td>
                    <td className="px-3 py-2">
                      <StatusPill status={r.status} error={r.error} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="text-xs text-stone-500">
        Want to add a missing horse to the pool first?{" "}
        <Link href="/admin/horses" className="underline">
          Manage horses
        </Link>
        .
      </p>
    </div>
  );
}

function StatusPill({ status, error }: { status: string; error: string | null }) {
  const tone =
    status === "ok"
      ? "bg-emerald-100 text-emerald-800"
      : status === "error"
        ? "bg-red-100 text-red-800"
        : "bg-stone-100 text-stone-600";
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-xs ${tone}`}
      title={error ?? undefined}
    >
      {status}
    </span>
  );
}
