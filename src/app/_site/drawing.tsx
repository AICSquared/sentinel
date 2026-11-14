// Fine-line drawing kit for the public pages: role glyphs, agent nodes, dotted callouts, the overseer
// and the planted credential. Colours come only from the theme tokens (Tailwind stroke-/fill- classes).
import type { Role } from "@/app/sentinel/_lib/contract";

export type NodeMode = "normal" | "flagged" | "infected" | "rogue";

/** A 16 px line glyph per role, centred on (x, y). */
export function RoleGlyph({ role, x, y, className }: { role: Role; x: number; y: number; className: string }) {
  const p = { className, fill: "none", strokeWidth: 1.1, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (role) {
    case "researcher":
      return (
        <g {...p}>
          <circle cx={x - 1.5} cy={y - 1.5} r={4.5} />
          <line x1={x + 1.8} y1={y + 1.8} x2={x + 5.5} y2={y + 5.5} />
        </g>
      );
    case "emailer":
      return (
        <g {...p}>
          <rect x={x - 6.5} y={y - 4.5} width={13} height={9} rx={1} />
          <polyline points={`${x - 6.5},${y - 4.5} ${x},${y + 0.8} ${x + 6.5},${y - 4.5}`} />
        </g>
      );
    case "coder":
      return (
        <g {...p}>
          <polyline points={`${x - 2.5},${y - 5} ${x - 6.5},${y} ${x - 2.5},${y + 5}`} />
          <polyline points={`${x + 2.5},${y - 5} ${x + 6.5},${y} ${x + 2.5},${y + 5}`} />
        </g>
      );
    case "analyst":
      return (
        <g {...p}>
          <line x1={x - 4.5} y1={y + 5} x2={x - 4.5} y2={y + 1} />
          <line x1={x} y1={y + 5} x2={x} y2={y - 5} />
          <line x1={x + 4.5} y1={y + 5} x2={x + 4.5} y2={y - 2} />
        </g>
      );
  }
}

/** One agent: an outlined circle with its role glyph. Rogue = filled; infected = ringed; flagged = amber. */
export function AgentNode({ role, x, y, mode, r = 18 }: { role: Role; x: number; y: number; mode: NodeMode; r?: number }) {
  if (mode === "rogue") {
    return (
      <g>
        <circle cx={x} cy={y} r={r + 2} className="fill-crit" />
        <RoleGlyph role={role} x={x} y={y} className="stroke-ground" />
      </g>
    );
  }
  const ring = mode === "infected" ? "stroke-crit" : mode === "flagged" ? "stroke-warn" : "stroke-ink";
  return (
    <g>
      <circle cx={x} cy={y} r={r} className={`fill-ground ${ring}`} strokeWidth={mode === "normal" ? 1 : 1.4} />
      {mode === "infected" && <circle cx={x} cy={y} r={r + 7} fill="none" className="stroke-crit" strokeWidth={1} strokeDasharray="2 3" />}
      <RoleGlyph role={role} x={x} y={y} className={mode === "infected" ? "stroke-crit" : mode === "flagged" ? "stroke-warn" : "stroke-ink"} />
    </g>
  );
}

/** A small anchor dot, a dotted leader that bends once, then a label (mono id line + plain line). */
export function Callout({
  ax,
  ay,
  lx,
  ly,
  id,
  text,
  align = "start",
  tone = "ink",
  onPhones = "show",
}: {
  ax: number;
  ay: number;
  lx: number;
  ly: number;
  id?: string;
  text: string;
  align?: "start" | "end";
  tone?: "ink" | "crit";
  /** The drawing shrinks on phones, and so would the label: "grow" keeps it readable, "hide" drops it. */
  onPhones?: "show" | "grow" | "hide";
}) {
  const bend = align === "start" ? lx - 8 : lx + 8;
  const tx = align === "start" ? lx + 6 : lx - 6;
  const line = tone === "crit" ? "stroke-crit" : "stroke-ink-3";
  const grow = onPhones === "grow";
  return (
    <g className={onPhones === "hide" ? "max-sm:hidden" : undefined}>
      <circle cx={ax} cy={ay} r={2} className={tone === "crit" ? "fill-crit" : "fill-ink-3"} />
      <polyline points={`${ax},${ay} ${bend},${ly} ${lx},${ly}`} fill="none" className={line} strokeWidth={1} strokeDasharray="1 3" strokeLinecap="round" />
      {id && (
        <text x={tx} y={ly - (grow ? 6 : 3)} textAnchor={align} className={`font-mono text-[12px] ${grow ? "max-sm:text-[17px]" : ""} ${tone === "crit" ? "fill-crit-tag" : "fill-ink"}`}>
          {id}
        </text>
      )}
      <text x={tx} y={ly + (grow ? 20 : 15)} textAnchor={align} className={`fill-ink-2 text-[13px] ${grow ? "max-sm:text-[17px]" : ""}`}>
        {text}
      </text>
    </g>
  );
}

/** Four corner ticks framing a drawing, like a plate in a field guide. */
export function FrameTicks({ w, h }: { w: number; h: number }) {
  const L = 10;
  const c = [
    [0.5, 0.5, 1, 1],
    [w - 0.5, 0.5, -1, 1],
    [0.5, h - 0.5, 1, -1],
    [w - 0.5, h - 0.5, -1, -1],
  ];
  return (
    <g fill="none" className="stroke-ink-3" strokeWidth={1}>
      {c.map(([x, y, dx, dy]) => (
        <polyline key={`${x}-${y}`} points={`${x + dx * L},${y} ${x},${y} ${x},${y + dy * L}`} />
      ))}
    </g>
  );
}

/** The overseer: concentric rings with a single live point. */
export function Overseer({ x, y }: { x: number; y: number }) {
  return (
    <g>
      <circle cx={x} cy={y} r={30} className="fill-ground stroke-ink" strokeWidth={1} />
      <circle cx={x} cy={y} r={44} fill="none" className="stroke-ink" strokeWidth={1} strokeDasharray="1 4" strokeLinecap="round" />
      <circle cx={x} cy={y} r={14} fill="none" className="stroke-ink" strokeWidth={1} />
      <circle cx={x} cy={y} r={3} className="fill-crit" />
    </g>
  );
}

/** The planted credential: a key on a dashed tag. */
export function DecoyKey({ x, y }: { x: number; y: number }) {
  return (
    <g fill="none" className="stroke-ink" strokeWidth={1.1}>
      <rect x={x - 22} y={y - 14} width={44} height={28} rx={6} className="fill-ground stroke-ink" strokeDasharray="3 3" strokeWidth={1} />
      <circle cx={x - 8} cy={y} r={4.5} />
      <polyline points={`${x - 3.5},${y} ${x + 12},${y} ${x + 12},${y + 5}`} />
      <line x1={x + 7} y1={y} x2={x + 7} y2={y + 4} />
    </g>
  );
}
