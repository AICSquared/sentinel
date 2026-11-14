import type { FeatureContribution } from "../_lib/contract";

// Plain names for the model's inputs (contract A columns 4-13, plus prompt_risk). Unknown names fall back to
// the raw column name so a future feature still shows up.
const PLAIN: Record<string, string> = {
  actions_per_min: "Actions per minute",
  distinct_tools_used: "Different tools used",
  distinct_tools_baseline: "Typical tool count for its role",
  failed_calls_per_min: "Failed calls per minute",
  touched_decoy: "Touched a decoy credential",
  out_of_scope_resource: "Used a system outside its role",
  msgs_to_agents_per_min: "Messages to other agents per minute",
  distinct_peers: "Different agents messaged",
  bytes_out_per_min: "Data sent outward per minute",
  sec_since_normal: "Seconds since it last looked normal",
  prompt_risk: "Suspicious prompt text",
};

export const plainFeature = (name: string) => PLAIN[name] ?? name.replaceAll("_", " ");

/**
 * "Why flagged": the classifier's biggest pushes for one agent (agents[].top_features, XGBoost per-row
 * contributions, largest first). Red bars push toward "attack", grey bars toward "normal". Bar length is
 * relative to the largest push shown, so it compares features for this agent only.
 * Renders a short note instead of bars when the snapshot has none (recorded demo run, models not loaded).
 */
export function WhyFlagged({ features }: { features: FeatureContribution[] | undefined }) {
  if (!features || features.length === 0) {
    return (
      <section aria-labelledby="why-flagged-h" className="mt-5">
        <h3 id="why-flagged-h" className="text-sm font-semibold">Why it was flagged</h3>
        <p className="mt-1 text-sm text-ink-3">
          No explanation for this run: the recorded demo has none, or the model isn&apos;t loaded.
        </p>
      </section>
    );
  }
  const max = Math.max(...features.map((f) => Math.abs(f.contribution)), Number.EPSILON);
  return (
    <section aria-labelledby="why-flagged-h" className="mt-5">
      <h3 id="why-flagged-h" className="text-sm font-semibold">Why it was flagged</h3>
      <p className="mt-0.5 text-sm text-ink-3">
        Longer bar = bigger push. Red pushes toward attack, grey toward normal.
      </p>
      <ul className="mt-2 flex flex-col gap-2">
        {features.map((f) => {
          const toward = f.contribution >= 0 ? "toward attack" : "toward normal";
          const pct = Math.max(4, Math.round((Math.abs(f.contribution) / max) * 100));
          return (
            <li key={f.feature} className="grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)_3.5rem] items-center gap-3 text-sm">
              <span className="text-ink-2">{plainFeature(f.feature)}</span>
              <span aria-hidden className="h-2.5 rounded-sm bg-info-bg">
                <span
                  className={`block h-full rounded-sm ${f.contribution >= 0 ? "bg-crit" : "bg-ink-3"}`}
                  style={{ width: `${pct}%` }}
                />
              </span>
              <span className="text-right font-mono tabular-nums text-ink-2">
                {f.contribution >= 0 ? "+" : "−"}
                {Math.abs(f.contribution).toFixed(1)}
                <span className="sr-only"> {toward}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
