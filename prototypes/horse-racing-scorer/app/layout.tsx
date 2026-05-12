import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "15 To Follow",
  description: "Pick 15 horses, score points across the UK racing season.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-stone-50 text-stone-900">
        <header className="border-b border-stone-200 bg-white">
          <nav className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 text-sm">
            <Link href="/" className="font-semibold tracking-tight">
              15 To Follow
            </Link>
            <Link href="/enter" className="hover:underline">Enter</Link>
            <Link href="/leaderboard" className="hover:underline">Leaderboard</Link>
            <Link href="/horses" className="hover:underline">Horses</Link>
            <Link href="/admin" className="ml-auto text-stone-500 hover:underline">Admin</Link>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">{children}</main>
        <footer className="border-t border-stone-200 bg-white">
          <div className="mx-auto max-w-5xl px-4 py-4 text-xs text-stone-500">
            10 / 5 / 3 points for 1st / 2nd / 3rd in qualifying races.
          </div>
        </footer>
      </body>
    </html>
  );
}
