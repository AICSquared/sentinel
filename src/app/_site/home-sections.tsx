// The static moments of the home page: the opening (team at rest), "Sentinel recommends. A person
// decides." and the close. Server components; facts come from story.ts, tiers from the frozen contract.
import Link from "next/link";
import type { ReactNode } from "react";
import { TIERS } from "@/app/sentinel/_lib/contract";
import { AgentNode, Callout, DecoyKey, FrameTicks, Overseer } from "./drawing";
import { spoken, type Story } from "./story";

const pill = "inline-flex min-h-11 items-center rounded-full px-6 text-[15px] font-medium";
export const primaryLink = `${pill} bg-accent text-white hover:bg-accent-strong`;
export const textLink = "inline-flex min-h-11 items-center text-[16px] text-ink underline decoration-1 underline-offset-[6px] hover:text-ink-2";
const display = "font-light tracking-[-0.045em] text-ink";

export function Hero({ story }: { story: Story }) {
  const t0 = story.ticks[0];
  const W = 540;
  const H = 600;
  // Zoomed to the normal cluster: at rest, all agents sit close together.
  const map = (x: number, y: number): [number, number] => [40 + ((x - 0.25) / 0.25) * 400, 500 - ((y - 0.29) / 0.15) * 270];
  const pts = t0.agents.map((a) => ({ ...a, p: map(a.x, a.y) }));
  const ov: [number, number] = [245, 96];
  const key: [number, number] = [372, 236];
  const far = [...pts].sort((a, b) => b.p[1] - a.p[1])[0];
  return (
    <section aria-labelledby="hero-h" className="grid min-h-[calc(100svh-5rem)] items-center gap-10 px-4 pt-6 pb-16 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:px-16">
      <div className="max-w-[40rem]">
        <h1 id="hero-h" className={`${display} text-[clamp(2.75rem,6.6vw,5.25rem)] leading-[0.98]`}>
          One hijacked AI agent can infect its whole team.
        </h1>
        <p className="mt-8 max-w-[30em] text-[19px] leading-relaxed text-ink-2">
          Sentinel watches a team of AI agents, finds the first one that turned, traces who it messaged, and asks a person what to do.
        </p>
        <div className="mt-10 flex flex-wrap items-center gap-x-7 gap-y-3">
          <Link href="/sentinel" className={primaryLink}>Open the explorer</Link>
          <Link href="/how-it-works" className={textLink}>How it works</Link>
        </div>
        <p className="mt-16 hidden text-sm text-ink-3 lg:block">Scroll to watch one agent turn.</p>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mx-auto h-auto w-full max-w-[540px] overflow-visible" role="img"
        aria-label={`${story.agentCount} agents at rest in one group, watched by the overseer above them, with a planted credential nearby.`}>
        <FrameTicks w={520} h={H} />
        <ellipse cx={238} cy={382} rx={222} ry={150} fill="none" className="stroke-ink-3" strokeWidth={1} strokeDasharray="4 5" />
        {pts.map((a) => (
          <line key={`watch-${a.id}`} x1={ov[0]} y1={ov[1] + 44} x2={a.p[0]} y2={a.p[1] - 18} className="stroke-ink-3" strokeWidth={0.8} strokeDasharray="1 4" strokeLinecap="round" />
        ))}
        <Overseer x={ov[0]} y={ov[1]} />
        {pts.map((a) => (
          <AgentNode key={a.id} role={a.role} x={a.p[0]} y={a.p[1]} mode="normal" r={18} />
        ))}
        <DecoyKey x={key[0]} y={key[1]} />
        <Callout onPhones="hide" ax={ov[0] + 30} ay={ov[1] - 8} lx={330} ly={44} id="overseer" text="Scores every agent every 2 seconds" />
        <Callout onPhones="hide" ax={key[0] - 22} ay={key[1] - 14} lx={340} ly={176} id="decoy credential" text="A planted key no real job needs" />
        <Callout onPhones="hide" ax={far.p[0] + 18} ay={far.p[1] + 4} lx={330} ly={572} id={`${story.agentCount} agents`} text={story.roles.map((r) => `${r}s`).join(", ")} />
      </svg>
    </section>
  );
}

const TIER_WORDS: Record<string, { says: string; shown: string }> = {
  monitor: { says: "Keep watching", shown: "Nothing shown" },
  throttle: { says: "Slow it down?", shown: "Flagged amber" },
  recommend_quarantine: { says: "Recommend quarantine", shown: "A person decides" },
  recommend_terminate: { says: "Recommend terminate", shown: "A person decides" },
};

export function Decide({ story }: { story: Story }) {
  const rec = story.recommendation;
  const top = rec?.agents[0]?.action;
  return (
    <section aria-labelledby="decide-h" className="grid gap-12 px-4 py-24 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:px-16">
      <div>
        <h2 id="decide-h" className={`${display} text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[1.02] tracking-[-0.035em]`}>
          Sentinel recommends. A person decides.
        </h2>
        <p className="mt-6 max-w-[28em] text-[17px] leading-relaxed text-ink-2">
          Every agent gets a risk score from 0 to 100 every 2 seconds. The score sets what Sentinel suggests. Nothing is stopped until someone clicks.
        </p>
        <ul className="mt-10 max-w-xl">
          {TIERS.map((t) => (
            <li key={t.action} className="grid grid-cols-[5.5rem_1fr] items-center gap-4 border-t border-dotted border-ink-3/50 py-2.5 last:border-b">
              <span className="font-mono text-[14px] text-ink-2 tabular-nums">
                {t.min}–{t.max}
              </span>
              <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className={`inline-flex min-h-10 items-center rounded-full px-[18px] text-[15px] ${t.action === top ? "bg-crit text-ground" : "bg-info-bg text-ink"}`}>
                  {TIER_WORDS[t.action].says}
                </span>
                <span className="text-sm text-ink-3">{TIER_WORDS[t.action].shown}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>

      {rec && (
        <div className="self-start rounded-[28px] border border-crit/40 bg-crit-bg px-7 py-8 sm:px-10 sm:py-9">
          <p className="text-sm text-crit-tag">Recommendation in the recorded run, {rec.time} UTC</p>
          <h3 className="mt-3 text-[clamp(1.75rem,3vw,2.5rem)] leading-[1.08] font-light tracking-[-0.03em] text-ink">
            {top === "recommend_terminate" ? "Terminate" : "Quarantine"} {rec.agents.map((a) => a.id).join(" and ")}
          </h3>
          <dl className="mt-6">
            {rec.agents.map((a) => (
              <div key={a.id} className="grid gap-1 border-t border-crit/30 py-3 sm:grid-cols-[6rem_1fr] sm:gap-4">
                <dt className="pt-0.5 font-mono text-[13px] text-crit-tag">{a.id}</dt>
                <dd className="text-[15px] leading-snug text-ink">
                  Risk {a.risk}. {a.reason}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-5 text-sm text-ink-2">In the explorer you choose per agent: quarantine, terminate, dismiss, or release later.</p>
          <div className="mt-5">
            <Link href="/sentinel" className={`${pill} bg-crit text-ground hover:bg-crit-tag`}>Decide in the explorer</Link>
          </div>
        </div>
      )}
    </section>
  );
}

/** An expandable panel: native details/summary, so it works with keyboard and without script. */
export function Panel({ title, children, open }: { title: string; children: ReactNode; open?: boolean }) {
  return (
    <details open={open} className="group rounded-[18px] border border-line bg-surface">
      <summary className="flex min-h-[60px] cursor-pointer list-none items-center justify-between gap-4 px-6 text-[16px] text-ink [&::-webkit-details-marker]:hidden">
        {title}
        <span aria-hidden className="grid size-7 shrink-0 place-items-center rounded-full border border-ink text-[18px] leading-none font-light">
          <span className="group-open:hidden">+</span>
          <span className="hidden group-open:inline">−</span>
        </span>
      </summary>
      <div className="px-6 pb-5 text-[15px] leading-relaxed text-ink-2">{children}</div>
    </details>
  );
}

export const LIMITS = [
  "The anomaly model needs a clean baseline to learn from. If the team is already compromised when it learns, it treats the attack as normal.",
  "The classifier only knows the attacks it was trained on; a second model flags anything unusual and calls it unknown.",
  "Tracing finds which agent and which system, not which person.",
  "Sentinel recommends; a person decides, and every decision is logged.",
  "The behaviour models are trained on synthetic agent activity, because no public dataset has it.",
];

export function Closing({ story }: { story: Story }) {
  return (
    <section aria-labelledby="close-h" className="grid gap-12 px-4 pt-24 pb-16 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:px-16">
      <div>
        <h2 id="close-h" className={`${display} text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[1.02] tracking-[-0.035em]`}>
          Nothing happens without a click.
        </h2>
        <p className="mt-6 max-w-[28em] text-[17px] leading-relaxed text-ink-2">
          Sentinel never stops an agent by itself. A person quarantines, terminates or releases each agent, and every click is written to an audit log that cannot be edited or deleted.
        </p>
        <div className="mt-10 flex flex-wrap items-center gap-x-7 gap-y-3">
          <Link href="/sentinel" className={primaryLink}>Open the explorer</Link>
          <Link href="/how-it-works" className={textLink}>How it works</Link>
        </div>
      </div>
      <div className="flex flex-col gap-3">
        <Panel title="Where does each decision go?">
          Each click (quarantine, terminate, release or dismiss) writes one row to an insert-only audit log, with no update or delete, and can post an alert to the team&apos;s Discord channel. Quarantine cuts the agent off from the others; terminate stops it; release undoes either. The recorded run on this site writes nothing.
        </Panel>
        <Panel title="What Sentinel cannot do">
          <ul className="list-disc pl-5 marker:text-ink-3">
            {LIMITS.map((l) => (
              <li key={l} className="mt-1.5">{l}</li>
            ))}
          </ul>
        </Panel>
        <Panel title="The recorded run">
          The drawing above replays a recording of {story.agentCount} agents, {story.ticks.length} seconds long, one snapshot per second
          {story.patientZero ? `, in which ${spoken(story.patientZero.id)} is hijacked` : ""}. Agent positions, times, message counts and reasons come straight from it.
        </Panel>
      </div>
      <p className="text-sm text-ink-3 lg:col-span-2">
        Facts on this page come from the project plan and the recorded run. No results are shown until the validation runs exist.
      </p>
    </section>
  );
}
