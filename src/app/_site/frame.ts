// Fits the behaviour-map drawings to the recording they show, so they never depend on where one particular
// recording happened to put its agents. Every position comes from story.ts (demo_timeline.json): the resting
// group is the agents before the first flag, the full run is every agent at every tick.
import type { Story, StoryAgent } from "./story";

export type Project = (x: number, y: number) => [number, number];
export type Box = { left: number; top: number; right: number; bottom: number };
export type Ellipse = { cx: number; cy: number; rx: number; ry: number };

/** Agents as they sat before anything was flagged (tick 0 when nothing is flagged in the run). */
export function restingAgents(story: Story): StoryAgent[] {
  const flag = story.ticks.findIndex((t) => t.patientZero);
  return story.ticks.slice(0, flag > 0 ? flag : 1).flatMap((t) => t.agents);
}

/** Every agent at every tick of the run. */
export function everyAgent(story: Story): StoryAgent[] {
  return story.ticks.flatMap((t) => t.agents);
}

/**
 * A projection from map coordinates (0..1) into `box` that shows all of `pts`, with the same scale on both
 * axes (so distances are not stretched) and y flipped (up on the map is up on screen). `minSpan` stops a very
 * tight group from being blown up to fill the box: a resting group 0.12 wide still only fills `minSpan`.
 */
export function fitFrame(pts: { x: number; y: number }[], box: Box, minSpan = 0.2): Project {
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const y0 = Math.min(...ys);
  const y1 = Math.max(...ys);
  const spanX = Math.max(x1 - x0, minSpan);
  const spanY = Math.max(y1 - y0, minSpan);
  const scale = Math.min((box.right - box.left) / spanX, (box.bottom - box.top) / spanY);
  const midX = (x0 + x1) / 2;
  const midY = (y0 + y1) / 2;
  const cx = (box.left + box.right) / 2;
  const cy = (box.top + box.bottom) / 2;
  return (x, y) => [cx + (x - midX) * scale, cy - (y - midY) * scale];
}

/**
 * A dashed ring around the resting group: centred on it, wide enough to hold every resting position, and
 * kept inside `within` when given (a wide resting group must not push the ring over the plate's edge or caption).
 */
export function restingEllipse(story: Story, project: Project, minRadius = 60, pad = 1.45, within?: Box): Ellipse {
  const pts = restingAgents(story).map((a) => project(a.x, a.y));
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const rx = Math.max(minRadius, ((Math.max(...xs) - Math.min(...xs)) / 2) * pad + 22);
  const ry = Math.max(minRadius * 0.6, ((Math.max(...ys) - Math.min(...ys)) / 2) * pad + 22);
  if (!within) return { cx, cy, rx, ry };
  return {
    cx,
    cy,
    rx: Math.min(rx, cx - within.left, within.right - cx),
    ry: Math.min(ry, cy - within.top, within.bottom - cy),
  };
}
