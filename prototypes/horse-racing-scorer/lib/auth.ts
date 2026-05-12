import { cookies } from "next/headers";

const COOKIE_NAME = "hrs_admin";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 30;

function adminPassword(): string | null {
  const pw = process.env.ADMIN_PASSWORD;
  return pw && pw.length > 0 ? pw : null;
}

export async function isAdmin(): Promise<boolean> {
  const expected = adminPassword();
  if (!expected) return false;
  const store = await cookies();
  return store.get(COOKIE_NAME)?.value === expected;
}

export async function signInAdmin(password: string): Promise<boolean> {
  const expected = adminPassword();
  if (!expected || password !== expected) return false;
  const store = await cookies();
  store.set(COOKIE_NAME, expected, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: COOKIE_MAX_AGE,
    secure: process.env.NODE_ENV === "production",
  });
  return true;
}

export async function signOutAdmin(): Promise<void> {
  const store = await cookies();
  store.delete(COOKIE_NAME);
}

export function adminPasswordConfigured(): boolean {
  return adminPassword() !== null;
}
