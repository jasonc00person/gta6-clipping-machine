---
name: submit-clips
description: Submits posted clips to the clipping campaign (Content Rewards or Clipping.net) within its 30-minute window, and, when the user asks, posts the clips to TikTok, Instagram Reels and YouTube Shorts in their browser first. Logs every post and submission. Use for "submit my clips", "submit these links", "post my clips", "post and submit", or step 4 of /gta.
---

# Post and submit clips

Campaigns pay only for submitted links, and most want them **within 30 minutes of posting**.

## 0. Who posts

- **Default:** the user posts from their own phone or browser and gives you the links. Skip to step 5.
- **The user asks you to post:** first show them, in chat, the exact list: each clip × platform,
  the caption, the YouTube title, and whether to turn on the platform's paid-partnership /
  branded-content label (campaign clips are paid promotion; platform rules say to disclose it,
  most clippers don't; it's their call). Post only after a clear yes. One yes covers the list they saw.

## 1. Use the right browser profile

Load the Claude in Chrome tools in one ToolSearch call (add `file_upload`, `form_input`, `find`).
The posting accounts must be the ones signed in on that Chrome: `list_connected_browsers`, then
check which account each site shows (TikTok profile, Instagram profile, YouTube Studio channel).
If the user's personal accounts are signed in there, stop: posting would go to the wrong account.
A separate Chrome profile for the clipping page, with Claude in Chrome connected, is the clean
setup. Signing in is always the user's job.

## 2. Make upload copies

The browser upload tool takes **at most 10 MB per file**; finished clips are often 15 to 30 MB.

```bash
uv run scripts/upload_copies.py work/<campaign>
```

Writes `clips/<name>/<name>.upload.mp4` (about 9 MB, HEVC, 30 fps). The platforms re-compress
every upload, so it looks the same once posted. Re-run it after rebuilding a clip.

## 3. Order: beat the window

1. **TikTok first, for every clip.** TikTok keeps new posts private ("Content under review") for a
   few minutes, and Content Rewards can't read a post until it's public.
2. Then Instagram, then YouTube.
3. Submit in batches as posts go public. Each post's 30 minutes starts when it was posted.

## 4. Posting, per platform

**TikTok** (`tiktok.com/tiktokstudio/upload`)
- `find` the hidden file input, then `file_upload` the `.upload.mp4`. Wait ~6 s for the editor:
  clicking the description too early makes select-all grab the whole page.
- The description starts as the filename: click into it, select all, delete, type the caption.
  Type hashtags one at a time, each followed by a space, so TikTok turns them into tags.
- If TikTok asks to "turn on automatic content checks", that's an account setting: Cancel unless
  the user wants it.
- Check the settings: "Who can see" = Everyone; "AI-generated content" off for real footage;
  "Disclose post content" per the user's choice. Then Post.
- The link is on `tiktok.com/tiktokstudio/content` (`/@handle/video/<id>`).

**Instagram** (`instagram.com` → Create → Post)
- Use the file input **inside the "Create new post" dialog**: the profile page has other file
  inputs (one sets the profile picture).
- Video posts become Reels: OK the notice.
- **The crop defaults to square.** Click the crop icon (bottom left) → **Original**, and check the
  preview shows the whole 9:16 frame before Next.
- Next → Next → type the caption. **Don't press Escape** (it opens "Discard post?"). AI label off
  for real footage. Share, and wait for "Your reel has been shared".
- The link is on `instagram.com/<handle>/reels/`, newest first (`/reel/<code>/`).

**YouTube Shorts** (`studio.youtube.com` → Upload videos)
- Check the channel name and ID in Studio are the page's, not the user's personal channel.
- Title = the YouTube title from `post.md`; Description = the caption with hashtags. A "Suggested
  hashtags" panel can shift the layout after typing the title: re-`find` the description box.
- "No, it's not made for kids" (required). "Altered content" stays No for real footage.
- Next three times → Public → Publish. The link is `youtube.com/shorts/<id>`.
- Read the Checks step: copyright claims on in-game music are common. "This claim doesn't affect
  your video's visibility" is fine (only ad revenue goes to the claimant). If it would block the
  video, stop and tell the user.

## 5. Submit on Content Rewards

1. Campaign page → **Submit clip**. Recent posts from linked accounts show up as cards with
   "N min left". Select cards, or paste a link.
2. Before ticking "I've read the requirements", check each post against `post.md`'s checklist
   (hashtag in the caption, right account, the campaign's rules). Flag anything that misses.
3. "We couldn't read that from the platform… may be private": the post is still in review, or
   just went public. Wait a few minutes and retry. If a pasted link keeps failing but the post
   shows as a card, clear the link field and select the card instead.
4. Several cards can go in one submit, but the dialog regroups by account after the first click.
   Compare the confirmation ("2 clips submitted") with what you meant to submit, and check
   `contentrewards.com/c/submissions` (Pending count) at the end.
5. Pop-ups such as "Join Reach's Discord" are optional account links: Not now / Skip for now,
   unless the user wants them.

If the user is submitting links they posted themselves, show them the list and get a yes before
the final submit click.

## 6. Log and report

Append each post to `work/<campaign>/submissions.json`:
`{"clip": "<name>", "platform": "tiktok", "url": "<post link>", "posted_at": "<ISO>", "submitted_at": "<ISO>"}`.
Report a table (clip × platform with links), anything skipped or flagged (claims, failed
submits), and close the tabs you opened.

Payouts: Content Rewards pays in rounds (about 7 days of earning + 3 days hold) to the Whop
wallet, and only once Whop is connected on the Content Rewards account; most campaigns also
need a minimum view count per clip and an approval. Clipping.net pays to PayPal or crypto after
each cycle. Withdrawing is always the user's job.
