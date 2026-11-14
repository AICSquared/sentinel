"use client";

import { useState, useTransition } from "react";
import { Button, Card, Tag } from "@/components/ui";
import type { Containment, Decision } from "../_lib/contract";
import { type Agent, isFlagged, tierMeta } from "./tier";

/** What Sentinel recommends and the human's two buttons. Sentinel never acts on its own. */
export function Recommendation({
  agents,
  containment,
  onDecide,
}: {
  agents: Agent[];
  containment: Containment;
  onDecide: (decision: Decision) => void | Promise<void>;
}) {
  const [pending, startTransition] = useTransition();
  const [failed, setFailed] = useState(false);
  const flagged = agents.filter(isFlagged);
  const slow = agents.filter((a) => a.recommended_action === "throttle");

  const decide = (d: Decision) => {
    setFailed(false);
    startTransition(async () => {
      try {
        await onDecide(d);
      } catch {
        setFailed(true);
      }
    });
  };

  if (flagged.length === 0) {
    return (
      <Card>
        <h2 className="text-lg font-semibold">Nothing to approve</h2>
        <p className="mt-1 text-ink-2">
          {slow.length === 0
            ? "No agent is above the quarantine line (risk 75)."
            : `${slow.map((a) => a.agent_id).join(", ")} ${slow.length === 1 ? "is" : "are"} acting unusually. Consider slowing ${slow.length === 1 ? "it" : "them"} down.`}
        </p>
      </Card>
    );
  }

  const ids = flagged.map((a) => a.agent_id).join(", ");
  const worst = Math.max(...flagged.map((a) => tierMeta[a.recommended_action].rank));
  const verb = worst >= 3 ? "terminate" : "quarantine";

  return (
    <Card>
      <h2 className="text-xl font-semibold">
        {containment === "approved" && `Approved: ${verb} ${ids}`}
        {containment === "dismissed" && `Dismissed: no action on ${ids}`}
        {(containment === "recommended" || containment === "none") && `Recommend ${verb}: ${ids}`}
      </h2>
      <ul className="mt-4 flex flex-col gap-3">
        {flagged.map((a) => (
          <li key={a.agent_id} className="flex flex-col gap-1">
            <span className="flex items-center gap-2.5">
              <span className="font-mono text-[15px] font-semibold">{a.agent_id}</span>
              <Tag severity={tierMeta[a.recommended_action].severity}>{tierMeta[a.recommended_action].label}</Tag>
              <span className="text-sm text-ink-3 tabular-nums">risk {a.risk}</span>
            </span>
            <span className="text-ink-2">{a.reason}</span>
          </li>
        ))}
      </ul>

      {containment === "recommended" || containment === "none" ? (
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button onClick={() => decide("approved")} disabled={pending}>
            Approve {verb}
          </Button>
          <Button variant="secondary" onClick={() => decide("dismissed")} disabled={pending}>
            Dismiss
          </Button>
          <p className="text-sm text-ink-3">Nothing happens until you click. Your choice is recorded.</p>
        </div>
      ) : (
        <p className="mt-5 text-ink-2">Decision recorded. Sentinel keeps watching the other agents.</p>
      )}
      <p role="status" className="mt-2 text-sm text-crit-tag">
        {failed ? "The decision was not saved. Try again." : ""}
      </p>
    </Card>
  );
}
