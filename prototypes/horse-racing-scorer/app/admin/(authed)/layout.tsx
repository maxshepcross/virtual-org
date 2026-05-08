import { redirect } from "next/navigation";
import Link from "next/link";
import { isAdmin, adminPasswordConfigured } from "@/lib/auth";
import { signOutAction } from "../actions";

export const dynamic = "force-dynamic";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  if (!adminPasswordConfigured()) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
        <h1 className="text-xl font-semibold">Admin not configured</h1>
        <p className="mt-2 text-sm">
          Set <code className="rounded bg-amber-100 px-1">ADMIN_PASSWORD</code> in your
          environment (e.g. in <code className="rounded bg-amber-100 px-1">.env.local</code>) and restart the server.
        </p>
      </div>
    );
  }

  const ok = await isAdmin();
  if (!ok) redirect("/admin/login");

  return (
    <div className="space-y-6">
      <nav className="flex flex-wrap gap-x-4 gap-y-1 border-b border-stone-200 pb-2 text-sm">
        <Link href="/admin" className="font-semibold">Admin</Link>
        <Link href="/admin/horses" className="hover:underline">Horses</Link>
        <Link href="/admin/races" className="hover:underline">Races &amp; results</Link>
        <Link href="/admin/entrants" className="hover:underline">Entrants</Link>
        <form action={signOutAction} className="ml-auto">
          <button type="submit" className="text-stone-500 hover:underline">
            Sign out
          </button>
        </form>
      </nav>
      {children}
    </div>
  );
}
