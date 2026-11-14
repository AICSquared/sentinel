---
name: demo-check
description: Use before marking a track done or before presenting. Verifies the track works offline in demo mode, the numbers hold up, and the demo script is ready.
---

# Demo check for `<track>`

Report each item as pass or fail on the track's channel as a `STATUS` post, then fix or `REQ` the owner.

1. **Production build:** `NEXT_PUBLIC_DEMO_MODE=1 pnpm demo`, then open http://localhost:3000/<track>. It must load with no errors in the terminal or the browser console.
2. **Offline:** with Wi-Fi off, the page still loads and every demo step works.
3. **The script:** walk the 3-minute demo script in `README.md` step by step. Every click works, nothing needs typing a URL, and nothing needs signing in.
4. **Numbers:** each number on screen matches a second, independent calculation. Note how you checked.
5. **Look:** plain-language headline with real units; no placeholder text, lorem ipsum, emoji or "TODO"; controls at least 44px; readable on a projector (zoom the browser to 150%).
6. **Presenter bar:** `[` and `]` reach this track, and `h` returns home.
7. **Checklist:** every must-have in `CHECKLIST.md` is checked with proof in the repo.

When all pass, tell Alex the track is ready to be marked `ready: true` in `src/lib/tracks.ts` and `State: done`.
