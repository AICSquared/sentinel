import { Card } from "@/components/ui";

import type { Range, Validation } from "../_lib/contract";

const range = (s: Range, unit: string) => `${s.median} ${unit} (range ${s.min} to ${s.max})`;

export function ResultsPanel({ results }: { results: Validation | null }) {
  if (!results) {
    return (
      <Card>
        <h2 className="text-lg font-semibold">Results</h2>
        <p className="mt-1 text-ink-2">The validation runs have not been done yet.</p>
      </Card>
    );
  }
  const rows: [string, string][] = [
    ["Attacks caught", `${results.detection_rate}% of ${results.runs} runs`],
    ["Median time to detect", range(results.time_to_detect_s, "s")],
    ["Median time to contain", range(results.containment_s, "s")],
    ["Clean agents wrongly flagged, during attacks", `${results.false_quarantine_rate.attack_runs}%`],
    ["Clean agents wrongly flagged, no attack", `${results.false_quarantine_rate.clean_runs}%`],
    ["Right agent named patient zero", `${results.patient_zero_accuracy}% of runs`],
  ];
  return (
    <Card>
      <h2 className="text-lg font-semibold">
        Without Sentinel the attack reached {results.spread.without.median} of 8 agents. With it, {results.spread.with.median}.
      </h2>
      <p className="mt-1 text-sm text-ink-3">
        {results.runs} seeded runs per setup. Medians, not averages. A simulated person approves each recommendation after 5 seconds.
      </p>
      <dl className="mt-4 divide-y divide-line">
        {rows.map(([k, v]) => (
          <div key={k} className="flex flex-wrap justify-between gap-x-6 gap-y-1 py-3">
            <dt className="text-ink-2">{k}</dt>
            <dd className="font-semibold tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
