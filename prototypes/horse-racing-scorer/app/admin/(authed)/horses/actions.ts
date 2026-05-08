"use server";

import { revalidatePath } from "next/cache";
import { isAdmin } from "@/lib/auth";
import { addHorse, bulkAddHorses, deleteHorse } from "@/lib/queries";

async function requireAdmin() {
  if (!(await isAdmin())) throw new Error("Unauthorized");
}

export async function addHorseAction(formData: FormData) {
  await requireAdmin();
  const name = String(formData.get("name") ?? "").trim();
  if (!name) return;
  try {
    addHorse(name);
  } catch (err) {
    console.error("addHorse failed", err);
  }
  revalidatePath("/admin/horses");
  revalidatePath("/horses");
  revalidatePath("/enter");
}

export async function bulkAddHorsesAction(formData: FormData) {
  await requireAdmin();
  const text = String(formData.get("names") ?? "");
  const names = text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  if (names.length === 0) return;
  bulkAddHorses(names);
  revalidatePath("/admin/horses");
  revalidatePath("/horses");
  revalidatePath("/enter");
}

export async function deleteHorseAction(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  if (!id) return;
  deleteHorse(id);
  revalidatePath("/admin/horses");
  revalidatePath("/horses");
  revalidatePath("/enter");
}
