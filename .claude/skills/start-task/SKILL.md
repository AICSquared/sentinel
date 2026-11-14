---
name: start-task
description: Use when starting work on a GitHub issue as a strike-team builder. Covers reading the issue, the worktree, board posts, checks and opening the PR.
---

# Start a task

1. **Read the issue** (`gh issue view <N>`). Note the files it owns and the checklist item it checks off. If it lists no owned files, post `BLOCKED` on your channel and stop.
2. **Read only what you need:** the issue, `docs/plans/<track>.md`, the track's `CHECKLIST.md`, and the files you own. Don't explore the rest of the repo.
3. **Worktree and branch:**
   ```bash
   git fetch origin
   git worktree add ../hack-<name>-<N> -b <N>-<slug> origin/main
   cd ../hack-<name>-<N> && pnpm install && cp ../<main-clone>/.board.env .
   ```
4. **Post** `ACK` on your channel: what you'll build, about how long.
5. **Build against `_data/sample.ts`** first, so it works in demo mode. Add live data last, behind `demoMode`.
6. **Before each commit:** `git status` (only your files), `pnpm check`. Commit small, then post `STATUS`. While waiting on someone, post `STATUS` every 15 min saying what you're waiting on.
7. **Before the PR:** `git fetch && git rebase origin/main`, `pnpm build`.
8. **Open the PR:** title `<track>: <what>`, body with `Closes #<N>`, a 3-line summary of what changed, and the component name and props for the integrator.
   ```bash
   gh pr create --title "<track>: <what>" --body "Closes #<N> ..."
   ```
9. **Post `DONE`** with the PR link. Tell your human: "PR ready for you to read and merge. Start a fresh session for the next task." Don't merge it yourself.
