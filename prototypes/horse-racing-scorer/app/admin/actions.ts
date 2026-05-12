"use server";

import { redirect } from "next/navigation";
import { signOutAdmin } from "@/lib/auth";

export async function signOutAction() {
  await signOutAdmin();
  redirect("/admin/login");
}
