---
name: submit-clips
description: Submits the links of clips the user has already posted to their clipping campaign (Content Rewards or Clipping.net) in the browser, and logs them. Use for "submit my clips", "submit these links", or step 3 of /gta.
---

# Submit posted clips

Campaigns pay only for submitted links, and most want them **within 30 minutes of posting**.

1. Ask for the post links if the user hasn't given them, and which clip each one is.
2. Check each link against the clip's `post.md`: right platform, required hashtags in the caption
   (open the post in Chrome and read it if unsure). Flag any rule it misses before submitting.
3. Open the campaign page (URL in `work/<campaign>/campaign.json`) in a new Chrome tab. The user
   must be signed in; if not, ask them to sign in themselves. Never type a password.
4. Find the submit flow on the page (e.g. a "Submit" / "Submit clip" button, or the dashboard on
   Clipping.net), and fill in the link. Read the page instead of guessing: these sites change.
5. **Before the final submit click**, show the user the exact links and campaign and get a yes in
   chat. One yes can cover the whole list they just saw.
6. After each submit, confirm it shows as submitted/pending on the page, then append to
   `work/<campaign>/submissions.json`:
   `{"clip": "<name>", "url": "<post link>", "platform": "tiktok", "submitted_at": "<ISO time>"}`.
7. Report what was submitted and anything that failed. Close the tabs you opened.

Payouts: Content Rewards pays in rounds (about 7 days of earning + 3 days hold) to the Whop
wallet; the user withdraws. Clipping.net pays to PayPal or crypto after each cycle. Withdrawing is
always the user's job.
