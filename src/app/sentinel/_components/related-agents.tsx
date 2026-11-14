import { Card, Tag } from "@/components/ui";
import type { RelatedAgent } from "../_lib/contract";
import type { Agent } from "./tier";

/** Who the selected agent messaged in the last 5 minutes, and which partners look infected. */
export function RelatedAgents({ sourceId, related, agents }: { sourceId: string | null; related: RelatedAgent[]; agents: Agent[] }) {
  if (!sourceId || related.length === 0) {
    return (
      <Card>
        <h2 className="text-lg font-semibold">Spread</h2>
        <p className="mt-1 text-ink-2">No agent has been flagged, so there is no spread to trace.</p>
      </Card>
    );
  }
  const infected = related.filter((r) => r.verdict === "likely_infected").length;
  const most = Math.max(...related.map((r) => r.messages));
  const riskOf = new Map(agents.map((a) => [a.agent_id, a.risk]));
  return (
    <Card>
      <h2 className="text-lg font-semibold">
        {sourceId} messaged {related.length} {related.length === 1 ? "agent" : "agents"} in the last 5 minutes
      </h2>
      <p className="mt-1 text-ink-2">
        {infected === 0 ? "None look infected." : `${infected} ${infected === 1 ? "looks" : "look"} infected.`} Infected means 10 or more
        messages and a risk of 40 or more.
      </p>
      <ul className="mt-4 divide-y divide-line">
        {related.map((r) => (
          <li key={r.agent_id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
            <span className="w-20 font-mono text-[15px]">{r.agent_id}</span>
            <span className="w-28 text-sm text-ink-2 tabular-nums">
              {r.messages} {r.messages === 1 ? "message" : "messages"}
            </span>
            <span aria-hidden className="h-1.5 min-w-16 flex-1 rounded-full bg-line">
              <span
                className={`block h-full rounded-full ${r.verdict === "likely_infected" ? "bg-crit" : "bg-ink-3"}`}
                style={{ width: `${Math.max(4, (r.messages / most) * 100)}%` }}
              />
            </span>
            <span className="w-16 text-sm text-ink-3 tabular-nums">risk {riskOf.get(r.agent_id) ?? "?"}</span>
            <Tag severity={r.verdict === "likely_infected" ? "Critical" : "Info"}>
              {r.verdict === "likely_infected" ? "Likely infected" : "Likely clean"}
            </Tag>
          </li>
        ))}
      </ul>
    </Card>
  );
}
