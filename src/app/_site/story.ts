// Every fact the public pages show, derived from the recorded run (src/app/sentinel/_data/demo_timeline.json).
// Nothing here is typed in by hand: if the recording is re-made, the pages follow it. No results numbers
// (detection rates etc.) are shown anywhere until the validation runs exist.
import timelineJson from "@/app/sentinel/_data/demo_timeline.json";
import type { Containment, DemoTimeline, FleetAgent, FleetSnapshot, RecommendedAction, Role } from "@/app/sentinel/_lib/contract";

export type StoryAgent = { id: string; role: Role; x: number; y: number; risk: number; action: RecommendedAction };
export type StoryLink = { from: string; to: string; messages: number; infected: boolean };
export type StoryTick = {
  time: string; // HH:MM:SS UTC
  at: string; // full ISO timestamp, for the seconds between two ticks
  containment: Containment; // none -> recommended -> approved | dismissed (the human's click)
  agents: StoryAgent[];
  patientZero: string | null;
  /** patient zero's partners at this tick: message count and verdict */
  related: { id: string; messages: number; infected: boolean }[];
  /** every agent's partners at this tick: who it messaged, how often, and whether the partner counts as infected */
  links: StoryLink[];
};
export type Flagged = { id: string; role: Role; risk: number; action: RecommendedAction; reason: string };

export type Story = {
  ticks: StoryTick[];
  patientZero: { id: string; role: Role; origin: string | null; flagged: string | null; delayS: number | null; touchedDecoy: boolean } | null;
  partner: { id: string; role: Role; messages: number; risk: number } | null; // likely infected
  bystander: { id: string; role: Role; messages: number; risk: number } | null; // likely clean
  recommendation: { time: string; agents: Flagged[] } | null;
  agentCount: number;
  roles: Role[];
};

const ticks = (timelineJson as unknown as DemoTimeline).ticks;
const hms = (iso: string | null | undefined) => (iso ? iso.slice(11, 19) : null);
const rank: Record<RecommendedAction, number> = { monitor: 0, throttle: 1, recommend_quarantine: 2, recommend_terminate: 3 };

function toTick(s: FleetSnapshot): StoryTick {
  const pz = s.agents.find((a) => a.agent_id === s.sentinel.patient_zero);
  return {
    time: hms(s.updated) ?? "",
    at: s.updated,
    containment: s.sentinel.containment,
    patientZero: s.sentinel.patient_zero,
    agents: s.agents.map((a) => ({ id: a.agent_id, role: a.role, x: a.position.x, y: a.position.y, risk: a.risk, action: a.recommended_action })),
    related: (pz?.related_agents ?? []).map((r) => ({ id: r.agent_id, messages: r.messages, infected: r.verdict === "likely_infected" })),
    links: s.agents.flatMap((a) =>
      a.related_agents.map((r) => ({ from: a.agent_id, to: r.agent_id, messages: r.messages, infected: r.verdict === "likely_infected" })),
    ),
  };
}

export function buildStory(): Story {
  const last = ticks[ticks.length - 1];
  const byId = new Map<string, FleetAgent>(last.agents.map((a) => [a.agent_id, a]));
  const pzAgent = last.sentinel.patient_zero ? byId.get(last.sentinel.patient_zero) : undefined;
  const origin = last.sentinel.origin_ts;
  const flagged = pzAgent?.first_flagged_ts ?? null;
  const delayS = origin && flagged ? Math.max(0, Math.round((Date.parse(flagged) - Date.parse(origin)) / 1000)) : null;

  const rel = pzAgent?.related_agents ?? [];
  const inf = rel.find((r) => r.verdict === "likely_infected");
  const clean = rel.find((r) => r.verdict === "likely_clean");
  const who = (id: string | undefined, messages: number) => {
    const a = id ? byId.get(id) : undefined;
    return a ? { id: a.agent_id, role: a.role, messages, risk: a.risk } : null;
  };

  // The recommendation as it stood once the final set of flagged agents was reached.
  const flaggedNow = last.agents.filter((a) => rank[a.recommended_action] >= 2).sort((a, b) => b.risk - a.risk);
  const key = (s: FleetSnapshot) => s.agents.filter((a) => rank[a.recommended_action] >= 2).map((a) => a.agent_id).sort().join(",");
  const firstSame = ticks.find((s) => key(s) === key(last));

  return {
    ticks: ticks.map(toTick),
    patientZero: pzAgent
      ? {
          id: pzAgent.agent_id,
          role: pzAgent.role,
          origin: hms(origin),
          flagged: hms(flagged),
          delayS,
          touchedDecoy: pzAgent.systems_touched.some((s) => s.startsWith("decoy:")),
        }
      : null,
    partner: inf ? who(inf.agent_id, inf.messages) : null,
    bystander: clean ? who(clean.agent_id, clean.messages) : null,
    recommendation: flaggedNow.length
      ? {
          time: hms(firstSame?.updated) ?? hms(last.updated) ?? "",
          agents: flaggedNow.map((a) => ({ id: a.agent_id, role: a.role, risk: a.risk, action: a.recommended_action, reason: a.reason })),
        }
      : null,
    agentCount: last.agents.length,
    roles: [...new Set(last.agents.map((a) => a.role))],
  };
}

/** "agent-47" -> "Agent 47" for headlines. */
export const spoken = (id: string) => id.replace(/^agent-/, "Agent ");
