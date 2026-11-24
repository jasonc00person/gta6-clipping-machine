# GTA 6 Clipping Machine

Run a GTA 6 clipping page with Claude Code. It does the boring parts for you:

1. **Finds the campaigns that pay.** Opens your browser on [Content Rewards](https://contentrewards.com) and
   [Clipping](https://clipping.net), reads every live campaign, and ranks them. Crowded mega-streamer pools rank low.
   Niche streamers with budget left, a good rate and few clippers rank high.
2. **Grabs the footage.** Most campaigns hand you the raw footage (a Twitch/YouTube/Kick VOD or a Drive
   folder). It downloads it for you. Even a 7-hour stream takes under a minute, because it only pulls the audio first.
3. **Finds the clippable moments.** It listens to the whole stream for the spots where the streamer
   blows up (chases, crashes, deaths, wild NPCs), transcribes them, and picks the ones that work as a
   standalone clip.
4. **Cuts basic shorts.** 9:16, facecam on top and gameplay underneath (or full-frame), with one
   Gen Z hook line in TikTok's own text style (TikTok Sans, white boxes, emoji) right on the seam.
   Word-by-word speech captions are there if you want them. Ready for TikTok, Shorts and Reels.
5. **Gives you a posting sheet** for every clip (caption, hashtags, the campaign's rules),
   **posts the clips** to TikTok, Reels and Shorts in your browser if you ask, and **submits the
   links** to the campaign inside its 30-minute window.

Posting is your call: post the clips yourself and hand Claude the links, or ask it to post them in
your browser after you approve every caption. Use a separate Chrome profile for your clipping
accounts so nothing ever lands on your personal ones.

## What you need

- [Claude Code](https://claude.com/claude-code) (a Claude Pro or Max plan)
- The Claude in Chrome extension (Chrome Web Store), connected to Claude Code (for steps 1 and 5)
- A free [Content Rewards](https://contentrewards.com) and/or [Clipping](https://clipping.net) account
- TikTok / YouTube / Instagram accounts to post from
- A Mac or Windows PC with ~10 GB free disk space

## Install

**1. Get the tools**

Mac (Terminal):
```bash
brew install ffmpeg uv
```

Windows (PowerShell), then close and reopen PowerShell:
```powershell
winget install --id Gyan.FFmpeg -e
winget install --id astral-sh.uv -e
```

**2. Get this repo**

```bash
git clone https://github.com/jasonc00person/gta6-clipping-machine.git
cd gta6-clipping-machine
```

(Or click **Code → Download ZIP** on GitHub and unzip it.)

**3. Open it in Claude Code** and type:

```
/gta
```

The first run checks your setup and tells you how to fix anything missing.

## Commands

| Command | What it does |
|---|---|
| `/gta` | The whole machine, start to finish |
| `/find-campaigns` | Browse both platforms, rank campaigns, recommend one |
| `/make-clips` | Footage → moments → finished clips + posting sheets |
| `/submit-clips` | Post your clips (only if you ask) and submit the links to the campaign |
| `/setup` | Check and install what's needed |

You can also just talk to it: *"make 5 clips from AsianJeff's latest stream"*, *"redo the second
clip with the full frame instead of the facecam"*, *"find me campaigns that pay over $1.50"*.

## How it picks campaigns

Every campaign gets a score:

```
score = rate per 1K views
      × room       (budget left ÷ clippers already in: crowded campaigns score low)
      × floor      (views a clip needs before it pays anything: 2K is easy, 100K is not)
      × freshness  (new campaigns still have budget and few clippers)
      × fit        (sound-only, logo-only, gambling and AI-only campaigns are skipped or marked down)
```

The formula is in [`scripts/rank_campaigns.py`](scripts/rank_campaigns.py) if you want to tune it.

## How it finds moments

It lets the stream's own audience vote. Three signals, strongest first:

1. **Viewer clips** (Twitch): clips the streamer's viewers already made from that VOD, ranked by
   views. People only clip what made them laugh or gasp.
2. **Chat floods** (Twitch): the moments chat suddenly explodes with "NOOO", "LMAOOO", "💀".
3. **Loudness**: when the stream suddenly gets much louder than the minutes around it. Weakest,
   because gunfire and cutscenes are loud too, but it works on any footage.

Each candidate gets transcribed with the chat messages from that moment mixed in. Claude reads
them, skips scripted mission cutscenes and dead air, looks at frames from the best ones, and
writes a plan: which seconds to cut (jump cuts included), the hook text, the caption. Then it builds
the clips and checks every one before handing them over.

## The money, honestly

- Campaigns pay roughly **$0.50 to $2 per 1,000 views**. At $1.13 per 1K, $10K a month is about
  9 million views a month.
- Most campaigns only pay once a clip passes a floor (often 1K to 10K views) and cap what one clip
  can earn (often $250 to $1,000).
- Content Rewards takes a 10% fee and pays out in rounds about every 10 days.
- Most clips get a few hundred views. A few take off. Volume and consistency matter more than any
  single clip. Nothing here guarantees income.

## Don't get banned

- **Never buy views or use bots.** Every platform checks for it and bans you from every campaign.
- **Follow each campaign's rules**: required hashtags, who must be on screen, audience country,
  no logos. They're copied into every clip's `post.md` checklist.
- **Submit within the window** (usually 30 minutes after posting).
- Some agencies ban "AI-generated content". These clips are real footage with basic edits, but if a
  campaign is strict, ask the campaign's support first.
- Don't post the same clip on several accounts on the same platform, and space out your posts.

## Troubleshooting

- **"ffmpeg not found"**: install it (above), then open a new terminal.
- **Chrome steps don't work**: make sure the Claude in Chrome extension is installed and connected.
- **First transcription is slow**: it's downloading a speech model (0.5 to 1.6 GB) the first time.
  On Windows without an NVIDIA GPU, transcription runs on the CPU and takes longer.
- **A stream is still live**: wait for the VOD.
- **Captions misspell a name**: tell Claude the right spelling and ask it to rebuild the clip.

Everything you make lives in `work/` (ignored by git).

## License

MIT. TikTok Sans (in `assets/fonts`) is © TikTok Inc. under the SIL Open Font License. Not affiliated with Rockstar Games, Content Rewards, Whop or Clipping. Make sure you have the
right to clip any footage you use. Campaign footage comes with that permission.
