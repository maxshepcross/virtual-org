"use client";

import { useActionState, useMemo, useState } from "react";
import { submitEntry } from "./actions";
import { PICK_COUNT, type EntryFormState } from "./constants";

type Horse = { id: string; name: string };

const initialState: EntryFormState = {};

export function EntryForm({ horses }: { horses: Horse[] }) {
  const [state, formAction, pending] = useActionState(submitEntry, initialState);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    const f = filter.trim().toLowerCase();
    if (!f) return horses;
    return horses.filter((h) => h.name.toLowerCase().includes(f));
  }, [filter, horses]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        if (next.size >= PICK_COUNT) return prev;
        next.add(id);
      }
      return next;
    });
  }

  const remaining = PICK_COUNT - selected.size;
  const canSubmit = selected.size === PICK_COUNT && !pending;

  return (
    <form action={formAction} className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium">Your name</span>
          <input
            name="name"
            required
            autoComplete="name"
            className="mt-1 block w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-stone-500 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium">Email</span>
          <input
            name="email"
            type="email"
            required
            autoComplete="email"
            className="mt-1 block w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-stone-500 focus:outline-none"
          />
          <span className="mt-1 block text-xs text-stone-500">
            We use this to identify you. Re-submitting with the same email replaces your picks.
          </span>
        </label>
      </div>

      <div className="rounded-lg border border-stone-200 bg-white">
        <div className="sticky top-0 z-10 flex flex-wrap items-center gap-3 border-b border-stone-200 bg-white px-4 py-3">
          <input
            type="search"
            placeholder="Search horses…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="flex-1 min-w-[12rem] rounded-md border border-stone-300 px-3 py-1.5 text-sm focus:border-stone-500 focus:outline-none"
          />
          <div
            className={`text-sm font-medium tabular-nums ${
              remaining === 0
                ? "text-emerald-700"
                : remaining < 0
                  ? "text-red-700"
                  : "text-stone-700"
            }`}
          >
            {selected.size} / {PICK_COUNT} picked
            {remaining > 0 ? ` · ${remaining} to go` : ""}
          </div>
        </div>

        <ul className="max-h-[60vh] divide-y divide-stone-100 overflow-y-auto">
          {filtered.map((h) => {
            const isSelected = selected.has(h.id);
            const disabled = !isSelected && selected.size >= PICK_COUNT;
            return (
              <li key={h.id}>
                <label
                  className={`flex cursor-pointer items-center gap-3 px-4 py-2 text-sm hover:bg-stone-50 ${
                    isSelected ? "bg-emerald-50" : ""
                  } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    disabled={disabled}
                    onChange={() => toggle(h.id)}
                    className="h-4 w-4 accent-stone-900"
                  />
                  <span className="flex-1">{h.name}</span>
                  {isSelected && <input type="hidden" name="horseId" value={h.id} />}
                </label>
              </li>
            );
          })}
          {filtered.length === 0 && (
            <li className="px-4 py-8 text-center text-sm text-stone-500">
              No horses match &ldquo;{filter}&rdquo;.
            </li>
          )}
        </ul>
      </div>

      {state.error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">{state.error}</p>
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-md bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-700 disabled:cursor-not-allowed disabled:bg-stone-300"
        >
          {pending ? "Submitting…" : `Submit ${selected.size} picks`}
        </button>
        {selected.size !== PICK_COUNT && (
          <span className="text-sm text-stone-500">
            Pick exactly {PICK_COUNT} to enable submit.
          </span>
        )}
      </div>
    </form>
  );
}
