"use client";

// Per-agent human actions (#53): the buttons and status tag shared by the agent queue and the detail panel.
// Every button is a person's choice; Sentinel itself never calls these.
import { Button, Tag } from "@/components/ui";
import type { AgentAction, AgentStatus } from "../_lib/contract";

export type OnAct = (agentIds: string[], action: AgentAction) => void | Promise<void>;

export const STATUS_LABEL: Record<AgentStatus, string> = {
  active: "Running",
  quarantined: "Quarantined",
  terminated: "Terminated",
};

export function StatusTag({ status, dismissed }: { status: AgentStatus; dismissed?: boolean }) {
  if (status === "active") return dismissed ? <Tag severity="Info">Alert dismissed</Tag> : null;
  return <Tag severity={status === "terminated" ? "Critical" : "Warning"}>{STATUS_LABEL[status]} by you</Tag>;
}

/** Quarantine / Terminate / Dismiss for a running agent; Release (the undo) for a stopped one. */
export function AgentActionButtons({
  agentId,
  status,
  onAct,
  busy,
}: {
  agentId: string;
  status: AgentStatus;
  onAct: OnAct;
  busy: boolean;
}) {
  if (status !== "active") {
    return (
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={busy} onClick={() => onAct([agentId], "release")}>
          {status === "terminated" ? "Undo terminate" : "Release"}
          <span className="sr-only"> {agentId}</span>
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      <Button disabled={busy} onClick={() => onAct([agentId], "quarantine")}>
        Quarantine<span className="sr-only"> {agentId}</span>
      </Button>
      <Button disabled={busy} onClick={() => onAct([agentId], "terminate")}>
        Terminate<span className="sr-only"> {agentId}</span>
      </Button>
      <Button variant="secondary" disabled={busy} onClick={() => onAct([agentId], "dismiss")}>
        Dismiss<span className="sr-only"> alert for {agentId}</span>
      </Button>
    </div>
  );
}
