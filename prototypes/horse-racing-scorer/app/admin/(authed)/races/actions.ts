"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { isAdmin } from "@/lib/auth";
import {
  clearRaceResults,
  createRace,
  deleteRace,
  setRaceResults,
} from "@/lib/queries";

async function requireAdmin() {
  if (!(await isAdmin())) throw new Error("Unauthorized");
}

export async function createRaceAction(formData: FormData) {
  await requireAdmin();
  const name = String(formData.get("name") ?? "").trim();
  const meeting = String(formData.get("meeting") ?? "").trim();
  const date = String(formData.get("date") ?? "").trim();
  if (!name || !date) return;
  const id = createRace({ name, meeting: meeting || undefined, date });
  revalidatePath("/admin/races");
  revalidatePath("/leaderboard");
  redirect(`/admin/races/${id}`);
}

export async function deleteRaceAction(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  if (!id) return;
  deleteRace(id);
  revalidatePath("/admin/races");
  revalidatePath("/leaderboard");
  revalidatePath("/horses");
}

export async function saveResultsAction(formData: FormData) {
  await requireAdmin();
  const raceId = String(formData.get("raceId") ?? "");
  if (!raceId) return;
  const first = String(formData.get("first") ?? "");
  const second = String(formData.get("second") ?? "");
  const third = String(formData.get("third") ?? "");
  const results: Array<{ position: 1 | 2 | 3; horseId: string }> = [];
  if (first) results.push({ position: 1, horseId: first });
  if (second) results.push({ position: 2, horseId: second });
  if (third) results.push({ position: 3, horseId: third });

  const ids = results.map((r) => r.horseId);
  if (new Set(ids).size !== ids.length) {
    redirect(`/admin/races/${raceId}?error=duplicate`);
  }

  setRaceResults(raceId, results);
  revalidatePath("/admin/races");
  revalidatePath(`/admin/races/${raceId}`);
  revalidatePath("/leaderboard");
  revalidatePath("/horses");
  revalidatePath("/");
  redirect(`/admin/races/${raceId}?saved=1`);
}

export async function clearResultsAction(formData: FormData) {
  await requireAdmin();
  const raceId = String(formData.get("raceId") ?? "");
  if (!raceId) return;
  clearRaceResults(raceId);
  revalidatePath(`/admin/races/${raceId}`);
  revalidatePath("/admin/races");
  revalidatePath("/leaderboard");
}
