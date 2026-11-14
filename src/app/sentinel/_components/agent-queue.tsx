"use client";

import { useState } from "react";
import { Button, Card, Tag } from "@/components/ui";
import type { AgentStatus } from "../_lib/contract";
import { AgentActionButtons, type OnAct, StatusTag } from "./agent-actions";
import { type Agent, isFlagged, tierMeta } from "./tier";

/**
 * #53: what Sentinel recommends, one row per agent. Pick any agent (its id selects it), act on it alone,
 * or tick several and act on just those. Agents a person already stopped stay listed with Release.
 */
export function AgentQueue({
  agents,
  statusOf,
  dismissed,
  selectedId,
  onSelect,
  onAct,
  busy,
}: {
  agents: Agent[];
  statusOf: (id: string) => AgentStatus;
  dismissed: Set<string>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onAct: OnAct;
  busy: boolean;
}) {
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const rows = agents
    .filter((a) => isFlagged(a) || statusOf(a.agent_id) !== "active")
    .sort((a, b) => Number(dismissed.has(a.agent_id)) - Number(dismissed.has(b.agent_id)) || b.risk - a.risk);
  const slow = agents.filter((a) => a.recommended_action === "throttle" && statusOf(a.agent_id) === "active");

  if (rows.length === 0) {
    return (
      <Card>
        <h2 className="text-lg font-semibold">Nothing to decide</h2>
        <p className="mt-1 text-ink-2">
          {slow.length === 0
            ? "No agent is above the quarantine line (risk 75)."
            : `${slow.map((a) => a.agent_id).join(", ")} ${slow.length === 1 ? "is" : "are"} acting unusually. Watch closely.`}
        </p>
      </Card>
    );
  }

  const open = rows.filter((a) => statusOf(a.agent_id) === "active" && !dismissed.has(a.agent_id));
  const picked = rows.filter((a) => checked.has(a.agent_id)).map((a) => a.agent_id);
  const pickedActive = picked.filter((id) => statusOf(id) === "active");
  const pickedStopped = picked.filter((id) => statusOf(id) !== "active");
  const toggle = (id: string) =>
    setChecked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const bulk = async (ids: string[], action: Parameters<OnAct>[1]) => {
    await onAct(ids, action);
    setChecked(new Set());
  };

  return (
    <Card aria-labelledby="queue-h">
      <h2 id="queue-h" className="text-xl font-semibold">
        {open.length
          ? `Sentinel recommends: ${open.map((a) => `${tierMeta[a.recommended_action].rank >= 3 ? "terminate" : "quarantine"} ${a.agent_id}`).join(", ")}`
          : "Every recommendation has a decision"}
      </h2>
      <p className="mt-1 text-sm text-ink-3">
        Choose per agent. Nothing happens until you click; every click is logged and can be undone with Release.
      </p>

      <ul className="mt-4 divide-y divide-line">
        {rows.map((a) => {
          const status = statusOf(a.agent_id);
          const m = tierMeta[a.recommended_action];
          const selected = a.agent_id === selectedId;
          return (
            <li key={a.agent_id} className={`flex flex-col gap-2 py-3 ${selected ? "-mx-3 rounded-[var(--radius-control)] bg-ground px-3" : ""}`}>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <label className="flex min-h-11 min-w-11 cursor-pointer items-center justify-center">
                  <input
                    type="checkbox"
                    className="size-5 accent-[var(--color-accent)]"
                    checked={checked.has(a.agent_id)}
                    onChange={() => toggle(a.agent_id)}
                    aria-label={`Select ${a.agent_id}`}
                  />
                </label>
                <button
                  type="button"
                  onClick={() => onSelect(a.agent_id)}
                  aria-pressed={selected}
                  className="min-h-11 rounded-[var(--radius-control)] px-1 font-mono text-[15px] font-semibold text-ink underline-offset-4 hover:underline"
                >
                  {a.agent_id}
                </button>
                <Tag severity={m.severity}>{m.label}</Tag>
                <span className="text-sm text-ink-3 tabular-nums">risk {a.risk}</span>
                <StatusTag status={status} dismissed={dismissed.has(a.agent_id)} />
              </div>
              <p className="pl-14 text-ink-2">{a.reason}</p>
              <div className="pl-14">
                <AgentActionButtons agentId={a.agent_id} status={status} onAct={onAct} busy={busy} />
              </div>
            </li>
          );
        })}
      </ul>

      {picked.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-4" aria-live="polite">
          <span className="mr-1 text-sm text-ink-2">
            {picked.length} selected: {picked.join(", ")}
          </span>
          {pickedActive.length > 0 && (
            <>
              <Button disabled={busy} onClick={() => bulk(pickedActive, "quarantine")}>Quarantine selected</Button>
              <Button disabled={busy} onClick={() => bulk(pickedActive, "terminate")}>Terminate selected</Button>
              <Button variant="secondary" disabled={busy} onClick={() => bulk(pickedActive, "dismiss")}>Dismiss selected</Button>
            </>
          )}
          {pickedStopped.length > 0 && (
            <Button variant="secondary" disabled={busy} onClick={() => bulk(pickedStopped, "release")}>Release selected</Button>
          )}
        </div>
      )}
    </Card>
  );
}
