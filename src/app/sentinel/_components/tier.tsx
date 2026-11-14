// Shared tier look for the Sentinel dashboard: one place maps recommended_action to a label, tag and dot.
import type { Severity } from "@/components/ui";
import type { FleetSnapshot, RecommendedAction } from "../_lib/contract";

export type Agent = FleetSnapshot["agents"][number];

export const tierMeta: Record<RecommendedAction, { label: string; severity: Severity; dot: string; rank: number }> = {
  monitor: { label: "Normal", severity: "Info", dot: "bg-ink-3", rank: 0 },
  throttle: { label: "Slow down?", severity: "Warning", dot: "bg-warn", rank: 1 },
  recommend_quarantine: { label: "Quarantine?", severity: "Critical", dot: "bg-crit", rank: 2 },
  recommend_terminate: {
    label: "Terminate?",
    severity: "Critical",
    dot: "bg-crit ring-2 ring-crit ring-offset-2 ring-offset-surface",
    rank: 3,
  },
};

/** An agent the human has to decide about (quarantine tier or above). */
export const isFlagged = (a: Pick<Agent, "recommended_action">) => tierMeta[a.recommended_action].rank >= 2;

export function TierDot({ action }: { action: RecommendedAction }) {
  return <span aria-hidden className={`inline-block size-3.5 shrink-0 rounded-full ${tierMeta[action].dot}`} />;
}

/** "06:00:12 UTC" from an ISO timestamp, without touching the viewer's time zone. */
export function clock(iso: string | null): string {
  return iso ? `${iso.slice(11, 19)} UTC` : "not yet";
}

/** Whole seconds from one ISO timestamp to another, or null if either is missing. */
export function secondsBetween(from: string | null, to: string | null): number | null {
  if (!from || !to) return null;
  const s = (Date.parse(to) - Date.parse(from)) / 1000;
  return Number.isFinite(s) ? Math.max(0, Math.round(s)) : null;
}
