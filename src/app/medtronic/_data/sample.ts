// Bundled sample data for demo mode (see src/lib/demo.ts). The scout replaces this with data
// for the real brief: real units, believable values, and the edge cases the demo has to show.
export type Row = { label: string; value: string; note?: string };

export const sample = {
  headline: "Waiting for the Medtronic brief.",
  rows: [] as Row[],
};
