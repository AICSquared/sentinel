import type { Metadata } from "next";
import Link from "next/link";
import { TIERS } from "@/app/sentinel/_lib/contract";
import { plainFeature } from "@/app/sentinel/_components/why-flagged";
import { LIMITS, Panel, primaryLink, textLink } from "../_site/home-sections";
import { buildStory } from "../_site/story";

export const metadata: Metadata = { title: "How it works" };

// The ten numbers the models read for each agent (contract A, columns 4-13), in plain words.
const FEATURES = [
  "actions_per_min",
  "distinct_tools_used",
  "distinct_tools_baseline",
  "failed_calls_per_min",
  "touched_decoy",
  "out_of_scope_resource",
  "msgs_to_agents_per_min",
  "distinct_peers",
  "bytes_out_per_min",
  "sec_since_normal",
];

const TIER_TEXT: Record<string, string> = {
  monitor: "Keep watching. Nothing is shown.",
  throttle: "Slow it down? The agent is flagged amber.",
  recommend_quarantine: "Recommend quarantine. A person decides.",
  recommend_terminate: "Recommend terminate. A person decides.",
};

const display = "font-light tracking-[-0.03em] text-ink";
const h2 = `${display} text-[clamp(1.75rem,3.2vw,2.5rem)] leading-[1.08]`;

export default function HowItWorks() {
  const story = buildStory();
  const steps = [
    {
      title: `${story.agentCount} agents`,
      body: `${story.roles.map((r) => `${r[0].toUpperCase()}${r.slice(1)}s`).join(", ")}. Every action is reported: each tool call, message to another agent and system touched.`,
    },
    { title: "The overseer", body: "Turns each agent's last 60 seconds into ten numbers, every 2 seconds." },
    { title: "Two models", body: "One knows the attacks it was trained on. The other notices anything unusual." },
    { title: "Risk 0 to 100", body: "One score and one plain sentence saying why. Then a person decides.", strong: true },
  ];
  return (
    <main className="px-4 pt-10 pb-20 sm:px-8 lg:px-16">
      <h1 className={`${display} max-w-4xl text-[clamp(2.5rem,5.6vw,4.5rem)] leading-[1]`}>From {story.agentCount === 8 ? "eight" : story.agentCount} agents to one decision.</h1>

      <ol className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label="How a decision is made">
        {steps.map((s, i) => (
          <li
            key={s.title}
            className={`relative rounded-[22px] border px-6 py-6 ${s.strong ? "border-crit bg-crit text-ground" : "border-ink-3/60 text-ink"}`}
          >
            <h2 className="text-[20px] font-normal">{s.title}</h2>
            <p className={`mt-2 text-[15px] leading-relaxed ${s.strong ? "text-ground" : "text-ink-2"}`}>{s.body}</p>
            {i < steps.length - 1 && (
              <span aria-hidden className="absolute top-1/2 -right-4 hidden w-4 border-t border-dotted border-ink-3 xl:block" />
            )}
          </li>
        ))}
      </ol>
      <p className="mt-4 text-sm text-ink-3">A simple frequency-count rule takes over if the models are missing or fail.</p>

      <div className="mt-20 grid gap-16 lg:grid-cols-2">
        <section aria-labelledby="swarm-h">
          <h2 id="swarm-h" className={h2}>The team being watched</h2>
          <p className="mt-4 max-w-[34em] text-[16px] leading-relaxed text-ink-2">
            The demo runs {story.agentCount} scripted agents in Docker, each with a job, such as reviewing pull requests or building the weekly sales report. One shared image, no AI model per agent. One of them is hijacked on cue: it touches a planted credential, reaches outside its role, and floods another agent with injected messages. An agent that receives enough of them turns too.
          </p>
        </section>

        <section aria-labelledby="numbers-h">
          <h2 id="numbers-h" className={h2}>The ten numbers</h2>
          <ul className="mt-4 grid gap-x-8 gap-y-1.5 text-[15px] text-ink-2 sm:grid-cols-2">
            {FEATURES.map((f) => (
              <li key={f} className="border-b border-dotted border-ink-3/40 py-1.5">{plainFeature(f)}</li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="models-h">
          <h2 id="models-h" className={h2}>The two models</h2>
          <dl className="mt-4 flex flex-col gap-5 text-[16px] leading-relaxed">
            <div>
              <dt className="text-ink">Known attacks: a gradient-boosted classifier (XGBoost)</dt>
              <dd className="mt-1 text-ink-2">
                Trained on labelled examples of each attack type. For every agent it reports which numbers pushed the score up, which become the plain-language reason and the &ldquo;why flagged&rdquo; bars.
              </dd>
            </div>
            <div>
              <dt className="text-ink">Anything unusual: an Isolation Forest, used twice</dt>
              <dd className="mt-1 text-ink-2">
                Before training, one removes junk rows from the training data only. While running, a second one learns what normal looks like and flags anything far from it, even an attack nobody trained for. It also places each agent on the behaviour map.
              </dd>
            </div>
          </dl>
          <p className="mt-4 text-sm text-ink-3">
            A third detector for message text, trained and tested on public prompt-injection data, exists but is not part of the live overseer yet.
          </p>
        </section>

        <section aria-labelledby="spread-h">
          <h2 id="spread-h" className={h2}>Tracing the spread</h2>
          <p className="mt-4 max-w-[34em] text-[16px] leading-relaxed text-ink-2">
            Sentinel counts who messaged whom over the last 5 minutes. When an agent is flagged, every agent it messaged is listed. A partner counts as likely infected when it received 10 or more messages and its own risk is 40 or more; otherwise it is likely clean and left alone. The first agent to reach risk 75 is named patient zero.
          </p>
        </section>
      </div>

      <div className="mt-20 grid gap-12 lg:grid-cols-2">
        <section aria-labelledby="tiers-h">
          <h2 id="tiers-h" className={h2}>What the score suggests</h2>
          <ul className="mt-6">
            {TIERS.map((t) => (
              <li key={t.action} className="grid grid-cols-[5.5rem_1fr] items-center gap-4 border-t border-dotted border-ink-3/50 py-3 last:border-b">
                <span className="font-mono text-[14px] text-ink-2 tabular-nums">
                  {t.min}–{t.max}
                </span>
                <span className="text-[16px] text-ink">{TIER_TEXT[t.action]}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-ink-3">Every tier is a recommendation. Nothing happens without a click.</p>
        </section>

        <section aria-labelledby="person-h" className="flex flex-col gap-3">
          <h2 id="person-h" className={h2}>What a person can do</h2>
          <p className="mt-1 mb-3 max-w-[34em] text-[16px] leading-relaxed text-ink-2">
            In the explorer, pick any agent by its dot or its row. Quarantine cuts it off from the others; terminate stops it; release undoes either; dismiss records that you looked and chose to leave it. Every click goes to an insert-only audit log.
          </p>
          <Panel title="If the models are unavailable">
            If a model file is missing or a model fails, Sentinel scores with a frequency-count rule (decoy touched, out-of-scope calls, message bursts) and says so on screen. Scoring never stops.
          </Panel>
          <Panel title="What Sentinel cannot do">
            <ul className="list-disc pl-5 marker:text-ink-3">
              {LIMITS.map((l) => (
                <li key={l} className="mt-1.5">{l}</li>
              ))}
            </ul>
          </Panel>
        </section>
      </div>

      <div className="mt-16 flex flex-wrap items-center gap-x-7 gap-y-3">
        <Link href="/sentinel" className={primaryLink}>Open the explorer</Link>
        <Link href="/" className={textLink}>Back to the overview</Link>
      </div>
    </main>
  );
}
