import { Card } from "@/components/ui";
import type { RecommendedAction } from "../_lib/contract";
import { type Agent, isFlagged, TierDot, tierMeta } from "./tier";

const LEGEND: RecommendedAction[] = ["monitor", "throttle", "recommend_quarantine", "recommend_terminate"];

/**
 * Each agent is a dot placed from its `position` (0..1). Normal agents sit together; a rogue drifts out.
 * The only motion on the page besides the headline numbers: dots glide to their new spot between ticks.
 */
export function FleetScatter({ agents, patientZero }: { agents: Agent[]; patientZero: string | null }) {
  const unusual = agents.filter((a) => a.recommended_action !== "monitor").length;
  return (
    <Card className="flex flex-col">
      <h2 className="text-lg font-semibold">Where each agent&apos;s last minute of behaviour sits</h2>
      <p className="mt-1 text-sm text-ink-2">
        Agents that behave alike sit together. {unusual === 0 ? "All agents are in the normal group." : `${unusual} moved away from the group.`}
      </p>

      <div
        role="img"
        aria-label={`Behaviour map of ${agents.length} agents. ${unusual} outside the normal group.`}
        className="relative mt-4 min-h-72 flex-1 overflow-hidden rounded-[var(--radius-control)] border border-line bg-ground"
      >
        {agents.map((a) => {
          const m = tierMeta[a.recommended_action];
          const labelled = a.recommended_action !== "monitor" || a.agent_id === patientZero;
          const flipLabel = a.position.x > 0.7;
          return (
            <div
              key={a.agent_id}
              title={`${a.agent_id}: risk ${a.risk}, ${m.label}`}
              style={{ left: `${a.position.x * 100}%`, top: `${(1 - a.position.y) * 100}%` }}
              className="absolute size-0 transition-[left,top] duration-1000 ease-out motion-reduce:transition-none"
            >
              <span className="absolute -translate-x-1/2 -translate-y-1/2">
                <TierDot action={a.recommended_action} />
              </span>
              {labelled && (
                <span
                  className={`absolute top-0 -translate-y-1/2 rounded-[var(--radius-tag)] bg-surface px-1.5 py-0.5 text-xs font-medium whitespace-nowrap text-ink ${flipLabel ? "right-0 mr-3" : "left-0 ml-3"}`}
                >
                  {a.agent_id} · risk {a.risk} · {m.label}
                </span>
              )}
            </div>
          );
        })}
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-sm text-ink-2">
        {LEGEND.map((action) => (
          <li key={action} className="flex items-center gap-2">
            <TierDot action={action} />
            {tierMeta[action].label}
          </li>
        ))}
      </ul>

      <ul className="sr-only">
        {agents.map((a) => (
          <li key={a.agent_id}>
            {a.agent_id}, {a.role}, risk {a.risk}, {tierMeta[a.recommended_action].label}
            {isFlagged(a) ? ", needs a decision" : ""}
          </li>
        ))}
      </ul>
    </Card>
  );
}
