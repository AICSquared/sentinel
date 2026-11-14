# HackNCAT team template

One Next.js app with a folder per sponsor track, demo mode for every track, and a message board that lets 4 people and their AI agents work as one team. Rules for people and agents: **`AGENTS.md`**.

## Before the event (Alex, once)
1. **Supabase:** create a project in the AICSquared Supabase org. In the SQL editor, run `supabase/migrations/*.sql`. Under Authentication > Providers > Email, turn off "Confirm email".
2. **Vercel:** in the team, install the **Supabase integration** from the Vercel Marketplace and connect it to that project. It fills in the environment variables for you.
   - Vercel's free Hobby plan can't deploy a **private repo owned by an organization**. Use Pro, make the repo public at submission, or present from a laptop with `pnpm demo` (the plan anyway).
3. **GitHub:** org Settings > Member privileges > Base permissions: **Write**, so every member can push branches.

## At kickoff (about 2 minutes)
```bash
gh repo create aicsquared/<event-repo> --template aicsquared/orchestration-test1 --private --clone
cd <event-repo>
pnpm install
tools/setup-event          # creates channels #1 to #7, pins #1, writes your .board.env
```
Then import the repo in Vercel (if deploying), point the Pi at it, and post the first active track on #1 as a `DECISION`.

## Everyone
```bash
gh repo clone aicsquared/<event-repo> && cd <event-repo>
pnpm install
printf 'BOARD_LEAD=1\nBOARD_ISSUE=6\nBOARD_WATCH=1,6\n' > .board.env   # use the active track's number
cp .env.example .env.local                                              # optional: Supabase keys from Alex
pnpm dev                                                                # http://localhost:3000
```
Windows: run everything in Git Bash.

## Each task
Start a **new** Claude Code session in a fresh worktree, then: "You are [<Name>'s Claude], strike team, channel #<N>. Take issue #<issue>. Use the start-task skill."

## Demo day
```bash
NEXT_PUBLIC_DEMO_MODE=1 pnpm demo    # production build, bundled data, no Wi-Fi needed
```
Use the presenter bar to switch tracks (`[` previous, `]` next, `h` home). Each track's README has its 3-minute script and backup video link.

## Layout
| Path | What |
|---|---|
| `src/app/<track>/` | One folder per sponsor track (page, parts, sample data, README, checklist) |
| `src/app/example/` | Worked example: sign-in, Server Action, Supabase with RLS, `after()` |
| `src/components/`, `src/lib/` | Shared UI, demo mode, track list, Supabase clients |
| `supabase/migrations/` | Database schema with Row Level Security |
| `.claude/skills/` | Procedures: start-task, scout-track, demo-check, submit-track |
| `tools/board` | Message board CLI (GitHub issues as channels) |
| `tools/setup-event` | One-time setup for a new event repo |

Fonts (Public Sans, IBM Plex Mono) are bundled under the SIL Open Font License, see `src/app/fonts/`.
