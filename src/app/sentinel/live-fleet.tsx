"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { EventLog } from "./_components/event-log";
import { FleetHeadline } from "./_components/fleet-headline";
import { FleetScatter } from "./_components/fleet-scatter";
import { LimitsCard } from "./_components/limits-card";
import { PatientZero } from "./_components/patient-zero";
import { Recommendation } from "./_components/recommendation";
import { RelatedAgents } from "./_components/related-agents";
import { ResultsPanel } from "./_components/results-panel";
import { decide, recordRecommendation, type FlaggedAgent } from "./actions";
import type { Containment, Decision, FleetAgent, FleetSnapshot, Validation } from "./_lib/contract";
import { pendingRecommendations } from "./_lib/response";

// Integrator wiring for /sentinel: picks the data source and owns the human decisions.
// Live: polls GET {apiUrl}/agents every second. Demo (or the overseer never answered): plays
// _data/demo_timeline.json one tick per second, with no network. Rendering is Stephen's
// _components; this file only feeds them.

type Source = "live" | "demo";
const POLL_MS = 1000;

const toFlagged = (a: FleetAgent): FlaggedAgent => ({
  agent_id: a.agent_id,
  risk: a.risk,
  attack_type: a.attack_type,
  recommended_action: a.recommended_action,
  reason: a.reason,
});

/** Containment as the human left it: approved/dismissed once every current recommendation is decided. */
function containmentAfter(snapshot: FleetSnapshot, decisions: Record<string, Decision>): Containment {
  const recs = pendingRecommendations(snapshot);
  if (recs.length === 0 || recs.some((a) => !decisions[a.agent_id])) return snapshot.sentinel.containment;
  return recs.some((a) => decisions[a.agent_id] === "approved") ? "approved" : "dismissed";
}

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
  const [source, setSource] = useState<Source>(demo ? "demo" : "live");
  const [tick, setTick] = useState(0);
  const [live, setLive] = useState<FleetSnapshot | null>(null);
  const [offline, setOffline] = useState(false);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [note, setNote] = useState("");
  const recorded = useRef(new Set<string>());

  // Demo playback: advance one tick per second, hold on the last.
  useEffect(() => {
    if (source !== "demo") return;
    const id = setInterval(() => setTick((t) => Math.min(t + 1, timeline.length - 1)), POLL_MS);
    return () => clearInterval(id);
  }, [source, timeline.length]);

  // Live polling. Falls back to demo playback only if the overseer never answered.
  useEffect(() => {
    if (source !== "live") return;
    let stop = false;
    let gotOne = false;
    const poll = async () => {
      try {
        const res = await fetch(`${apiUrl}/agents`, { cache: "no-store", signal: AbortSignal.timeout(2000) });
        if (!res.ok) throw new Error(String(res.status));
        const snap = (await res.json()) as FleetSnapshot;
        if (stop) return;
        gotOne = true;
        setLive(snap);
        setOffline(false);
      } catch {
        if (stop) return;
        setOffline(true);
        if (!gotOne) {
          setSource("demo");
          setNote("The overseer isn't answering, so this is the recorded demo run.");
        }
      }
    };
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [source, apiUrl]);

  const snapshot: FleetSnapshot = source === "live" && live ? live : timeline[Math.min(tick, timeline.length - 1)];
  const recs = pendingRecommendations(snapshot);
  const undecided = recs.filter((a) => !decisions[a.agent_id]);

  // Record each new Sentinel recommendation once (audit row + Discord alert; live runs only).
  useEffect(() => {
    const fresh = pendingRecommendations(snapshot).filter((a) => !recorded.current.has(`${a.agent_id}:${a.recommended_action}`));
    if (fresh.length === 0) return;
    fresh.forEach((a) => recorded.current.add(`${a.agent_id}:${a.recommended_action}`));
    recordRecommendation({ agents: fresh.map(toFlagged), source }).catch(() => {});
  }, [snapshot, source]);

  // Recommendation's buttons call this; it throws on failure so the component shows its error.
  const onDecide = useCallback(
    async (decision: Decision) => {
      const target = undecided.length ? undecided : recs;
      if (target.length === 0) return;
      const res = await decide({ agents: target.map(toFlagged), decision, source });
      setDecisions((d) => ({ ...d, ...Object.fromEntries(target.map((a) => [a.agent_id, decision])) }));
      // Tell the overseer too, so GET /agents (and the TUI) show approved/dismissed, not "recommended".
      // It only records the click; enforcement stays with a person (docker/quarantine.sh).
      let overseerNote = "";
      if (source === "live") {
        try {
          const r = await fetch(`${apiUrl}/decision`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ action: decision === "approved" ? "approve" : "dismiss" }),
            signal: AbortSignal.timeout(2000),
          });
          // 409 = the overseer already has no open recommendation; nothing to sync.
          if (!r.ok && r.status !== 409) overseerNote = " The overseer didn't record it; it still shows the recommendation.";
        } catch {
          overseerNote = " The overseer didn't answer; it still shows the recommendation.";
        }
      }
      setNote(res.note + overseerNote);
    },
    [undecided, recs, source, apiUrl],
  );

  const replay = () => {
    setTick(0);
    setDecisions({});
    recorded.current.clear();
    setNote("");
  };

  const pzId = snapshot.sentinel.patient_zero;
  const pz = snapshot.agents.find((a) => a.agent_id === pzId) ?? null;
  const sentinel = { ...snapshot.sentinel, containment: containmentAfter(snapshot, decisions) };
  const step = Math.min(tick, timeline.length - 1) + 1;

  return (
    <div className="flex flex-col gap-6">
      <FleetHeadline agents={snapshot.agents} sentinel={sentinel} />

      <div className="flex flex-wrap items-center gap-3 text-sm text-ink-2" aria-live="polite">
        <span>
          {source === "live"
            ? offline
              ? "Overseer not answering; showing the last snapshot."
              : "Live from the overseer, updated every second."
            : `Recorded demo run, second ${step} of ${timeline.length}.`}
        </span>
        {source === "demo" && (
          <Button variant="secondary" onClick={replay}>Replay demo</Button>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <FleetScatter agents={snapshot.agents} patientZero={pzId} />
        <div className="flex flex-col gap-6">
          <PatientZero agent={pz} originTs={snapshot.sentinel.origin_ts} />
          <RelatedAgents sourceId={pzId} related={pz?.related_agents ?? []} agents={snapshot.agents} />
        </div>
      </div>

      <Recommendation agents={snapshot.agents} containment={sentinel.containment} onDecide={onDecide} />
      {note && <p role="status" className="text-sm text-ink-2">{note}</p>}

      <EventLog events={snapshot.events} />
      <ResultsPanel results={validation} />
      <LimitsCard />
    </div>
  );
}
