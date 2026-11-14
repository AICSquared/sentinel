---
name: scout-track
description: Use when preparing a queued track before the strike team arrives (Codex scaffolds, Gemini researches). Produces the plan, checklist, sample data and a working page skeleton.
---

# Scout a track

The goal: when the strike team switches to this track, they find a plan, a checklist, realistic sample data and a page that already renders.

## Gemini (research, no commits)
1. Read the brief, rubric and any provided data or docs for `<track>`.
2. Post one `FINDING` on the track's channel: the problem in one sentence, every judging criterion, the data or hardware provided, what must be submitted (video, repo, slides, form), and what a winning 3-minute demo shows.
3. Draft `scratch/alex/<track>-checklist.md` (must-haves vs nice-to-haves) and `scratch/alex/<track>-brief.md` (the brief, pasted). Post `DONE`.

## Codex (scaffold, one PR titled `<track>: scout`)
Branch `<N>-<track>-scout` from fresh `main`. Produce:
1. `docs/plans/<track>.md`: the problem, the demo story (3 minutes, beat by beat), the screens, the data shape, and 3 to 6 tasks. Each task lists the exact files it owns (`src/app/<track>/_components/<feature>.tsx`, `_lib/<feature>.ts`) and the checklist item it checks off. One task is the integrator's (wiring `page.tsx`).
2. `src/app/<track>/README.md`: the brief pasted in, and the demo script outline.
3. `src/app/<track>/CHECKLIST.md`: must-haves from the rubric. Set `State: scouted`.
4. `src/app/<track>/_data/sample.ts`: realistic sample data with real units and the edge cases the demo needs. Keep the exported `sample` shape the page reads, or update the page to match.
5. `src/app/<track>/page.tsx`: a skeleton that renders the sample data with the shared UI. No Supabase calls.
6. If the track needs a table: a draft migration in `supabase/migrations/`, RLS on. Post a `REQ` to Alex; don't run it.

Run `pnpm check && pnpm build`, open the PR, and post `DONE` on #1: "<track> scouted" with the link. A human merges it.
