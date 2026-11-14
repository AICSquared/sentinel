"use client";

// The pinned scroll moment: scrolling plays the recorded run. Scroll progress picks a tick of
// demo_timeline.json; every dot sits at its real recorded position for that tick. Patient zero fills in
// when it is flagged, its partner gets a ring once it counts as infected, and the spread line thickens
// when the message count crosses the infected rule.
//
// Motion (Emil Kowalski's rules, see drawing.tsx): dots, the lines that join them and the callouts that name
// them all glide with the same curve and duration, so nothing runs ahead of the thing it is attached to. A
// state change (rogue fill, infected ring, a line, a callout) is a 200 ms fade, never a pop. Every one of
// these is a CSS transition, so a fast scroll retargets from where each element is instead of restarting.
// Under reduced motion the dots and lines jump and only the opacity changes remain.
import { useMotionValueEvent, useScroll } from "motion/react";
import { type CSSProperties, useMemo, useRef, useState } from "react";
import { AgentNode, Callout, EASE_OUT, FrameTicks, GLIDE, type NodeMode } from "./drawing";
import { everyAgent, fitFrame, restingEllipse } from "./frame";
import { spoken, type Story, type StoryTick } from "./story";

const W = 700;
const H = 620;
// Where the map is drawn inside the 700 x 620 plate. The projection into it comes from the recording itself.
const BOX = { left: 60, top: 80, right: 640, bottom: 560 };

type Phase = "normal" | "turned" | "spread";

function phaseOf(t: StoryTick, partner: string | null): Phase {
  if (!t.patientZero) return "normal";
  const p = t.related.find((r) => r.id === partner);
  return p?.infected ? "spread" : "turned";
}

// A line that glides: its endpoints move with the same curve and duration as the dots (the CSS `d` property
// transitions between two paths of the same shape; a browser without it just jumps, as it did before).
const LINE_MOTION = `[transition:d_500ms_cubic-bezier(0.23,1,0.32,1),opacity_200ms_cubic-bezier(0.23,1,0.32,1)] motion-reduce:[transition:opacity_200ms_cubic-bezier(0.23,1,0.32,1)]`;

function Line({ d, show = true, className, dash, width = 1 }: { d: string; show?: boolean; className: string; dash?: string; width?: number }) {
  return (
    <path
      d={d}
      style={{ d: `path("${d}")` } as CSSProperties}
      fill="none"
      strokeWidth={width}
      strokeDasharray={dash}
      strokeLinecap="round"
      className={`${className} ${LINE_MOTION} ${show ? "opacity-100" : "opacity-0"}`}
    />
  );
}

const seg = (a: [number, number], b: [number, number]) => `M ${a[0]} ${a[1]} L ${b[0]} ${b[1]}`;

export function SpreadStory({ story }: { story: Story }) {
  const ref = useRef<HTMLElement>(null);
  const last = story.ticks.length - 1;
  // Scroll covers the run from a few seconds before the first flag to the end, so most of the scroll
  // is the turn and the spread, not quiet seconds.
  const firstFlag = story.ticks.findIndex((t) => t.patientZero);
  const from = firstFlag > 0 ? Math.max(0, firstFlag - 5) : 0;
  const [i, setI] = useState(from);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  useMotionValueEvent(scrollYProgress, "change", (v) => setI(Math.min(last, Math.max(from, from + Math.round(v * (last - from))))));

  // The frame and the dashed "normal group" ring come from where this recording's agents actually sit.
  const project = useMemo(() => fitFrame(everyAgent(story), BOX), [story]);
  const ring = useMemo(() => restingEllipse(story, project, 60, 1.45, BOX), [story, project]);

  const t = story.ticks[i];
  const start = new Map(story.ticks[0].agents.map((a) => [a.id, project(a.x, a.y)]));
  const pz = story.patientZero?.id ?? null;
  const partner = story.partner?.id ?? null;
  const bystander = story.bystander?.id ?? null;
  const phase = phaseOf(t, partner);
  const pos = new Map(t.agents.map((a) => [a.id, project(a.x, a.y)]));
  const rel = new Map(t.related.map((r) => [r.id, r]));
  const modeOf = (id: string, action: string): NodeMode => {
    if (id === pz && t.patientZero) return "rogue";
    if (rel.get(id)?.infected) return "infected";
    return action === "monitor" ? "normal" : "flagged";
  };
  const P = pz ? pos.get(pz) : undefined;
  const Q = partner ? pos.get(partner) : undefined;
  const B = bystander ? pos.get(bystander) : undefined;
  const partnerRel = partner ? rel.get(partner) : undefined;
  const bystanderRel = bystander ? rel.get(bystander) : undefined;
  const riskOf = (id: string | null) => t.agents.find((a) => a.id === id)?.risk;
  const follow = (p: [number, number]): CSSProperties => ({ transform: `translate(${p[0]}px, ${p[1]}px)` });
  const followClass = `transition-transform ${GLIDE}`;

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

  // One screen per ~9 ticks, between 3 and 4.8 screens: a longer recording must not mean a longer scroll.
  const screens = Math.min(480, Math.max(300, (last - from + 1) * 9));

  return (
    <section ref={ref} aria-labelledby="spread-h" className="relative" style={{ height: `${screens}vh` }}>
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
          <ellipse cx={ring.cx} cy={ring.cy} rx={ring.rx} ry={ring.ry} fill="none" className="stroke-ink-3" strokeWidth={1} strokeDasharray="4 5" />

          {/* where the drifting agents started, and the trail they left: drawn for every agent, shown for the flagged */}
          {t.agents.map((a) => {
            const s = start.get(a.id)!;
            const e = pos.get(a.id)!;
            const drifting = a.action !== "monitor";
            return (
              <g key={`trail-${a.id}`}>
                <Line d={seg(s, e)} show={drifting} className="stroke-crit" dash="1 4" />
                <circle cx={s[0]} cy={s[1]} r={16} fill="none" strokeWidth={0.8} strokeDasharray="2 3"
                  className={`stroke-ink-3 transition-opacity duration-200 ${EASE_OUT} ${drifting ? "opacity-100" : "opacity-0"}`} />
              </g>
            );
          })}

          {/* the spread: dotted until the partner counts as infected, then solid and thick (a crossfade, not a swap) */}
          {P && Q && partnerRel && (
            <>
              <Line d={seg(P, Q)} show={!partnerRel.infected} className="stroke-crit" dash="2 4" />
              <Line d={seg(P, Q)} show={partnerRel.infected} className="stroke-crit" width={3} />
            </>
          )}
          {P && B && (
            <Line d={`M ${P[0] - 18} ${P[1] + 8} Q ${P[0] - 40} ${B[1] + 40} ${B[0] + 12} ${B[1] - 6}`} show={!!bystanderRel} className="stroke-ink-3" dash="1 4" />
          )}

          {t.agents.map((a) => (
            <g key={a.id} className={followClass} style={follow(pos.get(a.id)!)}>
              <AgentNode role={a.role} x={0} y={0} mode={modeOf(a.id, a.action)} r={14} />
            </g>
          ))}

          {/* callouts ride on the agent they name, so they glide with it instead of jumping ahead of it */}
          {P && pz && (
            <g className={followClass} style={follow(P)}>
              <Callout show={phase !== "normal"} onPhones="hide" ax={-12} ay={-12} lx={-60} ly={Math.max(30 - P[1], -110)} align="end" tone="crit"
                id={`${pz}, ${story.patientZero?.role}`} text={`Patient zero. Risk ${riskOf(pz)}. Flagged ${story.patientZero?.flagged ?? ""}`} />
            </g>
          )}
          {Q && partner && (
            <g className={followClass} style={follow(Q)}>
              <Callout show={phase === "spread"} onPhones="hide" ax={-22} ay={6} lx={Math.max(140 - Q[0], -180)} ly={50} align="end" tone="crit"
                id={`${partner}, ${story.partner?.role}`} text={`Likely infected. Risk ${riskOf(partner)}`} />
            </g>
          )}
          {B && bystander && (
            <g className={followClass} style={follow(B)}>
              <Callout show={phase === "spread"} onPhones="hide" ax={0} ay={14} lx={150} ly={Math.min(H - 30 - B[1], 90)}
                id={`${bystander}, ${story.bystander?.role}`} text={`${story.bystander?.messages} message${story.bystander?.messages === 1 ? "" : "s"}. Likely clean, risk ${riskOf(bystander)}`} />
            </g>
          )}
          <text x={20} y={H - 4} className="fill-ink-3 text-[12px] max-sm:hidden">Behaviour map from the recorded run. Close together means alike.</text>
        </svg>
      </div>
    </section>
  );
}
