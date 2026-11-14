import { Card } from "@/components/ui";

const SHOWN = 12;

/** The newest events, oldest first, newest last. Each line is "HH:MM:SS  text" (UTC). */
export function EventLog({ events }: { events: string[] }) {
  const lines = events.slice(-SHOWN);
  return (
    <Card>
      <h2 className="text-lg font-semibold">What Sentinel saw</h2>
      {lines.length === 0 ? (
        <p className="mt-1 text-ink-2">Nothing unusual so far.</p>
      ) : (
        <ol role="log" aria-label="Sentinel events, newest last" className="mt-3 flex flex-col gap-1.5 font-mono text-[13px] leading-snug text-ink-2">
          {lines.map((line, i) => (
            <li key={`${i}-${line}`} className="whitespace-pre-wrap">
              {line}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
