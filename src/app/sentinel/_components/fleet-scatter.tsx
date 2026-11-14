import { Card } from "@/components/ui";
import type { AgentStatus, RecommendedAction } from "../_lib/contract";
import { type Agent, isFlagged, TierDot, tierMeta } from "./tier";

const LEGEND: RecommendedAction[] = ["monitor", "throttle", "recommend_quarantine", "recommend_terminate"];

const LABEL_STEP_PX = 24; // one label's height plus a gap
const NEAR_X = 0.3; // labels this close sideways and ...
const NEAR_Y = 0.14; // ... this close vertically would overlap

/**
 * Several infected agents end up almost on the same spot, and their labels pile on top of each other.
 * Walk the labelled agents top to bottom; each one drops one step below every earlier label near it.
 * Dots keep their true positions; only the text moves, and it still starts with the agent id.
 */
export function labelSlots(agents: Agent[], labelled: (a: Agent) => boolean): Map<string, number> {
  const placed: { id: string; x: number; y: number; slot: number }[] = [];
  const order = agents.filter(labelled).sort((a, b) => b.position.y - a.position.y || a.agent_id.localeCompare(b.agent_id));
  for (const a of order) {
    const taken = new Set(
      placed
        .filter((p) => Math.abs(p.x - a.position.x) < NEAR_X && Math.abs(p.y - a.position.y) < NEAR_Y)
        .map((p) => p.slot),
    );
    let slot = 0;
    while (taken.has(slot)) slot += 1;
    placed.push({ id: a.agent_id, x: a.position.x, y: a.position.y, slot });
  }
  return new Map(placed.map((p) => [p.id, p.slot]));
}

/**
 * Each agent is a dot placed from its `position` (0..1). Normal agents sit together; a rogue drifts out.
 * The only motion on the page besides the headline numbers: dots glide to their new spot between ticks.
 */
export function FleetScatter({
  agents,
  patientZero,
  selectedId = null,
  onSelect,
  statusOf = () => "active",
}: {
  agents: Agent[];
  patientZero: string | null;
  /** #53: click a dot to pick that agent (each dot is a 44 px button); the picked dot is outlined. */
  selectedId?: string | null;
  onSelect?: (agentId: string) => void;
  statusOf?: (agentId: string) => AgentStatus;
}) {
  const unusual = agents.filter((a) => a.recommended_action !== "monitor").length;
  const isLabelled = (a: Agent) =>
    a.recommended_action !== "monitor" || a.agent_id === patientZero || a.agent_id === selectedId || statusOf(a.agent_id) !== "active";
  const slots = labelSlots(agents, isLabelled);
  return (
    <Card className="flex flex-col">
      <h2 className="text-lg font-semibold">Where each agent&apos;s last minute of behaviour sits</h2>
      <p className="mt-1 text-sm text-ink-2">
        Agents that behave alike sit together. {unusual === 0 ? "All agents are in the normal group." : `${unusual} moved away from the group.`}
      </p>

      <div
        role={onSelect ? "group" : "img"}
        aria-label={`Behaviour map of ${agents.length} agents. ${unusual} outside the normal group.${onSelect ? " Pick a dot to see that agent." : ""}`}
        className="relative mt-4 min-h-72 flex-1 overflow-hidden rounded-[var(--radius-control)] border border-line bg-ground"
      >
        {agents.map((a) => {
          const m = tierMeta[a.recommended_action];
          const labelled = isLabelled(a);
          const flipLabel = a.position.x > 0.4; // labels are long ("agent-53 · risk 100 · Terminate?"); flip early so none clip
          const slot = slots.get(a.agent_id) ?? 0;
          return (
            <div
              key={a.agent_id}
              title={`${a.agent_id}: risk ${a.risk}, ${m.label}`}
              style={{ left: `${a.position.x * 100}%`, top: `${(1 - a.position.y) * 100}%` }}
              className="absolute size-0 transition-[left,top] duration-1000 ease-out motion-reduce:transition-none"
            >
              {onSelect ? (
                <button
                  type="button"
                  onClick={() => onSelect(a.agent_id)}
                  aria-pressed={a.agent_id === selectedId}
                  aria-label={`${a.agent_id}, risk ${a.risk}, ${m.label}${statusOf(a.agent_id) !== "active" ? `, ${statusOf(a.agent_id)}` : ""}`}
                  className={`absolute flex size-11 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full ${a.agent_id === selectedId ? "ring-2 ring-accent" : ""} ${statusOf(a.agent_id) === "terminated" ? "opacity-40" : ""} ${statusOf(a.agent_id) === "quarantined" ? "outline-2 outline-offset-[-10px] outline-warn outline-dashed" : ""}`}
                >
                  <TierDot action={a.recommended_action} />
                </button>
              ) : (
                <span className="absolute -translate-x-1/2 -translate-y-1/2">
                  <TierDot action={a.recommended_action} />
                </span>
              )}
              {labelled && slot > 0 && (
                // Leader line from the dot down to its moved label, so a stacked label still names its own dot.
                <span aria-hidden className="absolute top-0 left-0 w-px bg-ink-3" style={{ height: slot * LABEL_STEP_PX }} />
              )}
              {labelled && (
                // When dots overlap (infected agents drift to the same spot), the labels are still stacked apart,
                // so a label click picks its own agent. Mouse shortcut only: the dot button above is the
                // keyboard and screen-reader control, so this one is skipped by Tab and hidden from assistive tech.
                <span
                  role={onSelect ? "presentation" : undefined}
                  aria-hidden={onSelect ? true : undefined}
                  onClick={onSelect ? () => onSelect(a.agent_id) : undefined}
                  style={{ marginTop: slot * LABEL_STEP_PX }}
                  className={`absolute top-0 -translate-y-1/2 rounded-[var(--radius-tag)] bg-surface px-1.5 py-0.5 text-xs font-medium whitespace-nowrap text-ink ${flipLabel ? "right-0 mr-3" : "left-0 ml-3"} ${onSelect ? "cursor-pointer hover:bg-info-bg" : ""} ${a.agent_id === selectedId ? "ring-1 ring-accent" : ""}`}
                >
                  {a.agent_id} · risk {a.risk} · {statusOf(a.agent_id) === "active" ? m.label : `${statusOf(a.agent_id)} by you`}
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
