// Tiered, human-gated response policy. Pure functions only: safe on server and client.
// Every tier is a RECOMMENDATION. Nothing in this file (or anywhere in Sentinel) enforces
// anything; a human approves or dismisses, and that decision goes to the audit log.

import type { Severity } from "@/components/ui";
import { TIERS, type FleetAgent, type FleetSnapshot, type RecommendedAction } from "./contract";

/** Tier table lookup, same as contract.py action_for(). Risk is clamped to 0-100. */
export function actionFor(risk: number): RecommendedAction {
  const r = Math.max(0, Math.min(100, Math.round(risk)));
  return (TIERS.find((t) => r >= t.min && r <= t.max) ?? TIERS[0]).action;
}

/** Plain words for each tier, for headlines and buttons. */
export const ACTION_LABEL: Record<RecommendedAction, string> = {
  monitor: "Monitor",
  throttle: "Slow down",
  recommend_quarantine: "Quarantine",
  recommend_terminate: "Terminate",
};

/** Tag colour per tier. Text always sits next to the colour, so colour is never the only signal. */
export const ACTION_SEVERITY: Record<RecommendedAction, Severity> = {
  monitor: "Done",
  throttle: "Warning",
  recommend_quarantine: "Critical",
  recommend_terminate: "Critical",
};

/** Tiers that need a human click (approve / dismiss). */
export function needsHuman(action: RecommendedAction): boolean {
  return action === "recommend_quarantine" || action === "recommend_terminate";
}

/** Agents Sentinel currently recommends quarantining or terminating, riskiest first. */
export function pendingRecommendations(snapshot: FleetSnapshot): FleetAgent[] {
  return snapshot.agents.filter((a) => needsHuman(a.recommended_action)).sort((a, b) => b.risk - a.risk);
}

/** Agents to slow down (throttle tier), riskiest first. */
export function throttled(snapshot: FleetSnapshot): FleetAgent[] {
  return snapshot.agents.filter((a) => a.recommended_action === "throttle").sort((a, b) => b.risk - a.risk);
}

/** Seconds between patient zero's first bad action and its first recommendation; null until both exist. */
export function secondsToDetect(snapshot: FleetSnapshot): number | null {
  const pz = snapshot.agents.find((a) => a.agent_id === snapshot.sentinel.patient_zero);
  if (!pz?.first_flagged_ts || !snapshot.sentinel.origin_ts) return null;
  const s = (Date.parse(pz.first_flagged_ts) - Date.parse(snapshot.sentinel.origin_ts)) / 1000;
  return Number.isFinite(s) && s >= 0 ? s : null;
}

/** One-line headline in plain words. */
export function headline(snapshot: FleetSnapshot): string {
  const pending = pendingRecommendations(snapshot);
  const n = snapshot.agents.length;
  if (pending.length === 0) {
    const slow = throttled(snapshot).length;
    return slow ? `${slow} of ${n} agents acting unusually. Watching closely.` : `${n} agents working normally.`;
  }
  const ids = pending.map((a) => a.agent_id).join(" and ");
  return `${ids} ${pending.length === 1 ? "looks" : "look"} compromised. Sentinel recommends quarantine; a human decides.`;
}

const AGENT_ID = /^agent-\d{1,4}$/;
export const isAgentId = (s: unknown): s is string => typeof s === "string" && AGENT_ID.test(s);
