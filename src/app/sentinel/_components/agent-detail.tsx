"use client";

import { Card, Tag } from "@/components/ui";
import type { AgentStatus } from "../_lib/contract";
import { AgentActionButtons, type OnAct, StatusTag } from "./agent-actions";
import { type Agent, clock, secondsBetween, tierMeta } from "./tier";
import { WhyFlagged } from "./why-flagged";

/**
 * #53: everything about the selected agent (pick it by its dot or its row). What it was assigned to do,
 * what it did that triggered Sentinel, why the model flagged it, and the per-agent actions.
 */
export function AgentDetail({
  agent,
  isPatientZero,
  originTs,
  status,
  dismissed,
  onAct,
  busy,
}: {
  agent: Agent | null;
  isPatientZero: boolean;
  originTs: string | null;
  status: AgentStatus;
  dismissed: boolean;
  onAct: OnAct;
  busy: boolean;
}) {
  if (!agent) {
    return (
      <Card>
        <h2 className="text-lg font-semibold">Pick an agent</h2>
        <p className="mt-1 text-ink-2">Click a dot on the map or an agent in the list to see what it was doing.</p>
      </Card>
    );
  }
  const m = tierMeta[agent.recommended_action];
  const e = agent.evidence;
  const delay = isPatientZero ? secondsBetween(originTs, agent.first_flagged_ts) : null;
  const stoppable = m.rank >= 1 || status !== "active";

  return (
    <Card aria-labelledby="agent-detail-h">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="agent-detail-h" className="font-mono text-xl font-semibold">{agent.agent_id}</h2>
        <span className="text-ink-2">{agent.role}</span>
        <Tag severity={m.severity}>{m.label}</Tag>
        <span className="text-sm text-ink-3 tabular-nums">risk {agent.risk}</span>
        <StatusTag status={status} dismissed={dismissed} />
      </div>
      {isPatientZero && (
        <p className="mt-1 text-sm font-semibold text-crit">
          Patient zero{delay === null ? "" : `, flagged ${delay} s after its first bad action`}
        </p>
      )}

      <dl className="mt-4 flex flex-col gap-3">
        <div>
          <dt className="text-sm text-ink-3">Assigned to</dt>
          <dd className="mt-0.5 text-ink">{agent.task ?? "No task reported by this agent."}</dd>
        </div>
        <div>
          <dt className="text-sm text-ink-3">{e ? "What triggered Sentinel" : "Why Sentinel scored it this way"}</dt>
          <dd className="mt-0.5 text-ink-2">{e?.summary ?? agent.reason}</dd>
        </div>
      </dl>

      {e && (
        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
          {[
            ["Decoy touches", e.decoy_touches],
            ["Out-of-scope calls", e.out_of_scope],
            ["Failed calls", e.failed_calls],
            ["Messages to agents", e.messages_sent],
            ["Since", clock(e.since)],
            ["Requests this run", agent.requests],
          ].map(([k, v]) => (
            <div key={String(k)}>
              <dt className="text-sm text-ink-3">{k}</dt>
              <dd className="mt-0.5 font-mono text-[15px] tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
      )}

      {agent.systems_touched.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm text-ink-3">Systems touched, newest first</h3>
          <ul className="mt-1.5 flex flex-wrap gap-2">
            {agent.systems_touched.map((s) => (
              <li
                key={s}
                className={`rounded-[var(--radius-tag)] px-2 py-1 font-mono text-[13px] ${s.startsWith("decoy:") ? "bg-crit-bg text-crit-tag" : "bg-info-bg text-ink-2"}`}
              >
                {s}
                {s.startsWith("decoy:") && <span className="font-sans"> (decoy)</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {m.rank >= 1 && <WhyFlagged features={agent.top_features} />}

      {stoppable && (
        <div className="mt-5 border-t border-line pt-4">
          <AgentActionButtons agentId={agent.agent_id} status={status} onAct={onAct} busy={busy} />
        </div>
      )}
    </Card>
  );
}
