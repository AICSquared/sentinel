"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { AgentDetail } from "./_components/agent-detail";
import { AgentQueue } from "./_components/agent-queue";
import { EventLog } from "./_components/event-log";
import { FleetHeadline } from "./_components/fleet-headline";
import { FleetScatter } from "./_components/fleet-scatter";
import { LimitsCard } from "./_components/limits-card";
import { RelatedAgents } from "./_components/related-agents";
import { ResultsPanel } from "./_components/results-panel";
import { actOnAgents, recordRecommendation, type FlaggedAgent } from "./actions";
import type { AgentAction, AgentStatus, Containment, FleetAgent, FleetSnapshot, Validation } from "./_lib/contract";
import { pendingRecommendations } from "./_lib/response";

// Integrator wiring for /sentinel: picks the data source and owns the human decisions.
// Live: polls GET {apiUrl}/agents every second. Demo (or the overseer never answered): plays
// _data/demo_timeline.json one tick per second, with no network.
// #53: a person picks an agent (its dot or its row) and quarantines, terminates, releases or dismisses
// it, alone or as a chosen group. Live, that goes through the `actOnAgents` server action (audit row,
// overseer flag the agent obeys, Discord). On the recording it is shown on this page only.

type Source = "live" | "demo";
const POLL_MS = 1000;

const toFlagged = (a: FleetAgent): FlaggedAgent => ({
  agent_id: a.agent_id,
  risk: a.risk,
  attack_type: a.attack_type,
  recommended_action: a.recommended_action,
  reason: a.reason,
});

const AFTER: Partial<Record<AgentAction, AgentStatus>> = { quarantine: "quarantined", terminate: "terminated", release: "active" };

export function LiveFleet({
  timeline,
  validation,
  demo,
  apiUrl,
}: {
  timeline: FleetSnapshot[];
  validation: Validation | null;
  demo: boolean;
  apiUrl: string;
}) {
  // Starts on the recording; switches to "live" when the overseer first answers (never in demo mode).
  const [source, setSource] = useState<Source>("demo");
  const [tick, setTick] = useState(0);
  const [live, setLive] = useState<FleetSnapshot | null>(null);
  const [offline, setOffline] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, AgentStatus>>({}); // the recording, or until the next live poll
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const recorded = useRef(new Set<string>());

  const resetDecisions = () => {
    setOverrides({});
    setDismissed(new Set());
    setSelectedId(null);
    recorded.current.clear();
    setNote("");
  };

  // Demo playback: advance one tick per second, hold on the last.
  useEffect(() => {
    if (source !== "demo") return;
    const id = setInterval(() => setTick((t) => Math.min(t + 1, timeline.length - 1)), POLL_MS);
    return () => clearInterval(id);
  }, [source, timeline.length]);

  // Live polling never gives up. Until the overseer first answers, the recorded run plays as a
  // placeholder (clearly labelled); the moment it answers, the page switches to live data. This
  // matters on stage: `docker compose up --build` restarts the overseer for ~20 s.
  useEffect(() => {
    if (demo) return;
    let stop = false;
    let gotOne = false;
    const poll = async () => {
      try {
        const res = await fetch(`${apiUrl}/agents`, { cache: "no-store", signal: AbortSignal.timeout(2000) });
        if (!res.ok) throw new Error(String(res.status));
        const snap = (await res.json()) as FleetSnapshot;
        if (stop) return;
        if (!gotOne) {
          // First live answer: drop anything clicked during the placeholder playback.
          gotOne = true;
          setOverrides({});
          setDismissed(new Set());
          setSelectedId(null);
          recorded.current.clear();
          setNote("");
          setSource("live");
        }
        setLive(snap);
        setOverrides({}); // live statuses come from the overseer from here on
        setOffline(false);
      } catch {
        if (stop) return;
        setOffline(true);
      }
    };
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [demo, apiUrl]);

  const snapshot: FleetSnapshot = source === "live" && live ? live : timeline[Math.min(tick, timeline.length - 1)];
  const byId = new Map(snapshot.agents.map((a) => [a.agent_id, a]));
  const statusOf = (id: string): AgentStatus => overrides[id] ?? byId.get(id)?.status ?? "active";

  // Record each new Sentinel recommendation once (audit row + Discord alert; live runs only).
  useEffect(() => {
    const fresh = pendingRecommendations(snapshot).filter((a) => !recorded.current.has(`${a.agent_id}:${a.recommended_action}`));
    if (fresh.length === 0) return;
    fresh.forEach((a) => recorded.current.add(`${a.agent_id}:${a.recommended_action}`));
    recordRecommendation({ agents: fresh.map(toFlagged), source }).catch(() => {});
  }, [snapshot, source]);

  // A person's per-agent action (#53). Throws nothing: problems are shown in the status line.
  const onAct = useCallback(
    async (ids: string[], action: AgentAction) => {
      const agents = ids.map((id) => byId.get(id)).filter((a): a is FleetAgent => Boolean(a));
      if (agents.length === 0) return;
      setBusy(true);
      try {
        const res = await actOnAgents({ agents: agents.map(toFlagged), action, source });
        const next = AFTER[action];
        if (source === "demo" && next) setOverrides((o) => ({ ...o, ...Object.fromEntries(ids.map((id) => [id, next])) }));
        if (source === "live") setOverrides((o) => ({ ...o, ...res.statuses }));
        setDismissed((d) => {
          const n = new Set(d);
          ids.forEach((id) => (action === "dismiss" ? n.add(id) : n.delete(id)));
          return n;
        });
        setNote(res.note);
      } catch {
        setNote("That action didn't go through. Try again.");
      } finally {
        setBusy(false);
      }
    },
    // byId is rebuilt every render from the snapshot; the snapshot is the real dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [snapshot, source],
  );

  const replay = () => {
    setTick(0);
    resetDecisions();
  };

  const pzId = snapshot.sentinel.patient_zero;
  const shownId = selectedId ?? pzId;
  const shown = shownId ? byId.get(shownId) ?? null : null;
  const recs = pendingRecommendations(snapshot);
  const undecided = recs.filter((a) => statusOf(a.agent_id) === "active" && !dismissed.has(a.agent_id));
  const containment: Containment =
    recs.length === 0 || undecided.length > 0
      ? snapshot.sentinel.containment
      : recs.some((a) => statusOf(a.agent_id) !== "active")
        ? "approved"
        : "dismissed";
  const step = Math.min(tick, timeline.length - 1) + 1;

  return (
    <div className="flex flex-col gap-6">
      <FleetHeadline agents={snapshot.agents} sentinel={{ ...snapshot.sentinel, containment }} />

      <div className="flex flex-wrap items-center gap-3 text-sm text-ink-2" aria-live="polite">
        <span>
          {source === "live"
            ? offline
              ? "Overseer not answering; showing the last snapshot."
              : "Live from the overseer, updated every second."
            : demo
              ? `Recorded demo run, second ${step} of ${timeline.length}.`
              : `Waiting for the overseer at ${apiUrl}: showing the recorded run (second ${step} of ${timeline.length}) until it answers.`}
        </span>
        {source === "demo" && (
          <Button variant="secondary" onClick={replay}>Replay demo</Button>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <FleetScatter agents={snapshot.agents} patientZero={pzId} selectedId={shownId} onSelect={setSelectedId} statusOf={statusOf} />
        <div className="flex flex-col gap-6">
          <AgentDetail
            agent={shown}
            isPatientZero={shownId !== null && shownId === pzId}
            originTs={snapshot.sentinel.origin_ts}
            status={shownId ? statusOf(shownId) : "active"}
            dismissed={shownId ? dismissed.has(shownId) : false}
            onAct={onAct}
            busy={busy}
          />
          <RelatedAgents sourceId={shownId} related={shown?.related_agents ?? []} agents={snapshot.agents} />
        </div>
      </div>

      <AgentQueue
        agents={snapshot.agents}
        statusOf={statusOf}
        dismissed={dismissed}
        selectedId={shownId}
        onSelect={setSelectedId}
        onAct={onAct}
        busy={busy}
      />
      {note && <p role="status" className="text-sm text-ink-2">{note}</p>}

      <EventLog events={snapshot.events} />
      <ResultsPanel results={validation} />
      <LimitsCard />
    </div>
  );
}
