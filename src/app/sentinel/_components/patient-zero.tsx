import { Card } from "@/components/ui";
import { type Agent, clock, secondsBetween } from "./tier";

/** The first agent to reach risk 75: when it started, what it did, what it touched. */
export function PatientZero({ agent, originTs }: { agent: Agent | null; originTs: string | null }) {
  if (!agent) {
    return (
      <Card>
        <h2 className="text-lg font-semibold">No patient zero yet</h2>
        <p className="mt-1 text-ink-2">Sentinel scores every agent every 2 seconds and names the first one to reach risk 75.</p>
      </Card>
    );
  }
  const delay = secondsBetween(originTs, agent.first_flagged_ts);
  return (
    <Card>
      <h2 className="text-xl leading-snug font-semibold">
        Patient zero: {agent.agent_id}, flagged{" "}
        {delay === null ? "after its first bad action" : `${delay} s after its first bad action`}
      </h2>
      <p className="mt-2 text-ink-2">{agent.reason}</p>
      <dl className="mt-5 grid gap-x-8 gap-y-4 sm:grid-cols-2">
        <div>
          <dt className="text-sm text-ink-3">First bad action</dt>
          <dd className="mt-0.5 font-mono text-[15px] tabular-nums">{clock(originTs)}</dd>
        </div>
        <div>
          <dt className="text-sm text-ink-3">Requests this run</dt>
          <dd className="mt-0.5 font-mono text-[15px] tabular-nums">{agent.requests}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-sm text-ink-3">Systems touched, newest first</dt>
          <dd className="mt-1.5">
            <ul className="flex flex-wrap gap-2">
              {agent.systems_touched.map((s) => (
                <li
                  key={s}
                  className={`rounded-[var(--radius-tag)] px-2 py-1 font-mono text-[13px] ${s.startsWith("decoy:") ? "bg-crit-bg text-crit-tag" : "bg-info-bg text-ink-2"}`}
                >
                  {s}
                  {s.startsWith("decoy:") && <span className="font-sans"> (decoy)</span>}
                </li>
              ))}
            </ul>
          </dd>
        </div>
      </dl>
    </Card>
  );
}
