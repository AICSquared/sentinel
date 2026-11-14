import type { Metadata } from "next";
import { Card, DemoBadge, Page, PageHeader } from "@/components/ui";
import { demoMode } from "@/lib/demo";
import { sample } from "./_data/sample";

// Medtronic track. The integrator (Alex's Claude) owns this file and wires in the parts from
// _components/. It renders from _data/ in demo mode, so the route always works on stage.
export const metadata: Metadata = { title: "Medtronic" };

export default function MedtronicPage() {
  return (
    <Page>
      <PageHeader meta={<span className="flex items-center gap-2">Medtronic track <DemoBadge on={demoMode} /></span>} title={sample.headline} />
      {sample.rows.length === 0 ? (
        <Card>
          <p className="text-ink-2">
            The plan lives in <code className="font-mono text-sm">docs/plans/medtronic.md</code> and progress in{" "}
            <code className="font-mono text-sm">src/app/medtronic/CHECKLIST.md</code>.
          </p>
        </Card>
      ) : (
        <Card>
          <ul className="flex flex-col divide-y divide-line">
            {sample.rows.map((r) => (
              <li key={r.label} className="flex items-baseline justify-between gap-4 py-3">
                <span>{r.label}</span>
                <span className="font-mono">{r.value}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </Page>
  );
}
