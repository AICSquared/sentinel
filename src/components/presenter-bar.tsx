"use client";

// Slim bar on every page for live demos: jump between tracks without typing URLs.
// Keyboard: [ and ] go to the previous and next ready track, h goes home.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { tracks } from "@/lib/tracks";

export function PresenterBar() {
  const pathname = usePathname();
  const router = useRouter();
  const current = pathname.split("/")[1] ?? "";
  const shown = tracks.some((t) => t.ready) ? tracks.filter((t) => t.ready) : tracks;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (e.metaKey || e.ctrlKey || e.altKey || el?.closest("input, textarea, select, [contenteditable]")) return;
      const i = shown.findIndex((t) => t.slug === current);
      if (e.key === "h") router.push("/");
      if (e.key === "]") router.push(`/${shown[(i + 1) % shown.length].slug}`);
      if (e.key === "[") router.push(`/${shown[(i - 1 + shown.length) % shown.length].slug}`);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, router, shown]);

  if (current === "login") return null;
  return (
    <nav aria-label="Tracks" className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-5xl items-center gap-1 overflow-x-auto px-5 sm:px-8">
        <Link href="/" className="flex min-h-11 items-center pr-3 font-semibold">HackNCAT</Link>
        {shown.map((t) => (
          <Link
            key={t.slug}
            href={`/${t.slug}`}
            aria-current={t.slug === current ? "page" : undefined}
            className="flex min-h-11 items-center px-3 text-sm whitespace-nowrap text-ink-2 aria-[current=page]:font-semibold aria-[current=page]:text-accent"
          >
            {t.name}
          </Link>
        ))}
      </div>
    </nav>
  );
}
