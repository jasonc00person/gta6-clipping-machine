---
name: find-campaigns
description: Opens the user's browser on Content Rewards and Clipping.net, reads the live clipping campaigns, ranks them for a new clipping page (rate, budget left per clipper, payout floor, freshness), and recommends which to join. Use for "find campaigns", "what should I clip", "best paying campaigns", or the first step of /gta.
---

# Find the best campaigns

Goal: a short, ranked list of campaigns worth clipping **today**, with the reason for each.
The money is in niche streamers: decent rate, budget left, few clippers. Huge pools
(e.g. a 4,000-clipper pool on a mega-streamer) are crowded and pay a sliver each.

## 1. Open the browser

Load the Claude in Chrome tools in one ToolSearch call (tabs_context_mcp, tabs_create_mcp,
navigate, get_page_text, javascript_tool, computer, tabs_close_mcp). Get tab context, open a
new tab, work only in it, and close it at the end. If Chrome isn't connected, tell the user to
install/connect the Claude in Chrome extension, or ask them to paste campaign links instead.

The discover pages are public, so the user doesn't need to be signed in to scout.

## 2. Content Rewards

1. Go to `https://contentrewards.com/c/discover/gtavi` (the GTA 6 category). If the user asked
   for more than GTA, also read `https://contentrewards.com/c/discover/clipping`.
2. `get_page_text` gives every card: agency, title, paid / budget, rate per 1K.
3. Get each card's link:
   ```js
   [...document.querySelectorAll('a[href*="/c/campaigns/"]')].map(a => a.getAttribute('href').split('?')[0] + ' | ' + a.textContent.replace(/\s+/g,' ').trim().slice(0,80)).join('\n')
   ```
4. Skip obvious no-gos without opening them: pools ("pool" in the title or "$X pool" instead of a rate),
   gambling sponsors (casino, Stake, Roobet, 1WIN, VAVADA, LUXDROP and similar), campaigns with under $150 left.
5. Open the remaining campaigns (up to ~15, best rate and most budget left first) and read each page.
   It shows: the description (click "Show more" if cut off), per-platform rate, **Min payout** ($),
   **Max payout** ($), budget paid / total, clipper count (the number next to the category tag,
   e.g. "Streamer · 42"), "Launched N days ago", and where the footage comes from.

## 3. Clipping.net

Go to `https://clipping.net/c/discover` and read the "All campaigns" section. Rates show
**per 100K views** (divide by 100 for per 1K) and "To qualify" is the minimum views per clip,
often 50K to 1M, which a new page rarely hits. Pools say "in pools / Split by views". Record the
Gaming and Streamers & IRL campaigns, plus anything GTA related. Clipping.net doesn't show
clipper counts or budgets: leave those null.

## 4. Save and rank

Write `work/scout/<YYYY-MM-DD>.json` (today's date):

```json
{
  "scouted_at": "2026-11-23",
  "campaigns": [
    {
      "platform": "contentrewards",
      "title": "$5,000 Dylan Page GTA VI Marathon Campaign",
      "agency": "NewsDaddy",
      "url": "https://contentrewards.com/c/campaigns/39753a1a-...",
      "type": "per_view",
      "rate_per_1k": 1.2,
      "rate_max_per_1k": 1.2,
      "budget": 5000,
      "paid": 197,
      "clippers": 7,
      "min_payout_usd": 4,
      "min_views": null,
      "max_payout_usd": 250,
      "launched_days_ago": 5,
      "platforms": ["tiktok", "instagram", "youtube", "x"],
      "footage": "Dylan Page's 120-hour GTA 6 marathon, live on YouTube",
      "notes": "Clips must show Dylan and include #DylanPage",
      "flags": ["gta"]
    }
  ]
}
```

- `type`: `per_view`, `pool`, or `per_post`.
- `flags` (any that apply): `gta`, `logo` (must overlay their logo), `sound` (must use their song),
  `gambling`, `ai_ban` (bans AI content), `ai_only` (wants AI-generated video), `apply` (needs approval).
- Use `null` for anything the page doesn't show. Never guess numbers.

Then run:

```bash
uv run scripts/rank_campaigns.py work/scout/<date>.json
```

## 5. Recommend

Show the top 5 as a short table: campaign, $/1K, budget left, clippers, pays from (views), why.
Give one recommendation and say why in a sentence. Then flag anything that could get the user
banned or unpaid: high view floors on a brand-new account, "AI content" bans, audience-country
rules, required hashtags or logos.

**Joining is the user's call.** Joining accepts the campaign's terms, so open the campaign page
and let the user click **Join Campaign** themselves (they must be signed in). Only click it for
them if they say so in chat for that specific campaign. Once they've joined, continue with
`/make-clips` for that campaign.
