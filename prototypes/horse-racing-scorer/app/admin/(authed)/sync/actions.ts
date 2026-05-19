"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { isAdmin } from "@/lib/auth";
import { resolveUnmatched, ignoreUnmatched } from "@/lib/queries";
import { runSync, yesterdayIso } from "@/lib/syncResults";

async function requireAdmin() {
  if (!(await isAdmin())) throw new Error("Unauthorized");
}

function bumpAllPaths() {
  revalidatePath("/admin/sync");
  revalidatePath("/leaderboard");
  revalidatePath("/horses");
  revalidatePath("/");
}

export async function manualSyncAction(formData: FormData) {
  await requireAdmin();
  const rawDate = String(formData.get("date") ?? "").trim();
  const date =
    rawDate && /^\d{4}-\d{2}-\d{2}$/.test(rawDate) ? rawDate : yesterdayIso();

  let runId = "";
  try {
    const outcome = await runSync({ date, triggeredBy: "manual" });
    runId = outcome.syncRunId;
  } catch (err) {
    const msg = encodeURIComponent(err instanceof Error ? err.message : String(err));
    redirect(`/admin/sync?error=${msg}`);
  }
  bumpAllPaths();
  redirect(`/admin/sync?ran=${runId}`);
}

export async function resolveUnmatchedAction(formData: FormData) {
  await requireAdmin();
  const unmatchedId = String(formData.get("unmatchedId") ?? "");
  const horseId = String(formData.get("horseId") ?? "");
  if (!unmatchedId || !horseId) return;
  resolveUnmatched(unmatchedId, horseId);
  bumpAllPaths();
}

export async function ignoreUnmatchedAction(formData: FormData) {
  await requireAdmin();
  const unmatchedId = String(formData.get("unmatchedId") ?? "");
  if (!unmatchedId) return;
  ignoreUnmatched(unmatchedId);
  bumpAllPaths();
}
