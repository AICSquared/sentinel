import { Card } from "@/components/ui";

const LIMITS = [
  "The anomaly model needs a clean baseline. If the swarm is already compromised when it learns, it treats the attack as normal.",
  "The classifier only knows the attacks it was trained on. A second model flags anything unusual, and calls it unknown.",
  "Tracing finds which agent and which system, not which person.",
  "Quarantine is a recommendation. Real enforcement needs access an overseer should not take on its own, so a human decides.",
  "The training data is synthetic.",
];

export function LimitsCard() {
  return (
    <Card>
      <h2 className="text-lg font-semibold">What Sentinel cannot do</h2>
      <ul className="mt-3 flex list-disc flex-col gap-2 pl-5 text-ink-2">
        {LIMITS.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
    </Card>
  );
}
