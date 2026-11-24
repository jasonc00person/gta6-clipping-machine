# /// script
# requires-python = ">=3.10"
# ///
"""Rank scouted campaigns for a new clipping page.

Usage:
    uv run scripts/rank_campaigns.py work/scout/<date>.json [--top 10] [--include-pools]

The scout file is written by the /find-campaigns skill (Claude reads the campaign pages in
your browser and records the numbers). This script does the math so the ranking is the same
every time:

    score = rate x room x floor x freshness x fit

  rate       $ per 1K views (the top rate when a range is shown)
  room       log of budget still unpaid per clipper already in. Crowded = low.
  floor      views a clip needs before it pays anything. A new account can hit 2K, rarely 100K.
  freshness  new campaigns have budget left and few clippers.
  fit        game/streamer footage you can actually clip. Sound/music, logo-only,
             gambling, and AI-only campaigns are dropped or marked down.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import die, load, save  # noqa: E402

GAMBLING = ("casino", "bet", "stake", "roobet", "metawin", "1win", "vavada", "shuffle", "gamdom", "luxdrop", "csgo")
SOUND = ("sound campaign", "audio campaign", "music campaign", "song", "remix", "| audio")


def floor_views(c: dict) -> float | None:
    if c.get("min_views"):
        return float(c["min_views"])
    rate = c.get("rate_per_1k") or 0
    if c.get("min_payout_usd") and rate:
        return float(c["min_payout_usd"]) / rate * 1000
    return None


def floor_factor(v: float | None) -> float:
    if v is None:
        return 0.8
    if v <= 2_500:
        return 1.0
    if v <= 10_000:
        return 0.85
    if v <= 50_000:
        return 0.5
    if v <= 100_000:
        return 0.3
    return 0.12


def score(c: dict, include_pools: bool) -> tuple[float, list[str], str | None]:
    """Returns (score, reasons, skip_reason)."""
    title = (c.get("title", "") + " " + c.get("agency", "") + " " + c.get("notes", "")).lower()
    flags = {f.lower() for f in c.get("flags", [])}
    reasons: list[str] = []

    if "gambling" in flags or any(g in title for g in GAMBLING):
        return 0, reasons, "gambling sponsor (account-ban risk)"
    if c.get("type") == "pool" and not include_pools:
        return 0, reasons, "pool: you split a fixed pot with every clipper"
    if "ai_only" in flags:
        return 0, reasons, "wants AI-generated video, not clips"

    rate = float(c.get("rate_max_per_1k") or c.get("rate_per_1k") or 0)
    if rate <= 0:
        return 0, reasons, "no per-view rate"

    budget = float(c.get("budget") or 0)
    paid = float(c.get("paid") or 0)
    left = max(0.0, budget - paid) if budget else None
    clippers = int(c.get("clippers") or 0)
    if left is not None and left < 150:
        return 0, reasons, f"only ${left:,.0f} left"

    if left is not None:
        per_clipper = left / (clippers + 1)
        room = math.log10(1 + per_clipper) / 3  # $1K per clipper ~ 1.0
        reasons.append(f"${left:,.0f} left, {clippers} clipper{'s' if clippers != 1 else ''} (${per_clipper:,.0f} each)")
    else:
        room = 0.6
        reasons.append("budget not shown")

    fv = floor_views(c)
    ff = floor_factor(fv)
    if fv is not None:
        reasons.append(f"pays from ~{fv:,.0f} views")

    age = c.get("launched_days_ago")
    fresh = 1.0
    if age is not None:
        fresh = 1.15 if age <= 3 else 1.0 if age <= 14 else 0.85
        if age <= 3:
            reasons.append("launched in the last 3 days")

    fit = 1.0
    if "sound" in flags or any(s in title for s in SOUND):
        fit *= 0.45
        reasons.append("sound/music campaign: clip must use their track")
    if "logo" in flags or "logo campaign" in title:
        fit *= 0.6
        reasons.append("logo campaign: must overlay their logo")
    if "ai_ban" in flags:
        fit *= 0.9
        reasons.append("bans AI content: keep edits simple, no AI visuals")
    if "gta" in title or "gta" in flags:
        fit *= 1.1
    if c.get("max_payout_usd") and float(c["max_payout_usd"]) < 50:
        fit *= 0.7
        reasons.append(f"cap only ${c['max_payout_usd']} per clip")

    reasons.insert(0, f"${rate:.2f}/1K")
    return rate * room * ff * fresh * fit, reasons, None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scout")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--include-pools", action="store_true")
    a = p.parse_args()

    data = load(Path(a.scout))
    if not data or not data.get("campaigns"):
        die(f"no campaigns in {a.scout}")

    ranked, skipped = [], []
    for c in data["campaigns"]:
        s, reasons, skip = score(c, a.include_pools)
        if skip:
            skipped.append((c, skip))
        else:
            ranked.append({**c, "score": round(s, 3), "why": reasons})
    ranked.sort(key=lambda c: c["score"], reverse=True)

    out = Path(a.scout).with_name(Path(a.scout).stem + ".ranked.json")
    save(out, {"ranked": ranked, "skipped": [{"title": c.get("title"), "why": w} for c, w in skipped]})

    print(f"{len(ranked)} campaigns ranked, {len(skipped)} skipped -> {out}\n")
    for i, c in enumerate(ranked[: a.top], 1):
        print(f"{i:>2}. [{c['score']:.2f}] {c.get('title')}  ({c.get('platform')}, {c.get('agency', '?')})")
        print(f"      {' · '.join(c['why'])}")
        print(f"      {c.get('url', '')}")
    if skipped:
        print("\nSkipped:")
        for c, why in skipped[:15]:
            print(f"   - {c.get('title')}: {why}")


if __name__ == "__main__":
    main()
