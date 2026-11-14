# Team rules (HackNCAT)

Every agent reads this file at the start of every session. Part A is how we work; Part B is how the app is built. Step-by-step procedures live in `.claude/skills/<name>/SKILL.md`: Claude loads them as skills, and Codex and Gemini read the file when they do that job.

# Part A: how we work

## 1. The plan
- **One repo, one app, a folder per track.** Every track is a route (`/lenovo`) in `src/app/<track>/`. Branches are only for single tasks.
- **Tracks go one at a time.** All Claude agents form the **strike team** on the active track until it meets its done bar (its `CHECKLIST.md`). Alex posts the active track on #1 as a `DECISION`.
- **Scouts prepare the next track** so the strike team never starts from a blank page:
  - **Gemini** researches: reads the brief and rubric, posts a `FINDING`, drafts the checklist, and reviews PRs (`REVIEW`).
  - **Codex** scaffolds: plan, sample data and a working page skeleton (skill `scout-track`).
  - **Alex's RPi5** (a bot) flags agents silent for 15+ min and posts summaries. It can't answer, so never `REQ` it; if it flags you, post `STATUS`.
- **Humans stay in charge.** Humans create and assign issues and merge every PR after reading it. Agents propose; they never merge.

## 2. Your identity
Your human tells you your **tag** (`[Alex's Claude]`), **role** (strike, scout or support) and **channel**. Tags are exact, capitals included: `[Stephen's Claude]`, not `[Stephen's claude]`.

## 3. The board
Channels are GitHub issues: #1 lead, #2 rtx, #3 cisco, #4 amat, #5 sandia, #6 lenovo, #7 medtronic. Your channel is in `.board.env`.

Every post is `[<Name>'s <Agent>] LABEL text`, under 10 lines. Link files and PRs instead of pasting them.

| Label | Use it for |
|---|---|
| `ACK` | You saw a request or mention; say what you'll do |
| `STATUS` | After every commit or push, and every 15 min while working or waiting (`waiting on #9`) |
| `DONE` | A request is finished; link the PR |
| `BLOCKED` | You can't go on: why, and who you need (`@login`) |
| `REQ` | Asking a person or agent for something, and by when |
| `REVIEW` | A verdict on a PR, then numbered issues with file:line |
| `FINDING` | A research result with its source link |
| `OFFLINE` | Before you stop or hit a usage limit: what's done, what's left |
| `DECISION` | Humans only |
| `DIGEST` | Summaries (the RPi5) |

Every `REQ` or mention gets an `ACK`, then one `DONE` or `BLOCKED`.

Commands: `tools/board post "..."` (your channel), `--to 1` (lead), `tools/board unread`, `tools/board wait`, `tools/board read -n 20 --from 6`.
- Claude Code: hooks show unread posts on every prompt. Keep one background `tools/board wait` running.
- Codex and Gemini: run `tools/board unread` before every task and every commit.

## 4. Who owns what
- Inside a track, your issue lists the files you own, normally `src/app/<track>/_components/<feature>.tsx` and `_lib/<feature>.ts`. Edit only those. Need something else changed? `REQ` its owner.
- **Alex's Claude is the integrator:** it owns each track's `page.tsx` and wires the parts together.
- **Alex owns shared code:** `src/components/`, `src/lib/`, `supabase/`, `.claude/`, `tools/`.
- Ask your human before anything irreversible: merging, deleting, force-pushing, spending money, submitting.

## 5. Git
1. Your own worktree per task: `git worktree add ../hack-<name>-<issue#> -b <issue#>-<slug> origin/main`
2. Stage only your own files, never `git add -A`. Run `git status` before every commit.
3. `pnpm check` before every commit, `pnpm build` before a PR.
4. PR title starts with the track (`lenovo: battery table`); body says `Closes #N` and lists what changed. Your human merges.
5. `git fetch && git rebase origin/main` before pushing. Never force-push.

## 6. Saving tokens
- **A fresh session for every task.** Context lives in files, not chats: the issue, `docs/plans/<track>.md`, the track's `CHECKLIST.md` and the board. When your PR is up, post `DONE` and tell your human to start a new session.
- **Read only what your task needs.** The issue lists the files; don't explore the whole repo.
- **Research is Gemini's job.** Builders don't read sponsor docs end to end; ask for a `FINDING`.
- **Model choice:** Sonnet for routine edits and board posts; Opus for design, hard bugs and integration.

## 7. Demos
- Every track page must work in **demo mode** (`src/lib/demo.ts`): it renders from `src/app/<track>/_data/` with no network and no sign-in.
- Present with `pnpm demo` (a production build on the laptop). The presenter bar switches tracks: `[` and `]` for previous and next, `h` for home.
- Before a track is done, run the `demo-check` skill. To submit, use `submit-track`.

## 8. Lessons from JSNN
- Agree on the data shape first, build against sample data, swap in the real source last.
- A `DONE` links proof: a PR or a screenshot.
- Any number we show judges gets checked a second, independent way.
- Read the sponsor's docs and data before guessing. Don't trust "latest" or device clocks without checking.
- Thresholds use the median, not the mean.

# Part B: the stack

Next.js 16 (App Router, TypeScript, pnpm, Tailwind), **Supabase** for auth and data when a track needs it, **Vercel** for a live link. Add Python only if a brief needs data analysis or machine learning, in `src/app/<track>/_py/` or a script the human runs.

## 9. Commands
`pnpm dev` (http://localhost:3000), `pnpm check` (lint and types), `pnpm build`, `pnpm demo` (build, then serve like production)

## 10. Where things go
| What | Where |
|---|---|
| A track | `src/app/<track>/`: `page.tsx`, `_components/`, `_lib/`, `_data/sample.ts`, `README.md`, `CHECKLIST.md` |
| Shared UI | `src/components/ui/index.tsx` (Page, PageHeader, Card, Button, ButtonLink, Tag, Field, SetupNotice, DemoBadge), `src/components/kpi.tsx` |
| Track list | `src/lib/tracks.ts` (set `ready: true` when a track is done) |
| Demo mode | `src/lib/demo.ts` |
| Supabase clients | `src/lib/supabase/` (`client.ts`, `server.ts`, `admin.ts`) |
| Database | `supabase/migrations/` (one new file per change, never edit an old one) |
| Worked example | `src/app/example/` (sign-in, a Server Action saves to Supabase, work runs in `after()`, the page revalidates) |

## 11. Next.js 16 (newer than most training data)
- Request-time code goes in `src/proxy.ts`, not `middleware.ts`.
- `cookies()`, `headers()`, `params` and `searchParams` are async: `await` them.
- Mutations are Server Actions in `actions.ts` with `"use server"`, ending in `revalidatePath(...)`.
- Background work under a minute: `after()` from `next/server`. Longer: a separate script.
- Cache Components is off. Pages that read the user or live data add `export const dynamic = "force-dynamic"`.
- Unsure about an API? Read `node_modules/next/dist/docs/` first.

## 12. Supabase
- `"use client"` components: `createClient()` from `@/lib/supabase/client`.
- Server Components, Server Actions, Route Handlers: `await createClient()` and `getUser()` from `@/lib/supabase/server`.
- `@/lib/supabase/admin` uses the secret key and skips Row Level Security. Server only, never in browser code.
- Every table has Row Level Security on, with policies on `auth.uid() = user_id`. Prefix track tables with the track (`lenovo_devices`). Copy the template at the bottom of the first migration. A new table is a new migration plus a `REQ` to Alex.
- In demo mode, read `_data/` instead of Supabase. Without keys, pages must still render.

## 13. Look and feel
- Use the tokens in `src/app/globals.css` (`bg-surface`, `text-ink-2`, `bg-accent`). No new colors without asking Alex.
- Headlines say what's happening in plain words, with real units. No gradients, emoji, glassy cards or "unlock insights" filler.
- Animate only the 3 to 5 headline numbers, with `<Kpi>`.
- Every control is a real `<button>`, `<a>` or labeled input, at least 44px tall.

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Worktree convention
- If your Claude Code session has worktree mode ON, it already made your worktree. Do NOT also run `git worktree add` from the start-task skill — just create branch `<issue#>-<slug>` here and work.
- Each worktree is a fresh folder. Before building, run:
  `printf 'BOARD_LEAD=1\nBOARD_ISSUE=2\nBOARD_WATCH=1,2\n' > .board.env` then `pnpm install` (and your pip installs).
