import { redirect } from "next/navigation";
import { isAdmin, signInAdmin, adminPasswordConfigured } from "@/lib/auth";

export const dynamic = "force-dynamic";

type Props = { searchParams: Promise<{ error?: string }> };

export default async function AdminLoginPage({ searchParams }: Props) {
  if (!adminPasswordConfigured()) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
        <h1 className="text-xl font-semibold">Admin not configured</h1>
        <p className="mt-2 text-sm">
          Set <code className="rounded bg-amber-100 px-1">ADMIN_PASSWORD</code> in your environment.
        </p>
      </div>
    );
  }
  if (await isAdmin()) redirect("/admin");

  const { error } = await searchParams;

  async function login(formData: FormData) {
    "use server";
    const password = String(formData.get("password") ?? "");
    const ok = await signInAdmin(password);
    if (!ok) redirect("/admin/login?error=1");
    redirect("/admin");
  }

  return (
    <div className="mx-auto max-w-sm rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-bold">Admin sign in</h1>
      <form action={login} className="mt-4 space-y-3">
        <label className="block">
          <span className="text-sm font-medium">Password</span>
          <input
            type="password"
            name="password"
            required
            autoFocus
            className="mt-1 block w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-stone-500 focus:outline-none"
          />
        </label>
        {error && (
          <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
            Wrong password.
          </p>
        )}
        <button
          type="submit"
          className="w-full rounded-md bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-700"
        >
          Sign in
        </button>
      </form>
    </div>
  );
}
