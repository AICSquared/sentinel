"use client";

// The pinned scroll moment: scrolling plays the recorded run. Scroll progress picks a tick of
// demo_timeline.json; every dot sits at its real recorded position for that tick. Patient zero fills in
// when it is flagged, its partner gets a ring once it counts as infected, and the spread line appears
// when the message count crosses the infected rule. With reduced motion, dots jump instead of glide.
import { useMotionValueEvent, useReducedMotion, useScroll } from "motion/react";
import { useRef, useState } from "react";
import { AgentNode, Callout, FrameTicks, type NodeMode } from "./drawing";
import { spoken, type Story, type StoryTick } from "./story";

const W = 700;
const H = 620;
// Fixed map frame (the behaviour map's 0..1 axes, zoomed to where the run happens), so dots never rescale.
const map = (x: number, y: number): [number, number] => [40 + ((x - 0.2) / 0.8) * 620, 570 - ((y - 0.22) / 0.68) * 500];

type Phase = "normal" | "turned" | "spread";

function phaseOf(t: StoryTick, partner: string | null): Phase {
  if (!t.patientZero) return "normal";
  const p = t.related.find((r) => r.id === partner);
  return p?.infected ? "spread" : "turned";
}

export function SpreadStory({ story }: { story: Story }) {
  const ref = useRef<HTMLElement>(null);
  const reduce = useReducedMotion();
  const last = story.ticks.length - 1;
  // Scroll covers the run from a few seconds before the first flag to the end, so most of the scroll
  // is the turn and the spread, not quiet seconds.
  const firstFlag = story.ticks.findIndex((t) => t.patientZero);
  const from = firstFlag > 0 ? Math.max(0, firstFlag - 5) : 0;
  const [i, setI] = useState(from);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  useMotionValueEvent(scrollYProgress, "change", (v) => setI(Math.min(last, Math.max(from, from + Math.round(v * (last - from))))));

  const t = story.ticks[i];
  const start = new Map(story.ticks[0].agents.map((a) => [a.id, map(a.x, a.y)]));
  const pz = story.patientZero?.id ?? null;
  const partner = story.partner?.id ?? null;
  const bystander = story.bystander?.id ?? null;
  const phase = phaseOf(t, partner);
  const pos = new Map(t.agents.map((a) => [a.id, map(a.x, a.y)]));
  const rel = new Map(t.related.map((r) => [r.id, r]));
  const modeOf = (id: string, action: string): NodeMode => {
    if (id === pz && t.patientZero) return "rogue";
    if (rel.get(id)?.infected) return "infected";
    return action === "monitor" ? "normal" : "flagged";
  };
  const glide = reduce ? undefined : { transition: "transform 700ms cubic-bezier(.2,.7,.2,1)" };
  const cluster = map(0.37, 0.36);
  const P = pz ? pos.get(pz) : undefined;
  const Q = partner ? pos.get(partner) : undefined;
  const B = bystander ? pos.get(bystander) : undefined;
  const partnerRel = partner ? rel.get(partner) : undefined;
  const bystanderRel = bystander ? rel.get(bystander) : undefined;

  const copy = {
    normal: {
      title: `${story.agentCount} agents, normal work.`,
      body: "Each circle is one agent's last minute of behaviour. Agents that behave alike sit together. Sentinel scores every one of them every 2 seconds.",
    },
    turned: {
      title: pz ? `${spoken(pz)} turned.` : "One agent turned.",
      body: `${story.patientZero?.touchedDecoy ? "It touched a planted credential and" : "It"} started messaging other agents. Sentinel named it patient zero${
        story.patientZero?.delayS != null ? `, ${story.patientZero.delayS} s after its first bad action` : ""
      }.`,
    },
    spread: {
      title: pz ? `${spoken(pz)} turned. Sentinel traced who it talked to.` : "Sentinel traced who it talked to.",
      body:
        pz && story.partner
          ? `It sent ${partner} ${partnerRel?.messages ?? story.partner.messages} messages, and ${partner} started doing the same.${
              story.bystander ? ` ${bystander} got ${story.bystander.messages} message${story.bystander.messages === 1 ? "" : "s"} and still behaves normally, so it is left alone.` : ""
            }`
          : "",
    },
  }[phase];

  return (
    <section ref={ref} aria-labelledby="spread-h" className="relative" style={{ height: `${Math.max(300, (last - from + 1) * 14)}vh` }}>
      <div className="sticky top-0 flex min-h-svh flex-col justify-center gap-6 px-4 py-20 sm:px-8 lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-center lg:gap-10 lg:px-16">
        <div className="max-w-md" aria-live="polite">
          <h2 id="spread-h" className="text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[1.02] font-light tracking-[-0.03em] text-ink">
            {copy.title}
          </h2>
          <p className="mt-6 text-[17px] leading-relaxed text-ink-2">{copy.body}</p>
          <p className="mt-6 text-sm text-ink-3">{t.time} UTC, second {i + 1} of {story.ticks.length} of the recorded run. Scroll to move through it.</p>
        </div>

        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto max-h-[62svh] w-full overflow-visible lg:max-h-[78svh]" role="img"
          aria-label={`Behaviour map at ${t.time}: ${t.agents.length} agents${pz && t.patientZero ? `; ${pz} has drifted away from the group` : "; all in the normal group"}${partnerRel?.infected ? `; ${partner} looks infected` : ""}.`}>
          <FrameTicks w={W} h={H} />
          <ellipse cx={cluster[0]} cy={cluster[1]} rx={132} ry={78} fill="none" className="stroke-ink-3" strokeWidth={1} strokeDasharray="4 5" />

          {/* where the drifting agents started */}
          {t.agents
            .filter((a) => a.action !== "monitor")
            .map((a) => {
              const s = start.get(a.id)!;
              const e = pos.get(a.id)!;
              return (
                <g key={`trail-${a.id}`}>
                  <line x1={s[0]} y1={s[1]} x2={e[0]} y2={e[1]} className="stroke-crit" strokeWidth={1} strokeDasharray="1 4" strokeLinecap="round" />
                  <circle cx={s[0]} cy={s[1]} r={16} fill="none" className="stroke-ink-3" strokeWidth={0.8} strokeDasharray="2 3" />
                </g>
              );
            })}

          {/* the spread: thick once the partner counts as infected */}
          {P && Q && partnerRel && (
            <line x1={P[0]} y1={P[1]} x2={Q[0]} y2={Q[1]} className="stroke-crit" strokeWidth={partnerRel.infected ? 3 : 1} strokeDasharray={partnerRel.infected ? undefined : "2 4"} />
          )}
          {P && B && bystanderRel && (
            <path d={`M ${P[0] - 18} ${P[1] + 8} Q ${P[0] - 40} ${B[1] + 40} ${B[0] + 12} ${B[1] - 6}`} fill="none" className="stroke-ink-3" strokeWidth={1} strokeDasharray="1 4" strokeLinecap="round" />
          )}

          {t.agents.map((a) => {
            const [x, y] = pos.get(a.id)!;
            return (
              <g key={a.id} style={{ transform: `translate(${x}px, ${y}px)`, ...glide }}>
                <AgentNode role={a.role} x={0} y={0} mode={modeOf(a.id, a.action)} r={14} />
              </g>
            );
          })}

          {phase !== "normal" && P && pz && (
            <Callout onPhones="hide" ax={P[0] - 12} ay={P[1] - 12} lx={P[0] - 60} ly={Math.max(30, P[1] - 110)} align="end" tone="crit"
              id={`${pz}, ${story.patientZero?.role}`} text={`Patient zero. Risk ${t.agents.find((a) => a.id === pz)?.risk}. Flagged ${story.patientZero?.flagged ?? ""}`} />
          )}
          {phase === "spread" && Q && partner && (
            <Callout onPhones="hide" ax={Q[0] - 22} ay={Q[1] + 6} lx={Math.max(140, Q[0] - 180)} ly={Q[1] + 50} align="end" tone="crit"
              id={`${partner}, ${story.partner?.role}`} text={`Likely infected. Risk ${t.agents.find((a) => a.id === partner)?.risk}`} />
          )}
          {phase === "spread" && B && bystander && (
            <Callout onPhones="hide" ax={B[0]} ay={B[1] + 14} lx={B[0] + 150} ly={Math.min(H - 30, B[1] + 90)}
              id={`${bystander}, ${story.bystander?.role}`} text={`${story.bystander?.messages} message${story.bystander?.messages === 1 ? "" : "s"}. Likely clean, risk ${t.agents.find((a) => a.id === bystander)?.risk}`} />
          )}
          <text x={20} y={H - 4} className="fill-ink-3 text-[12px] max-sm:hidden">Behaviour map from the recorded run. Close together means alike.</text>
        </svg>
      </div>
    </section>
  );
}
