---
name: gta
description: Runs the whole GTA 6 clipping machine. Finds the best-paying clipping campaigns, makes ready-to-post shorts from the campaign's footage, posts them if asked, and submits the links. Use when the user types /gta, "run the machine", "start clipping", or "make me money with clipping".
---

# The GTA 6 clipping machine

Run these in order. Each one is its own skill and can also be run alone.

1. **Setup** (first run only): `/setup`. Skip if `uv run scripts/doctor.py` already ends with "All good".
2. **Find campaigns**: `/find-campaigns`. Browse Content Rewards + Clipping.net, rank, and recommend.
   Stop and let the user pick and join one.
3. **Make clips**: `/make-clips` for the joined campaign. Brief, footage, moments, plan, build, check.
4. **Post + submit**: `/submit-clips`. The user posts each clip themselves (caption from `post.md`)
   and gives you the links, or asks you to post them in the browser after approving the captions.
   Either way the links go in within the campaign's window (usually 30 min).

Keep the user in the loop at the decision points (which campaign, which moments if they want a
say, final submit) and move fast everywhere else. Tell them in a line what's happening at each
step; long downloads and transcriptions take minutes. Run them in the background and say so.

At the end, recap: clips made (with paths), what's posted and submitted, and the next thing to do
(post the rest, check views tomorrow, run /make-clips again on the next stream).
