import Link from "next/link";
import { Page, PageHeader, Tag } from "@/components/ui";
import { tracks } from "@/lib/tracks";

export default function Home() {
  const ready = tracks.filter((t) => t.ready).length;
  return (
    <Page>
      <PageHeader
        meta="HackNCAT · AICSquared"
        title={ready ? `${ready} of ${tracks.length} sponsor tracks are ready to demo.` : "Pick a sponsor track."}
      />
      <ul className="grid grid-cols-[repeat(auto-fit,minmax(min(260px,100%),1fr))] gap-4">
        {tracks.map((t) => (
          <li key={t.slug}>
            <Link
              href={`/${t.slug}`}
              className="flex h-full min-h-28 flex-col gap-2 rounded-[var(--radius-card)] bg-surface p-6 hover:outline hover:outline-2 hover:outline-accent"
            >
              <span className="text-xl font-semibold">{t.name}</span>
              <span className="w-fit">
                <Tag severity={t.ready ? "Done" : "Info"}>{t.ready ? "Ready" : "In progress"}</Tag>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Page>
  );
}
