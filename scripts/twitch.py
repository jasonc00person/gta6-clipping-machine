"""What Twitch viewers think was good: viewer-made clips and chat activity for a VOD.

Uses Twitch's public web API (the same one the site uses, no login). Two signals:
  clips  clips viewers made from the VOD, with view counts and where they start in it.
         People only clip what made them laugh or gasp, so these are the strongest signal.
  chat   every chat message with its time in the VOD. Chat floods ("LMAOOO", "KEKW", "💀")
         a few seconds after something happens.

Twitch only serves the first page of results to scripts, so clips are: the VOD's first 100
plus the channel's top 100 of the week and month by views, filtered to this VOD.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

GQL = "https://gql.twitch.tv/gql"
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # Twitch's public web client id
BOTS = {"nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "soundalerts", "sery_bot",
        "wizebot", "botrixoficial", "kofistreambot", "streamstickers", "blerp", "pokemoncommunitygame"}
HYPE = re.compile(
    r"(lmao|lmfao|lol|kek|lul|omegalul|icant|haha|hahah|😂|🤣|💀|😭|☠|w+ ?jeff|clip (it|that)|"
    r"no way|bro what|wtf|holy|pog|\?\?\?)", re.I)


def vod_id(url: str | None) -> str | None:
    m = re.search(r"twitch\.tv/videos/(\d+)", url or "")
    return m.group(1) if m else None


def _gql(query: str, tries: int = 3) -> dict:
    body = json.dumps({"query": query}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(GQL, data=body, headers={"Client-ID": CLIENT_ID,
                                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))
    return {}


def _clip(n: dict) -> dict:
    return {"title": n.get("title") or "", "views": int(n.get("viewCount") or 0),
            "start": float(n.get("videoOffsetSeconds") or 0), "dur": float(n.get("durationSeconds") or 30),
            "url": f"https://clips.twitch.tv/{n['slug']}"}


def viewer_clips(vid: str) -> list[dict]:
    fields = "slug title viewCount durationSeconds videoOffsetSeconds video { id }"
    r = _gql('query { video(id: "%s") { owner { login } clips(first: 100) { edges { node { %s } } } } }'
             % (vid, fields))
    video = (r.get("data") or {}).get("video") or {}
    found = {}
    for e in ((video.get("clips") or {}).get("edges") or []):
        found[e["node"]["slug"]] = _clip(e["node"])
    login = (video.get("owner") or {}).get("login")
    for period in ("LAST_WEEK", "LAST_MONTH", "ALL_TIME"):
        if not login:
            break
        r = _gql('query { user(login: "%s") { clips(first: 100, criteria: {period: %s, sort: VIEWS_DESC}) '
                 '{ edges { node { %s } } } } }' % (login, period, fields))
        for e in ((((r.get("data") or {}).get("user") or {}).get("clips") or {}).get("edges") or []):
            n = e["node"]
            if (n.get("video") or {}).get("id") == vid and n.get("videoOffsetSeconds") is not None:
                found[n["slug"]] = _clip(n)
    return sorted(found.values(), key=lambda c: -c["views"])


def _chat_range(vid: str, a: float, b: float) -> list[dict]:
    out, seen, t = [], set(), a
    while t < b:
        r = _gql('query { video(id: "%s") { comments(contentOffsetSeconds: %d) { edges { node { id '
                 'contentOffsetSeconds commenter { login } message { fragments { text } } } } } } }'
                 % (vid, int(t)))
        edges = ((((r.get("data") or {}).get("video") or {}).get("comments") or {}).get("edges")) or []
        if not edges:
            break
        last = t
        for e in edges:
            n = e["node"]
            last = max(last, n["contentOffsetSeconds"])
            # pages start a little before the asked-for second, so drop what belongs to the previous range
            if n["id"] in seen or not a <= n["contentOffsetSeconds"] < b:
                continue
            seen.add(n["id"])
            text = "".join(f.get("text") or "" for f in (n.get("message") or {}).get("fragments") or []).strip()
            who = ((n.get("commenter") or {}).get("login") or "").lower()
            if not text or text.startswith("!") or who in BOTS or "http" in text:
                continue  # commands, bots, ads and links say nothing about the moment
            out.append({"t": n["contentOffsetSeconds"], "m": text})
        t = last if last > t else t + 1  # jump to the last message seen; +1 s if a second overflows a page
    return out


def chat(vid: str, length: float, workers: int = 8) -> list[dict]:
    """All chat messages of the VOD as [{"t": seconds, "m": text}], fetched in parallel ranges."""
    step = max(600.0, length / (workers * 4))
    ranges = [(s, min(length, s + step)) for s in range(0, int(length) + 1, int(step))]
    with ThreadPoolExecutor(workers) as ex:
        parts = list(ex.map(lambda r: _chat_range(vid, *r), ranges))
    msgs = [m for p in parts for m in p]
    msgs.sort(key=lambda m: m["t"])
    return msgs


def is_hype(text: str) -> bool:
    return bool(HYPE.search(text)) or (len(text) >= 4 and text.isupper() and any(c.isalpha() for c in text))
