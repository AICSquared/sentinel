// The incident, derived from the recorded run and nothing else: who turned when, who infected whom, and when a
// person decided. Every time, count and name the timeline shows comes from here, so a re-recorded run re-tells
// itself. No result numbers.
import type { RecommendedAction, Role } from "@/app/sentinel/_lib/contract";
import { spoken, type Story } from "./story";

/** 0 = behaving normally, 1 = slow it down (amber), 2 = flagged for a person's decision (quarantine or terminate). */
export type Tier = 0 | 1 | 2;
export const tierOf = (a: RecommendedAction): Tier => (a === "recommend_quarantine" || a === "recommend_terminate" ? 2 : a === "throttle" ? 1 : 0);

export type IncidentRow = { id: string; role: Role; tiers: Tier[]; risk: number[]; flaggedAt: number | null; peak: number };
export type IncidentFlag = { tick: number; kind: "turned" | "infected" | "approved"; text: string; time: string };
/** `to` turned at `tick`, after `from` had messaged it often enough (`messages`) that it counts as infected. */
export type IncidentArc = { from: string; to: string; tick: number; messages: number };
export type Incident = {
  ticks: number;
  times: string[]; // HH:MM:SS UTC per tick
  rows: IncidentRow[]; // patient zero first, then in the order they were flagged, then the rest
  flags: IncidentFlag[];
  arcs: IncidentArc[];
  approvedAt: number | null;
  title: string;
  body: string;
};

const seconds = (a: string, b: string) => Math.max(0, Math.round((Date.parse(b) - Date.parse(a)) / 1000));
const list = (names: string[]) => (names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);

export function buildIncident(story: Story): Incident {
  const n = story.ticks.length;
  const last = story.ticks[n - 1];
  const pz = story.patientZero?.id ?? null;

  const rows: IncidentRow[] = last.agents.map((a) => {
    const at = story.ticks.map((t) => t.agents.find((x) => x.id === a.id));
    const tiers = at.map((x) => (x ? tierOf(x.action) : 0));
    const risk = at.map((x) => x?.risk ?? 0);
    const flaggedAt = tiers.findIndex((t) => t === 2);
    return { id: a.id, role: a.role, tiers, risk, flaggedAt: flaggedAt < 0 ? null : flaggedAt, peak: Math.max(...risk) };
  });
  rows.sort((a, b) => {
    if (a.id === pz) return -1;
    if (b.id === pz) return 1;
    if (a.flaggedAt !== null && b.flaggedAt !== null) return a.flaggedAt - b.flaggedAt;
    if (a.flaggedAt !== null) return -1;
    if (b.flaggedAt !== null) return 1;
    return b.peak - a.peak || a.id.localeCompare(b.id);
  });

  const flaggedRows = rows.filter((r) => r.flaggedAt !== null).sort((a, b) => a.flaggedAt! - b.flaggedAt!);
  const flaggedAt = new Map(flaggedRows.map((r) => [r.id, r.flaggedAt!]));

  // Who infected whom: an agent that was flagged before the target and whose messages made the target count as
  // infected. The arc lands where the target turns, so the picture reads as cause then effect even when the
  // message count only crossed the infection rule a few seconds after the target was flagged.
  const arcs: IncidentArc[] = [];
  for (const r of flaggedRows) {
    if (r.id === pz) continue;
    for (let t = 0; t < n; t++) {
      const hit = story.ticks[t].links.find((l) => l.to === r.id && l.infected && flaggedAt.has(l.from) && flaggedAt.get(l.from)! <= r.flaggedAt!);
      if (hit) {
        arcs.push({ from: hit.from, to: r.id, tick: r.flaggedAt!, messages: hit.messages });
        break;
      }
    }
  }

  const approvedAt = story.ticks.findIndex((t) => t.containment === "approved");
  const flags: IncidentFlag[] = flaggedRows.map((r) => ({
    tick: r.flaggedAt!,
    kind: r.id === pz ? "turned" : "infected",
    text: `${spoken(r.id)} flagged`,
    time: story.ticks[r.flaggedAt!].time,
  }));
  if (approvedAt >= 0) flags.push({ tick: approvedAt, kind: "approved", text: "A person approves", time: story.ticks[approvedAt].time });
  flags.sort((a, b) => a.tick - b.tick);

  // The sentence: all of it measured off the recording.
  let title = "One agent turned.";
  let body = "";
  const first = pz ? flaggedAt.get(pz) : undefined;
  if (pz && first !== undefined) {
    title = `${spoken(pz)} turned.`;
    const delay = story.patientZero?.delayS;
    const others = flaggedRows.filter((r) => r.id !== pz);
    const lastFlag = flaggedRows[flaggedRows.length - 1].flaggedAt!;
    const parts = [`Sentinel flagged it ${delay == null ? "" : delay <= 0 ? "at once" : `in ${delay} s`}`.trim()];
    if (others.length) parts.push(`followed the infection to ${list(others.map((r) => spoken(r.id)))} within ${seconds(story.ticks[first].at, story.ticks[lastFlag].at)} s`);
    parts.push(
      approvedAt >= 0
        ? `a person approved ${seconds(story.ticks[first].at, story.ticks[approvedAt].at)} s after the first flag`
        : "a person was asked what to do",
    );
    body = `${parts.slice(0, -1).join(", ")}${parts.length > 1 ? ", and " : ""}${parts[parts.length - 1]}.`;
    body = body.charAt(0).toUpperCase() + body.slice(1);
  }

  return { ticks: n, times: story.ticks.map((t) => t.time), rows, flags, arcs, approvedAt: approvedAt < 0 ? null : approvedAt, title, body };
}
