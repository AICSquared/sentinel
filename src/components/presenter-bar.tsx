"use client";

// Site navigation on every page: the Sentinel mark, Overview, How it works, and the explorer.
// Presenter shortcut kept from the template: press h to go home (not while typing).
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/how-it-works", label: "How it works" },
];

function Mark() {
  return (
    <svg aria-hidden width="22" height="22" viewBox="0 0 22 22" fill="none" className="stroke-ink" strokeWidth={1.2}>
      <circle cx="11" cy="11" r="9.5" />
      <circle cx="11" cy="11" r="4.5" strokeDasharray="2 2" />
      <circle cx="11" cy="11" r="1.4" className="fill-crit" stroke="none" />
    </svg>
  );
}

export function PresenterBar() {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (e.metaKey || e.ctrlKey || e.altKey || el?.closest("input, textarea, select, [contenteditable]")) return;
      if (e.key === "h") router.push("/");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  if (pathname.startsWith("/login")) return null;
  const inExplorer = pathname.startsWith("/sentinel");
  return (
    <nav aria-label="Site" className="px-4 pt-5 sm:px-8 lg:px-16">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <Link href="/" className="mr-auto flex min-h-11 items-center gap-2.5 text-[17px] font-medium tracking-[-0.01em] text-ink">
          <Mark />
          Sentinel
        </Link>
        {LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            aria-current={pathname === l.href ? "page" : undefined}
            // On phones the Sentinel mark already links home, so "Overview" is dropped to keep one row.
            className={`${l.href === "/" ? "hidden sm:flex" : "flex"} min-h-11 items-center text-[15px] text-ink decoration-1 underline-offset-[6px] hover:underline aria-[current=page]:underline`}
          >
            {l.label}
          </Link>
        ))}
        <Link
          href="/sentinel"
          aria-current={inExplorer ? "page" : undefined}
          className="inline-flex min-h-11 items-center rounded-full bg-accent px-5 text-[15px] font-medium text-white hover:bg-accent-strong aria-[current=page]:bg-accent-strong"
        >
          Explorer
        </Link>
      </div>
    </nav>
  );
}
