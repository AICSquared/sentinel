import { Kpi } from "@/components/kpi";
import type { FleetSnapshot } from "../_lib/contract";
import { isFlagged, secondsBetween } from "./tier";

/** The four numbers that animate, with one plain sentence above them. Nothing else on the page counts up. */
export function FleetHeadline({ agents, sentinel }: { agents: FleetSnapshot["agents"]; sentinel: FleetSnapshot["sentinel"] }) {
  const flagged = agents.filter(isFlagged).length;
  const peak = agents.reduce((m, a) => Math.max(m, a.risk), 0);
  const zero = agents.find((a) => a.agent_id === sentinel.patient_zero);
  const detect = secondsBetween(sentinel.origin_ts, zero?.first_flagged_ts ?? null);

  return (
    <section aria-labelledby="fleet-headline" className="flex flex-col gap-4">
      <h2 id="fleet-headline" className="text-[clamp(22px,3vw,28px)] leading-tight font-semibold tracking-tight">
        {agents.length} agents watched, {flagged === 0 ? "none flagged" : `${flagged} flagged`}
        {sentinel.patient_zero && `. Patient zero is ${sentinel.patient_zero}.`}
      </h2>
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-[var(--radius-card)] bg-line lg:grid-cols-4">
        <Kpi label="Agents watched" value={agents.length} />
        <Kpi label="Agents flagged" value={flagged} note="Risk 75 or higher" />
        <Kpi label="Peak risk" value={peak} suffix="/ 100" note="Highest agent right now" />
        <Kpi
          label="Time to detect"
          value={detect ?? 0}
          suffix="s"
          note={detect === null ? "No attack detected" : "First bad action to first flag"}
        />
      </div>
    </section>
  );
}
