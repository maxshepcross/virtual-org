"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createOrReplaceEntrant } from "@/lib/queries";
import { PICK_COUNT, type EntryFormState } from "./constants";

export async function submitEntry(
  _prev: EntryFormState,
  formData: FormData,
): Promise<EntryFormState> {
  const name = String(formData.get("name") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const horseIds = formData.getAll("horseId").map(String);

  if (!name) return { error: "Please enter your name." };
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return { error: "Please enter a valid email address." };
  }
  if (horseIds.length !== PICK_COUNT) {
    return {
      error: `Please pick exactly ${PICK_COUNT} horses (you picked ${horseIds.length}).`,
    };
  }
  if (new Set(horseIds).size !== horseIds.length) {
    return { error: "You can't pick the same horse twice." };
  }

  let entrantId: string;
  try {
    const result = createOrReplaceEntrant(name, email, horseIds);
    entrantId = result.entrantId;
  } catch (err) {
    console.error("submitEntry failed", err);
    return { error: "Something went wrong saving your entry. Please try again." };
  }

  revalidatePath("/leaderboard");
  revalidatePath("/horses");
  revalidatePath("/");
  redirect(`/enter/thanks?id=${entrantId}`);
}
