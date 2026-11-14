import type { Metadata } from "next";
import { DemoBadge, Page, PageHeader } from "@/components/ui";
import timelineJson from "./_data/demo_timeline.json";
import type { DemoTimeline } from "./_lib/contract";
import { LiveFleet } from "./live-fleet";

// Sentinel (Cisco, Mission 3). The integrator (Alex's Claude) owns this file and wires in the
// parts. Demo mode plays _data/demo_timeline.json with no network and no keys; otherwise the
// page polls the overseer's GET /agents (NEXT_PUBLIC_SENTINEL_API_URL, default localhost:8000).
export const metadata: Metadata = { title: "Live fleet" };

// JSON imports widen literal unions to string, so cast. The file was checked against contract.py in PR #12.
const timeline = (timelineJson as unknown as DemoTimeline).ticks;
const apiUrl = process.env.NEXT_PUBLIC_SENTINEL_API_URL || "http://localhost:8000";
// Recorded playback only when asked for (NEXT_PUBLIC_DEMO_MODE=1). The shared demoMode also turns on
// when Supabase keys are missing, which must not stop a keyless laptop from showing the live swarm;
// audit writes still skip themselves without Supabase, and an unreachable overseer falls back to playback.
const playback = process.env.NEXT_PUBLIC_DEMO_MODE === "1";

export default function SentinelPage() {
  return (
    <Page>
      <PageHeader
        meta={<span className="flex items-center gap-2">Sentinel · Cisco track <DemoBadge on={playback} /></span>}
        title="One hijacked AI agent can infect its whole team. Sentinel finds it and asks a human what to do."
      />
      {/* validation stays null until _py/validate.py writes _data/validation.json (C12). */}
      <LiveFleet timeline={timeline} validation={null} demo={playback} apiUrl={apiUrl} />
    </Page>
  );
}
