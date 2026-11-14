---
name: submit-track
description: Use when a track is done and needs its submission package (README, video, links). The human submits; agents only prepare.
---

# Prepare the submission for `<track>`

1. **Demo check passed** (skill `demo-check`) and `CHECKLIST.md` says `State: done`.
2. **README.md complete:** the brief, what we built (one paragraph a judge reads in 20 seconds), how to run it, the demo script, how we built it, and honest credit for what AI agents did.
3. **Video:** remind the human to record the demo script (under 3 minutes) and paste the link into README and `CHECKLIST.md`.
4. **Screenshots:** 2 or 3 key screens saved in `docs/evidence/<track>/`.
5. **Repo link:** the main repo is private. If the sponsor needs a public repo, the human copies this track into one:
   ```bash
   mkdir ../<track>-submission && cp -R src/app/<track> ../<track>-submission/
   ```
   plus anything it imports from `src/components` and `src/lib`. Or the human makes the main repo public at submission time.
6. **Post `DONE`** on #1 with the README link, and list what the human still has to do on the submission form. Never submit anything yourself.
