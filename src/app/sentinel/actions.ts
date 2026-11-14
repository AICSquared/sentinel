"use server";

import { revalidatePath } from "next/cache";
import { getUser } from "@/lib/supabase/server";
import { hasSupabase } from "@/lib/supabase/env";
import { sendAlert } from "./_lib/alert";
import { writeAudit, type AuditEntry } from "./_lib/audit";
import {
  ACTIONS,
  AGENT_ACTIONS,
  AGENT_STATUSES,
  ATTACK_TYPES,
  type AgentAction,
  type AgentStatus,
  type AttackType,
  type Decision,
  type RecommendedAction,
} from "./_lib/contract";
import { ACTION_LABEL, isAgentId, needsHuman } from "./_lib/response";

// Human-gated response. Sentinel only RECOMMENDS. The one thing here that changes an agent is
// actOnAgents, and it runs only when a person clicks Quarantine / Terminate / Release (#53).
// Every click is written to the insert-only audit log. The audit row records the user's id
// (never their email: anyone holding the publishable key can read the table).

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
  const by = user?.id ?? "presenter";
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

// ---------------------------------------------------------------- per-agent actions (#53)

export type AgentActionResult = ActionResult & {
  /** The overseer's status for each agent it accepted; missing when it refused or wasn't reachable. */
  statuses: Record<string, AgentStatus>;
};

const PAST: Record<AgentAction, string> = {
  quarantine: "QUARANTINED",
  terminate: "TERMINATED",
  release: "RELEASED",
  dismiss: "DISMISSED the alert for",
};

// Server-side call to the overseer, so the browser never needs CORS or the overseer's address.
// The URL comes only from env, never from the request.
const OVERSEER_URL = (process.env.SENTINEL_API_URL || process.env.NEXT_PUBLIC_SENTINEL_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function tellOverseer(agentId: string, action: AgentAction, by: string): Promise<AgentStatus | string> {
  try {
    const res = await fetch(`${OVERSEER_URL}/agents/${encodeURIComponent(agentId)}/action`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action, by }),
      signal: AbortSignal.timeout(2500),
      cache: "no-store",
    });
    if (!res.ok) {
      const why = res.status === 404 ? "unknown agent or an overseer without the action endpoint" : res.status === 409 ? "nothing to change" : `HTTP ${res.status}`;
      return `overseer refused (${why})`;
    }
    const body = (await res.json()) as { status?: unknown };
    return (AGENT_STATUSES as readonly unknown[]).includes(body.status) ? (body.status as AgentStatus) : "overseer sent no status";
  } catch {
    return "overseer not reachable";
  }
}

/**
 * A person quarantines, terminates, releases (undo) or dismisses one or more chosen agents.
 * Live: audit row per agent, the overseer writes the flag the agent obeys, one Discord alert.
 * Demo playback: nothing leaves the browser's page state; the caller applies the change locally.
 */
export async function actOnAgents(input: { agents: unknown; action: unknown; source: "live" | "demo" }): Promise<AgentActionResult> {
  const agents = clean(input?.agents);
  const action = input?.action;
  if (agents.length === 0 || !(AGENT_ACTIONS as readonly unknown[]).includes(action)) {
    return { audited: 0, alerted: false, note: "Nothing to do.", statuses: {} };
  }
  const act = action as AgentAction;
  if (input.source !== "live") {
    return { audited: 0, alerted: false, note: `Recorded run: ${act} shown here only, not sent or logged.`, statuses: {} };
  }

  const user = hasSupabase ? await getUser() : null;
  const by = user?.id ?? "presenter";
  const outcomes = await Promise.all(agents.map((a) => tellOverseer(a.agent_id, act, user ? "operator" : "presenter")));
  const statuses: Record<string, AgentStatus> = {};
  const problems: string[] = [];
  agents.forEach((a, i) => {
    const o = outcomes[i];
    if ((AGENT_STATUSES as readonly string[]).includes(o)) statuses[a.agent_id] = o as AgentStatus;
    else problems.push(`${a.agent_id}: ${o}`);
  });

  const audit = await writeAudit(
    agents.map((a, i) => ({
      agent_id: a.agent_id,
      risk: a.risk,
      attack_type: a.attack_type,
      action: act,
      decided_by: by,
      detail: { recommended_action: a.recommended_action, reason: a.reason, overseer: outcomes[i] },
    })),
  );
  const alert = await sendAlert(
    `${user ? "A signed-in operator" : "The presenter"} ${PAST[act]} ${list(agents)}.` +
      (problems.length ? ` Not applied: ${problems.join("; ")}.` : ""),
  );
  revalidatePath("/sentinel");
  const done = Object.keys(statuses);
  const head = done.length ? `${PAST[act].toLowerCase().replace(" the alert for", "")} ${done.join(", ")}.` : "";
  return {
    audited: audit.written,
    alerted: alert.sent,
    note: [head && head[0].toUpperCase() + head.slice(1), problems.length ? `Not applied: ${problems.join("; ")}.` : "", note(audit, alert.sent)].filter(Boolean).join(" "),
    statuses,
  };
}
