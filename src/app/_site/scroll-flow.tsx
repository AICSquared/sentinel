"use client";

// The incident as one light spreading through a calm team, driven by scrolling. The section pins; the scroll
// position is the clock (no autoplay, no player). Eight agents drift like a loose constellation. As you scroll,
// one of them turns the site's red-orange, red light flows along the thread to the agent it infected, which
// ignites in turn, and then a person approves. Scroll back and it un-turns. Nothing about the incident plays by
// itself; only the calm background (the dots drifting, the faint message lights) is alive on its own. Every name,
// time and count comes from the recorded run through incident.ts.
//
// Motion (Emil Kowalski's rules): the picture chases the scroll position with an exponential approach (fast
// first, then it settles), so it feels fluid in both directions instead of stepping; each ignition is one ripple
// plus one surge of light; nothing runs while the section is off screen. Reduced motion draws a still frame that
// follows the scroll without drift, flow or smoothing. Colours are read from the site's tokens; nothing is added.
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { buildIncident, type Tier } from "./incident";
import { spoken, type Story } from "./story";

const REDUCED = "(prefers-reduced-motion: reduce)";
const reducedNow = () => window.matchMedia(REDUCED).matches;

// Where the agents sit, as fractions of the canvas. The first slots are the infection's path (patient zero, then
// whoever it turned, in order), a loose S across the picture; the quiet agents fill the rest.
const SPOTS: [number, number][] = [
  [0.13, 0.52], [0.38, 0.3], [0.62, 0.62], [0.86, 0.36], [0.28, 0.84], [0.55, 0.9], [0.6, 0.12], [0.1, 0.14],
];
const PARTICLES = 340;
const INFECTS_AT = 10; // messages at which a partner counts as infected (the product's rule)
const mix = (c: string, a: number) => `color-mix(in srgb, ${c} ${Math.round(a * 100)}%, transparent)`;
const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const list = (names: string[]) => (names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);

type Palette = { crit: string; ink: string; ink2: string; ink3: string; mono: string };
function readPalette(): Palette {
  const cs = getComputedStyle(document.documentElement);
  const get = (n: string, f: string) => cs.getPropertyValue(n).trim() || f;
  return {
    crit: get("--color-crit", "#f0716a"),
    ink: get("--color-ink", "#e8eaed"),
    ink2: get("--color-ink-2", "#b8bdc6"),
    ink3: get("--color-ink-3", "#8f96a1"),
    mono: getComputedStyle(document.body).getPropertyValue("--font-mono").trim() || "ui-monospace, SFMono-Regular, Menlo, monospace",
  };
}

type Particle = { e: number; t: number; dir: 1 | -1; v: number; r: number };
type Sim = {
  w: number;
  h: number;
  dpr: number;
  heat: number[];
  prevTier: Tier[] | null;
  parts: Particle[];
  ripples: { i: number; t0: number }[];
  surge: Map<number, number>;
  burst: number;
  hover: number;
  shown: number; // the tick the picture is showing right now (it chases the scroll target)
  pal: Palette;
};

export function ScrollFlow({ story, children }: { story: Story; children?: ReactNode }) {
  const inc = useMemo(() => buildIncident(story), [story]);
  const N = inc.ticks;
  // Scroll covers the run from a few seconds before the first flag to the end, so almost none of it is spent on quiet seconds.
  const firstFlag = inc.flags.length ? inc.flags[0].tick : 0;
  const from = Math.max(0, firstFlag - 6);
  const span = N - 1 - from;
  const screens = Math.min(460, Math.max(300, (span + 1) * 8));

  // Every pair that ever messaged gets a faint thread, so the team at rest is visibly talking; the ones that carry
  // the infection turn red-orange as it reaches them.
  const edges = useMemo(() => {
    const idx = new Map(inc.rows.map((r, i) => [r.id, i]));
    const key = (a: number, b: number) => (a < b ? `${a}|${b}` : `${b}|${a}`);
    const strength = new Map<string, number[]>();
    story.ticks.forEach((t, ti) => {
      for (const l of t.links) {
        const a = idx.get(l.from);
        const b = idx.get(l.to);
        if (a === undefined || b === undefined || a === b) continue;
        const k = key(a, b);
        let arr = strength.get(k);
        if (!arr) strength.set(k, (arr = new Array<number>(N).fill(0)));
        arr[ti] = Math.max(arr[ti], l.messages);
      }
    });
    const chain = new Set(inc.arcs.map((a) => key(idx.get(a.from)!, idx.get(a.to)!)));
    return [...strength.entries()]
      .filter(([k, arr]) => chain.has(k) || Math.max(...arr) >= 1)
      .map(([k, arr], i) => {
        const [a, b] = k.split("|").map(Number);
        return { a, b, s: arr, bend: (i % 2 ? 1 : -1) * (0.1 + 0.07 * ((i * 5) % 3)), phase: i * 1.3 };
      });
  }, [story, inc, N]);

  const [tick, setTick] = useState(from);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const target = useRef(from); // where the scroll says we are, in ticks (fractional)
  const tickRef = useRef(from);
  const kick = useRef<() => void>(() => {});
  const redraw = useRef<() => void>(() => {});

  useEffect(() => {
    const canvas = canvasRef.current!;
    const box = boxRef.current!;
    const ctx = canvas.getContext("2d")!;
    const sim: Sim = {
      w: 0,
      h: 0,
      dpr: 1,
      heat: inc.rows.map(() => 0),
      prevTier: null,
      parts: [],
      ripples: [],
      surge: new Map(),
      burst: 0,
      hover: -1,
      shown: from,
      pal: readPalette(),
    };
    const rnd = (a: number, b: number) => a + Math.random() * (b - a);
    const pickEdge = (f: number) => {
      const ti = clamp(Math.floor(f), 0, N - 1);
      const w = edges.map((e) => 0.2 + e.s[ti] / 22);
      let x = Math.random() * w.reduce((s, v) => s + v, 0);
      for (let i = 0; i < w.length; i++) if ((x -= w[i]) <= 0) return i;
      return w.length - 1;
    };
    const spawn = (f: number): Particle => ({ e: pickEdge(f), t: Math.random(), dir: Math.random() < 0.5 ? 1 : -1, v: rnd(0.09, 0.2), r: rnd(1, 1.7) });
    sim.parts = edges.length ? Array.from({ length: PARTICLES }, () => spawn(from)) : [];

    const pos = (i: number, now: number, animate: boolean): [number, number] => {
      const [fx, fy] = SPOTS[i % SPOTS.length];
      const dx = animate ? Math.sin(now * 0.00033 + i * 1.9) * sim.w * 0.007 : 0;
      const dy = animate ? Math.cos(now * 0.00029 + i * 2.3) * sim.h * 0.012 : 0;
      return [sim.w * (0.07 + 0.86 * fx) + dx, sim.h * (0.1 + 0.8 * fy) + dy];
    };
    const ctrl = (a: [number, number], b: [number, number], bend: number, ph: number, now: number, animate: boolean): [number, number] => {
      const mx = (a[0] + b[0]) / 2;
      const my = (a[1] + b[1]) / 2;
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      const sway = animate ? Math.sin(now * 0.0005 + ph) * 0.03 : 0;
      return [mx - dy * (bend + sway), my + dx * (bend + sway)];
    };
    const bez = (a: [number, number], c: [number, number], b: [number, number], t: number): [number, number] => {
      const u = 1 - t;
      return [u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]];
    };

    const draw = (now: number, dt: number, f: number, animate: boolean) => {
      const { w, h, pal } = sim;
      if (!w || !h) return;
      const ti = clamp(Math.floor(f + 1e-6), 0, N - 1);
      ctx.setTransform(sim.dpr, 0, 0, sim.dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const P = inc.rows.map((_, i) => pos(i, now, animate));

      // ignition: the moment the picture shows a node becoming flagged, one ripple and one surge along the thread that infected it
      const tiers = inc.rows.map((r) => r.tiers[ti]);
      if (sim.prevTier) {
        tiers.forEach((t, i) => {
          if (t === 2 && sim.prevTier![i] !== 2 && animate) {
            sim.ripples.push({ i, t0: now });
            const arc = inc.arcs.find((a) => a.to === inc.rows[i].id);
            if (arc) {
              const si = inc.rows.findIndex((r) => r.id === arc.from);
              const ei = edges.findIndex((e) => (e.a === si && e.b === i) || (e.a === i && e.b === si));
              if (ei >= 0) {
                sim.surge.set(ei, now + 1800);
                for (let k = 0; k < 30; k++) {
                  const p = sim.parts[sim.burst++ % sim.parts.length];
                  p.e = ei;
                  p.dir = edges[ei].a === si ? 1 : -1;
                  p.t = p.dir > 0 ? -k * 0.028 : 1 + k * 0.028;
                  p.v = 0.5;
                  p.r = 1.9;
                }
              }
            }
          }
        });
      }
      sim.prevTier = tiers;

      // heat eases toward its target (exponential approach: fast first, then settles)
      const k = animate ? 1 - Math.exp(-dt / 240) : 1;
      tiers.forEach((t, i) => {
        const goal = t === 2 ? 1 : t === 1 ? 0.4 : 0;
        sim.heat[i] += (goal - sim.heat[i]) * k;
      });

      // which way each node's threads leave it (so its label can sit on the opposite side)
      const pull = inc.rows.map(() => [0, 0] as [number, number]);
      edges.forEach((e) => {
        const s = Math.min(1, e.s[ti] / 10);
        if (!s) return;
        const dx = P[e.b][0] - P[e.a][0];
        const dy = P[e.b][1] - P[e.a][1];
        const d = Math.hypot(dx, dy) || 1;
        pull[e.a][0] += (dx / d) * s;
        pull[e.a][1] += (dy / d) * s;
        pull[e.b][0] -= (dx / d) * s;
        pull[e.b][1] -= (dy / d) * s;
      });

      // threads: grey while calm, red-orange once an end of it is hot and it carries the infection rule's worth of messages
      ctx.lineCap = "round";
      edges.forEach((e, ei) => {
        const s = e.s[ti];
        const hot = s >= INFECTS_AT && (sim.heat[e.a] > 0.5 || sim.heat[e.b] > 0.5);
        const c = ctrl(P[e.a], P[e.b], e.bend, e.phase, now, animate);
        ctx.beginPath();
        ctx.moveTo(P[e.a][0], P[e.a][1]);
        ctx.quadraticCurveTo(c[0], c[1], P[e.b][0], P[e.b][1]);
        ctx.lineWidth = 1 + Math.min(1, s / 30) * 1.5;
        ctx.strokeStyle = hot || (sim.surge.get(ei) ?? 0) > now ? mix(pal.crit, 0.28 + 0.3 * Math.min(1, s / 30)) : mix(pal.ink3, 0.07 + 0.2 * Math.min(1, s / 20));
        ctx.stroke();
      });

      // the lights flowing along the threads
      ctx.globalCompositeOperation = "lighter";
      for (const p of sim.parts) {
        if (animate) {
          p.t += p.dir * p.v * (dt / 1000) * (0.6 + edges[p.e].s[ti] / 28);
          if ((p.dir > 0 && p.t > 1) || (p.dir < 0 && p.t < 0)) {
            // arrived: start again on a thread chosen by its current strength, from its start end
            const next = spawn(f);
            p.e = next.e;
            p.dir = next.dir;
            p.v = next.v;
            p.r = next.r;
            p.t = next.dir > 0 ? 0 : 1;
          }
        }
        if (p.t < 0 || p.t > 1) continue;
        const e = edges[p.e];
        const src = p.dir > 0 ? e.a : e.b;
        const red = (sim.heat[src] > 0.5 && e.s[ti] >= INFECTS_AT / 2) || ((sim.surge.get(p.e) ?? 0) > now && p.v > 0.4);
        const c = ctrl(P[e.a], P[e.b], e.bend, e.phase, now, animate);
        const [x, y] = bez(P[e.a], c, P[e.b], p.t);
        ctx.fillStyle = red ? mix(pal.crit, 0.8) : mix(pal.ink3, 0.5);
        ctx.beginPath();
        ctx.arc(x, y, p.r, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = red ? mix(pal.crit, 0.1) : mix(pal.ink3, 0.05);
        ctx.beginPath();
        ctx.arc(x, y, p.r * 3.4, 0, Math.PI * 2);
        ctx.fill();
      }

      // nodes: a soft light that grows with heat, a core, and a ring
      inc.rows.forEach((_, i) => {
        const [x, y] = P[i];
        const hh = sim.heat[i];
        if (hh > 0.02) {
          const g = ctx.createRadialGradient(x, y, 0, x, y, 26 + 70 * hh);
          g.addColorStop(0, mix(pal.crit, 0.5 * hh));
          g.addColorStop(1, mix(pal.crit, 0));
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(x, y, 26 + 70 * hh, 0, Math.PI * 2);
          ctx.fill();
        }
      });
      ctx.globalCompositeOperation = "source-over";
      inc.rows.forEach((r, i) => {
        const [x, y] = P[i];
        const hh = sim.heat[i];
        const hovered = sim.hover === i;
        ctx.beginPath();
        ctx.arc(x, y, 7 + 6 * hh + (hovered ? 2 : 0), 0, Math.PI * 2);
        ctx.fillStyle = hh > 0.5 ? pal.crit : mix(pal.ink3, 0.9);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(x, y, 15 + 7 * hh, 0, Math.PI * 2);
        ctx.strokeStyle = hh > 0.5 ? mix(pal.crit, 0.7) : mix(pal.ink3, 0.35);
        ctx.lineWidth = 1;
        ctx.stroke();
        // The label goes on the side away from the threads, so it never sits on a stream of light.
        const [vx, vy] = pull[i];
        const mag = Math.hypot(vx, vy);
        const side = mag < 0.25 ? (x < w * 0.8 ? "r" : "l") : Math.abs(vx) >= Math.abs(vy) * 0.8 ? (vx > 0 ? "l" : "r") : vy > 0 ? "t" : "b";
        const lit = hh > 0.5 && r.flaggedAt !== null;
        const reach = 26 + 6 * hh;
        const lx = side === "r" ? x + reach : side === "l" ? x - reach : x;
        const ly = side === "t" ? y - reach - (lit ? 16 : 4) : side === "b" ? y + reach + 4 : y - (lit ? 8 : 0);
        ctx.textAlign = side === "r" ? "left" : side === "l" ? "right" : "center";
        ctx.textBaseline = "middle";
        ctx.font = `${hh > 0.5 || hovered ? 14 : 12}px ${pal.mono}`;
        ctx.fillStyle = hh > 0.5 || hovered ? pal.ink : mix(pal.ink3, 0.9);
        ctx.fillText(r.id, lx, ly);
        if (lit) {
          ctx.font = `11px ${pal.mono}`;
          ctx.fillStyle = mix(pal.ink2, 0.9);
          ctx.fillText(`flagged ${inc.times[r.flaggedAt!]}`, lx, ly + 16);
        }
      });

      // ripples from each ignition
      sim.ripples = sim.ripples.filter((rp) => now - rp.t0 < 1300);
      for (const rp of sim.ripples) {
        const a = (now - rp.t0) / 1300;
        const e = 1 - Math.pow(1 - a, 3);
        ctx.beginPath();
        ctx.arc(P[rp.i][0], P[rp.i][1], 18 + 120 * e, 0, Math.PI * 2);
        ctx.strokeStyle = mix(pal.crit, 0.7 * (1 - a));
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    };

    // The loop: the shown tick chases the scroll target, and the picture is drawn from it.
    let raf = 0;
    let last = performance.now();
    let visible = false;
    const frame = (now: number) => {
      raf = 0;
      const dt = Math.min(64, now - last);
      last = now;
      sim.shown += (target.current - sim.shown) * (1 - Math.exp(-dt / 170));
      if (Math.abs(target.current - sim.shown) < 0.002) sim.shown = target.current;
      draw(now, dt, sim.shown, true);
      if (visible) raf = requestAnimationFrame(frame);
    };
    const start = () => {
      if (!raf && visible && !reducedNow()) {
        last = performance.now();
        raf = requestAnimationFrame(frame);
      }
    };
    kick.current = start;
    redraw.current = () => {
      sim.shown = target.current;
      draw(performance.now(), 0, sim.shown, false);
    };

    // The scroll position is the clock.
    const section = sectionRef.current!;
    const onScroll = () => {
      const r = section.getBoundingClientRect();
      const room = r.height - window.innerHeight;
      const p = room > 0 ? clamp(-r.top / room) : 1;
      // a short hold at each end, so the calm team and the final picture each get a moment to rest
      const f = from + clamp((p - 0.05) / 0.88) * span;
      target.current = f;
      const t = Math.floor(f + 1e-6);
      if (t !== tickRef.current) {
        tickRef.current = t;
        setTick(t);
      }
      if (reducedNow()) redraw.current();
      else start();
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);

    const resize = () => {
      sim.dpr = Math.min(2, window.devicePixelRatio || 1);
      sim.w = box.clientWidth;
      sim.h = box.clientHeight;
      canvas.width = Math.round(sim.w * sim.dpr);
      canvas.height = Math.round(sim.h * sim.dpr);
      sim.pal = readPalette();
      if (reducedNow() || !raf) redraw.current();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(box);
    resize();

    const onMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      let best = -1;
      let bd = 30 * 30;
      inc.rows.forEach((_, i) => {
        const [x, y] = pos(i, performance.now(), false);
        const d = (x - mx) ** 2 + (y - my) ** 2;
        if (d < bd) {
          bd = d;
          best = i;
        }
      });
      if (best !== sim.hover) {
        sim.hover = best;
        setHoverId(best >= 0 ? inc.rows[best].id : null);
        if (reducedNow()) redraw.current();
      }
    };
    const onLeave = () => {
      sim.hover = -1;
      setHoverId(null);
      if (reducedNow()) redraw.current();
    };
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerleave", onLeave);

    // Draw only while the pinned section is on screen.
    const io = new IntersectionObserver(
      ([e]) => {
        visible = e.isIntersecting;
        if (visible) {
          onScroll();
          start();
        }
      },
      { threshold: 0 },
    );
    io.observe(section);
    onScroll();
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
    };
  }, [inc, edges, N, from, span]);

  // What the words say follows the scroll: calm, then the first flag, then the spread, then the person.
  const flaggedNow = inc.rows.filter((r) => r.tiers[tick] === 2);
  const arcsNow = inc.arcs.filter((a) => a.tick <= tick);
  const pz = inc.rows.find((r) => r.flaggedAt === firstFlag && inc.flags[0]?.kind === "turned");
  const decided = inc.approvedAt !== null && tick >= inc.approvedAt;
  const phase = decided ? "decided" : arcsNow.length ? "spread" : flaggedNow.length ? "turned" : "calm";
  const secs = (a: number, b: number) => Math.max(0, Math.round((Date.parse(story.ticks[b].at) - Date.parse(story.ticks[a].at)) / 1000));
  const delay = story.patientZero?.delayS;
  const copy = {
    calm: { title: `${inc.rows.length} agents, normal work.`, body: "Each light is a message between agents. Sentinel scores every agent every 2 seconds." },
    turned: {
      title: pz ? `${spoken(pz.id)} turned.` : inc.title,
      body: `Sentinel flagged it ${delay == null ? "" : delay <= 0 ? "at once" : `in ${delay} s`}. Its messages now run red.`.replace(" .", "."),
    },
    spread: {
      title: arcsNow.length > 2 ? `It spread to ${arcsNow.length} more agents.` : `It spread to ${list(arcsNow.map((a) => spoken(a.to)))}.`,
      body: arcsNow.map((a) => `${spoken(a.from)} sent ${spoken(a.to)} ${a.messages} messages before it turned.`).join(" "),
    },
    decided: {
      title: "A person decided.",
      body: `Sentinel recommended; a person approved at ${inc.times[inc.approvedAt ?? tick]} UTC, ${inc.approvedAt !== null && firstFlag >= 0 ? secs(firstFlag, inc.approvedAt) : 0} s after the first flag.`,
    },
  }[phase];
  const hovered = hoverId ? inc.rows.find((r) => r.id === hoverId) : null;
  const progress = span > 0 ? clamp((tick - from) / span) : 1;
  const mark = (t: number) => `${clamp((t - from) / span) * 100}%`;

  return (
    <section ref={sectionRef} aria-labelledby="incident-h" className="relative" style={{ height: `${screens}vh` }}>
      <div className="sticky top-0 flex h-svh min-h-[34rem] flex-col justify-center gap-6 px-4 py-14 sm:px-8 lg:px-16">
        <div className="flex flex-wrap items-end justify-between gap-x-12 gap-y-4">
          {/* the words change with the scroll; each change is one short fade-in, not a replay */}
          <div key={phase} className="max-w-[44rem] transition-[opacity,translate] duration-300 ease-[cubic-bezier(0.23,1,0.32,1)] starting:translate-y-2 starting:opacity-0 motion-reduce:starting:translate-y-0">
            {/* Fixed boxes: two lines for the headline, three for the sentence, whatever the words. The text
                changes inside them, so nothing below ever moves as you scroll. */}
            <h2 id="incident-h" className="flex h-[2.04em] items-end overflow-hidden text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[1.02] font-light tracking-[-0.03em] text-ink">
              <span>{copy.title}</span>
            </h2>
            <p className="mt-4 h-[7.2rem] max-w-[36em] overflow-hidden text-[17px] leading-relaxed text-ink-2 sm:h-[5.2rem]">{copy.body}</p>
          </div>
          {children}
        </div>

        <div ref={boxRef} className="relative h-[clamp(260px,44svh,440px)] w-full">
          <canvas ref={canvasRef} aria-hidden className="absolute inset-0 size-full touch-pan-y" />
        </div>

        {/* where you are in the run: a thin line that fills as you scroll, with a dot for each flag and the approval */}
        <div className="grid items-center gap-x-6 lg:grid-cols-[minmax(0,1fr)_26rem]" aria-hidden>
          <div className="relative h-px bg-ink-3/50">
            <div className="absolute inset-y-0 left-0 w-full origin-left bg-ink transition-transform duration-150 ease-out motion-reduce:transition-none" style={{ transform: `scaleX(${progress})` }} />
            {inc.flags.map((f) => (
              <span
                key={`${f.kind}-${f.tick}`}
                className={`absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full ${f.kind === "approved" ? "bg-ink" : "bg-crit"}`}
                style={{ left: mark(f.tick) }}
              />
            ))}
          </div>
          <p className="mt-3 h-12 overflow-hidden text-[15px] text-ink-2 lg:mt-0 lg:h-6 lg:whitespace-nowrap">
            {hovered ? (
              <>
                <span className="font-mono text-ink">{hovered.id}</span>, {hovered.role}, {hovered.flaggedAt !== null ? `flagged ${inc.times[hovered.flaggedAt]} UTC` : "never flagged"}, peak risk {hovered.peak}
              </>
            ) : (
              <>
                <span className="font-mono text-ink">{inc.times[tick]} UTC</span>, {flaggedNow.length === 0 ? "all agents normal" : `${flaggedNow.length} of ${inc.rows.length} flagged`}
              </>
            )}
          </p>
        </div>
      </div>

      {/* the same incident as text, in order, for anyone not looking at the picture */}
      <ol className="sr-only">
        {inc.flags.map((f) => (
          <li key={`${f.kind}-${f.tick}`}>
            {f.time} UTC: {f.text}.
          </li>
        ))}
        {inc.arcs.map((a) => (
          <li key={`${a.from}-${a.to}`}>
            {inc.times[a.tick]} UTC: {spoken(a.to)} turned after {spoken(a.from)} sent it {a.messages} messages.
          </li>
        ))}
      </ol>
    </section>
  );
}
