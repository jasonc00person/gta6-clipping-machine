---
name: make-clips
description: Turns a joined clipping campaign into ready-to-post 9:16 shorts. Reads the brief, downloads the campaign footage (Twitch/YouTube/Kick VODs, Drive/Dropbox folders), finds the best moments, cuts them with captions and a hook, and writes a posting sheet per clip. Use for "make clips", "clip this campaign", "clip this VOD", or step 2 of /gta.
---

# Make clips for a campaign

Input: a campaign the user has joined (a campaign page URL, or one picked in /find-campaigns).
Output: `work/<campaign>/clips/<name>/<name>.mp4` + `post.md` for each clip.

Everything runs with `uv run scripts/<script>.py`. Each script's `--help` explains it.

## 1. Read the brief → campaign.json

Open the campaign page in Chrome (load Claude in Chrome tools in one ToolSearch call, new tab).
Joined campaigns show **Reference materials** (usually a Drive folder or footage links) and
sometimes a rules page (e.g. reachclipping.com/<name>): read those too. Write
`work/<campaign-slug>/campaign.json`:

```json
{
  "title": "$2,500 AsianJeff Clipping Campaign",
  "url": "https://contentrewards.com/c/campaigns/...",
  "rate_per_1k": 1.0,
  "min_payout_usd": 10,
  "max_payout_usd": 300,
  "platforms": ["tiktok", "instagram", "youtube", "x"],
  "footage": ["https://www.twitch.tv/asianjeff"],
  "footage_rules": "GTA 6 playthrough streams from Nov 19 on only",
  "hashtags": ["#AsianJeff"],
  "mentions": [],
  "rules": [
    "AsianJeff is the main focus and shown positively",
    "No logos of any kind",
    "Audience 50%+ US/CA/AU/UK/NZ"
  ],
  "logo": null,
  "submit_window_minutes": 30
}
```

`logo` is only for logo campaigns: `{"path": "refs/logo.png", "corner": "top-right", "width": 220}`.
`rules` become the checklist in every post.md, so copy them faithfully and keep them short.

## 2. Get the footage

```bash
uv run scripts/fetch.py work/<campaign> <url-or-file> [--id short-name]
uv run scripts/fetch.py work/<campaign> https://www.twitch.tv/<streamer>/videos --list
```

- A channel link: `--list` first, then fetch the newest VOD that fits `footage_rules`.
- Up to 40 min: downloads the whole video. Longer: audio only; video comes later, per clip.
- Drive/Dropbox folders: every video becomes a source; images (logos) land in `refs/`.
- Live streams can't be fetched until the VOD exists.

## 3. Find the moments

```bash
uv run scripts/find_moments.py work/<campaign> --source <id> [--top 25] [--range 2:00:00 5:00:00]
```

Then **read `work/<campaign>/moments/<id>.md`**. Long streams give one window per loudness
spike (the streamer's reaction) with the transcript of the 40 s before and 20 s after.
For marathon VODs over ~8 h, scan in `--range` chunks.

Pick 3 to 6 moments. A good GTA clip:
- has **one clear event** (chase, crash, death, glitch, wild NPC, heist going wrong, a big win)
  and the streamer's reaction to it;
- **stands alone**: no "like I said earlier", no inside jokes that need the stream;
- opens **within a second or two of the action**, never on setup chatter;
- ends right after the payoff (the reaction or the punchline), 15 to 45 s total;
- fits the brief (e.g. the streamer must be on screen and look good: no rage-bait framing).

Skip windows that are just music, menus, or chat reading.

## 4. Look before you cut

```bash
uv run scripts/peek.py work/<campaign> <source> <start> <end>
```

Read both images it prints. The contact sheet shows what's on screen across the span; skip a
moment if the gameplay doesn't show what the audio suggests. The `_grid.jpg` has 10% grid lines:
read the facecam box off it as `[x, y, w, h]` fractions of the frame (the facecam is usually the
same for the whole stream, so do this once per source).

Layouts:
- `split`: facecam top, gameplay bottom. **Default for streamer campaigns** (they want the streamer visible).
- `fit`: whole frame over a blurred background. For footage without a facecam, or when the action fills the frame.
- `crop`: a 9:16 slice centred on `x`. For close-up action with no important UI at the edges.

## 5. Write plan.json

`work/<campaign>/plan.json`. Times are SOURCE times from moments/<id>.json, which has every
word's start/end: start ~0.2 s before the first word you keep, end ~0.5 s after the last.

```json
{
  "defaults": {"layout": "split", "cam": [0.74, 0.04, 0.25, 0.31]},
  "clips": [
    {
      "name": "jeff-vs-the-cops",
      "source": "day3",
      "segments": [["1:02:03.4", "1:02:38.9"]],
      "hook": "he really thought he could outrun them",
      "caption": "he was SO confident 😭 #gta6 #gtavi",
      "title": "He Thought He Could Outrun The Cops (GTA 6)",
      "why": "chase into crash, huge reaction, no context needed"
    }
  ]
}
```

- `segments`: one span, or several for jump cuts (cut dead air out of the middle).
- `hook`: the on-screen top text. Short, lowercase-casual, curiosity or punchline. **No emoji** (the font can't draw them).
- `caption`: the post caption. Emoji are fine here. Campaign hashtags/mentions are appended automatically.
- Per-clip overrides: `layout`, `cam`, `zoom` (1.0 to 1.5, zooms the gameplay), `x` (crop),
  `game_x` / `game_y` (where the split's gameplay crop centres), `hook_secs` (hide the hook after N s).
- `name` is a unique kebab-case title.

## 6. Build and check

```bash
uv run scripts/make_clips.py work/<campaign>          # all clips
uv run scripts/make_clips.py work/<campaign> --only jeff-vs-the-cops
```

For every clip, **read `clips/<name>/preview.jpg`**: facecam framed (no half faces, no overlay
junk), the gameplay showing the action, captions and hook readable, nothing important under the
text. Read the transcript at the bottom of `post.md` for misheard names. Fix plan.json and rebuild
with `--only`. Don't hand over a clip you haven't looked at.

## 7. Hand over

List each clip: name, length, the hook, and the path to its `post.md`. Tell the user to:
1. post each clip themselves from the accounts linked to the campaign (TikTok, Shorts, Reels, X),
   with the caption from post.md, spacing posts out instead of dumping them all at once;
2. run `/submit-clips` right after posting: most campaigns require the link within 30 minutes.

Never post to social accounts for the user.
