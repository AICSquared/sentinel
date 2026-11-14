"use server";

import { revalidatePath } from "next/cache";
import { getUser } from "@/lib/supabase/server";
import { hasSupabase } from "@/lib/supabase/env";
import { sendAlert } from "./_lib/alert";
import { writeAudit, type AuditEntry } from "./_lib/audit";
import { ACTIONS, ATTACK_TYPES, type AttackType, type Decision, type RecommendedAction } from "./_lib/contract";
import { ACTION_LABEL, isAgentId, needsHuman } from "./_lib/response";

// Human-gated response. These actions RECORD recommendations and human decisions; they never
// quarantine, throttle or stop anything. Enforcement stays with a person (docker/quarantine.sh).

export type FlaggedAgent = {
  agent_id: string;
  risk: number;
  attack_type: AttackType;
  recommended_action: RecommendedAction;
  reason: string;
};

export type ActionResult = { audited: number; alerted: boolean; note: string };

const MAX_AGENTS = 16;

function clean(agents: unknown): FlaggedAgent[] {
  if (!Array.isArray(agents)) return [];
  return agents
    .slice(0, MAX_AGENTS)
    .filter(
      (a): a is FlaggedAgent =>
        typeof a === "object" &&
        a !== null &&
        isAgentId(a.agent_id) &&
        Number.isFinite(a.risk) &&
        (ATTACK_TYPES as readonly string[]).includes(a.attack_type) &&
        (ACTIONS as readonly string[]).includes(a.recommended_action) &&
        typeof a.reason === "string",
    )
    .map((a) => ({ ...a, risk: Math.max(0, Math.min(100, Math.round(a.risk))), reason: a.reason.slice(0, 300) }));
}

const plain = (t: AttackType) => t.replace(/_/g, " ");
const list = (agents: FlaggedAgent[]) => agents.map((a) => `${a.agent_id} (risk ${a.risk}, ${plain(a.attack_type)})`).join(", ");

function note(audit: { written: number; skipped: boolean; error?: string }, alerted: boolean) {
  if (audit.error) return `Audit log write failed: ${audit.error}`;
  if (audit.skipped) return "Demo mode: nothing written to the audit log.";
  return `Logged ${audit.written} row${audit.written === 1 ? "" : "s"}${alerted ? " and alerted the team" : ""}.`;
}

/**
 * Sentinel's own recommendation, recorded the first time the dashboard sees it.
 * `source: "demo"` (timeline playback) never writes: recorded data must come from a live run.
 */
export async function recordRecommendation(input: { agents: unknown; source: "live" | "demo" }): Promise<ActionResult> {
  const agents = clean(input?.agents).filter((a) => needsHuman(a.recommended_action));
  if (agents.length === 0) return { audited: 0, alerted: false, note: "Nothing to record." };
  if (input.source !== "live") return { audited: 0, alerted: false, note: "Demo playback: not recorded." };

  const rows: AuditEntry[] = agents.map((a) => ({
    agent_id: a.agent_id,
    risk: a.risk,
    attack_type: a.attack_type,
    action: a.recommended_action,
    decided_by: "sentinel",
    detail: { reason: a.reason },
  }));
  const audit = await writeAudit(rows);
  const alert = await sendAlert(
    `Sentinel recommends: ${agents.map((a) => `${ACTION_LABEL[a.recommended_action].toLowerCase()} ${a.agent_id}`).join(", ")}. ` +
      `${list(agents)}. Reason: ${agents[0].reason} Approve or dismiss on the dashboard; nothing happens until a human decides.`,
  );
  return { audited: audit.written, alerted: alert.sent, note: note(audit, alert.sent) };
}

/** A human approves or dismisses Sentinel's recommendation for one or more agents. */
export async function decide(input: { agents: unknown; decision: Decision; source: "live" | "demo" }): Promise<ActionResult> {
  const agents = clean(input?.agents);
  const decision = input?.decision;
  if (agents.length === 0 || (decision !== "approved" && decision !== "dismissed")) {
    return { audited: 0, alerted: false, note: "Nothing to decide." };
  }
  if (input.source !== "live") return { audited: 0, alerted: false, note: `Demo playback: ${decision}, not recorded.` };

  const user = hasSupabase ? await getUser() : null;
  const by = user?.email ?? user?.id ?? "presenter";
  const rows: AuditEntry[] = agents.map((a) => ({
    agent_id: a.agent_id,
    risk: a.risk,
    attack_type: a.attack_type,
    action: decision,
    decided_by: by,
    detail: { recommended_action: a.recommended_action, reason: a.reason },
  }));
  const audit = await writeAudit(rows);
  // Name what was actually recommended for each agent (quarantine vs terminate), not a fixed word.
  const what = agents.map((a) => `${ACTION_LABEL[a.recommended_action].toLowerCase()} ${a.agent_id} (risk ${a.risk}, ${plain(a.attack_type)})`).join(", ");
  const verb = decision === "approved" ? "APPROVED" : "DISMISSED the recommendation to";
  // The audit row names the person; the Discord message doesn't, so no email leaves our database.
  const alert = await sendAlert(
    `${user ? "A signed-in operator" : "The presenter"} ${verb} ${what}.` + (decision === "approved" ? " A person acts on it with docker/quarantine.sh." : ""),
  );
  revalidatePath("/sentinel");
  return { audited: audit.written, alerted: alert.sent, note: note(audit, alert.sent) };
}
