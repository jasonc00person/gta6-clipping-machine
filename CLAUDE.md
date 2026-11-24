# GTA 6 Clipping Machine

A Claude Code project that runs a clipping page: it finds paying clipping campaigns, cuts the
campaign's footage into short vertical clips, and submits the links after the user posts them.

Start with `/gta`. The steps are also separate skills: `/setup`, `/find-campaigns`, `/make-clips`,
`/submit-clips` (in `.claude/skills/`).

## Layout

- `scripts/`: Python, each run with `uv run scripts/<name>.py` (dependencies install themselves).
  `--help` on any script explains it.
  - `doctor.py`: setup check. `rank_campaigns.py`: scores scouted campaigns.
  - `fetch.py`: footage in. `find_moments.py`: loudness spikes + transcripts. `peek.py`: frames to look at.
  - `make_clips.py`: plan.json to finished clips. `render.py`, `media.py`, `asr.py`, `common.py`: helpers.
- `work/`: everything per user and per campaign (gitignored).
  - `work/scout/<date>.json`: scouted campaigns, `.ranked.json` next to it.
  - `work/<campaign>/`: `campaign.json`, `sources.json`, `audio/`, `video/`, `moments/`, `sheets/`,
    `plan.json`, `clips/<name>/{<name>.mp4, preview.jpg, cover.jpg, post.md}`, `submissions.json`.

## Rules

- The user posts to social media. Never upload or post for them.
- Joining a campaign and submitting links are the user's decisions: confirm in chat first.
- Never sign in, create accounts, or type passwords for the user. If a page needs a login, ask them.
- Follow each campaign's rules (required hashtags, who must be on screen, no logos, etc.).
  They go into `campaign.json` and every clip's `post.md` checklist.
- Look at every clip's `preview.jpg` before calling it done.
- Long jobs (downloads, transcription, renders) go in the background with a one-line heads-up.

## Gotchas

- Times in `plan.json` and `moments/*.json` are source times (seconds or `h:mm:ss.s`).
- Hook text can't contain emoji (the caption font has none). Emoji go in the post caption.
- Long streams are never downloaded whole: `find_moments.py` uses the audio, and the
  video for each clip is fetched on demand (`media.local_span`).
- On-screen text is drawn with Pillow and overlaid, so any ffmpeg build works.
