# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "numpy",
#   "pillow",
#   "yt-dlp",
#   "mlx-whisper>=0.4.2; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "faster-whisper>=1.1.0; sys_platform != 'darwin' or platform_machine != 'arm64'",
# ]
# ///
"""Build the clips in plan.json into ready-to-post 9:16 shorts.

Usage:
    uv run scripts/make_clips.py work/<campaign> [--only NAME] [--no-captions]

For each clip in work/<campaign>/plan.json:
  1. gets the footage for its segments (downloads just those seconds for long streams)
  2. joins the segments, transcribes the result for word-timed captions
  3. lays it out 9:16 (fit / split / crop), burns in captions + hook text (+ logo if the campaign
     needs one), evens out the loudness
  4. writes clips/<name>/<name>.mp4, preview.jpg (6 frames, to check the layout) and post.md
     (caption, hashtags and the campaign's rules, ready to paste)

plan.json:
{
  "defaults": {"layout": "split", "cam": [0.74, 0.05, 0.24, 0.30]},
  "clips": [
    {
      "name": "cops-vs-jeff",
      "source": "asianjeff-gta-6-day-3",
      "segments": [["1:02:03.5", "1:02:41"]],      # source times; several = jump cuts
      "hook": "he really thought he got away",      # on-screen text, no emoji
      "hook_secs": null,                            # null = whole clip
      "layout": "split", "cam": [...], "zoom": 1.0, "x": 0.5, "game_x": 0.5,
      "caption": "bro forgot cops exist #gta6",     # the post caption
      "title": "He Thought He Got Away (GTA 6)",    # YouTube Shorts title
      "why": "chase into crash, big reaction, stands alone"
    }
  ]
}
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asr import transcribe  # noqa: E402
from common import die, fmt_time, load, need, parse_time, probe, run, workdir  # noqa: E402
from media import local_span, sources  # noqa: E402
from peek import contact_sheet, grab  # noqa: E402
from render import Painter, chunks, layout, overlay_track, plain  # noqa: E402


def resolve(work: Path, clip: dict) -> list[dict]:
    """Each segment -> {file, start (file seconds), dur, has_audio, info}."""
    segs = clip.get("segments") or die(f"clip '{clip['name']}' has no segments")
    spans = []
    for seg in segs:
        a, b = parse_time(seg[0]), parse_time(seg[1])
        if b <= a:
            die(f"clip '{clip['name']}': segment end {seg[1]} is before its start {seg[0]}")
        spans.append((a, b))
    # fetch nearby segments (jump cuts) as one download instead of one each
    lo, hi = min(a for a, _ in spans), max(b for _, b in spans)
    if len(spans) > 1 and hi - lo <= 120:
        local_span(work, clip["source"], lo, hi)
    out = []
    for a, b in spans:
        f, off = local_span(work, clip["source"], a, b)
        out.append({"file": f, "start": a - off, "dur": b - a, "info": probe(f)})
    return out


def inputs_and_join(segs: list[dict], fps: int) -> tuple[list, str]:
    args, parts = [], []
    k = 0
    for i, s in enumerate(segs):
        args += ["-ss", f"{s['start']:.3f}", "-t", f"{s['dur']:.3f}", "-i", s["file"]]
        v = k
        k += 1
        if s["info"]["has_audio"]:
            a_ref = f"[{v}:a]"
        else:
            args += ["-f", "lavfi", "-t", f"{s['dur']:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            a_ref = f"[{k}:a]"
            k += 1
        parts.append(f"[{v}:v]settb=AVTB,setpts=PTS-STARTPTS,fps={fps},setsar=1[v{i}];"
                     f"{a_ref}asetpts=PTS-STARTPTS,aresample=48000,"
                     f"aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
    n = len(segs)
    join = ";".join(parts) + ";" + "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vin][ain]"
    return args, join


def build(work: Path, clip: dict, campaign: dict, captions: bool):
    name = clip["name"]
    out_dir = work / "clips" / name
    tmp = out_dir / "_tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    segs = resolve(work, clip)
    duration = sum(s["dur"] for s in segs)
    if duration > 90:
        print(f"  ⚠ {name} is {duration:.0f}s. Shorts over 60-90s get fewer views; consider trimming.")
    info = segs[0]["info"]
    sw, sh = info["width"], info["height"]
    fps = 60 if info.get("fps", 30) >= 50 else 30
    args, join = inputs_and_join(segs, fps)

    # pass 1: the clip's audio, for captions
    words = []
    if captions:
        wav = tmp / "audio.wav"
        run(["ffmpeg", "-y", "-v", "error", *args, "-filter_complex", join.replace("[vin]", "[vnull]") +
             ";[vnull]nullsink", "-map", "[ain]", "-ac", "1", "-ar", "16000", wav])
        words = transcribe(wav)
    caps = chunks(words) if captions else []

    # overlay: hook + captions + logo
    try:
        vf, spots = layout(clip, sw, sh)
    except ValueError as e:
        die(str(e))
    hook = plain(clip.get("hook") or "") or None
    painter = Painter(spots, campaign.get("logo"), work)
    track = overlay_track(tmp, painter, duration, caps, hook, clip.get("hook_secs"))

    # pass 2: the video
    final = out_dir / f"{name}.mp4"
    k_overlay = sum(1 for x in args if x == "-i")
    graph = (f"{join};{vf};[{k_overlay}:v]format=rgba[ov];"
             f"[vl][ov]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v];"
             f"[ain]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    run(["ffmpeg", "-y", "-v", "error", *args, "-f", "concat", "-safe", "0", "-i", track,
         "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-t", f"{duration:.3f}",
         "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-r", str(fps),
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final])

    # checks + extras
    got = probe(final)
    if abs(got["duration"] - duration) > 0.5 or not got["has_audio"]:
        die(f"{name}: output looks wrong (duration {got['duration']:.1f}s vs {duration:.1f}s, audio={got['has_audio']})")
    times = [duration * (i + 0.5) / 6 for i in range(6)]
    contact_sheet(final, times, [fmt_time(t) for t in times], out_dir / "preview.jpg")
    grab(final, min(1.0, duration / 2), out_dir / "cover.jpg", width=None)
    write_post(out_dir, clip, campaign, duration, words)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"  ✓ {final.relative_to(work)}  ({duration:.1f}s, {clip.get('layout', 'fit')})")


def write_post(out_dir: Path, clip: dict, campaign: dict, duration: float, words: list[dict]):
    tags = " ".join(campaign.get("hashtags", []))
    mentions = " ".join(campaign.get("mentions", []))
    caption = " ".join(x for x in [clip.get("caption", ""), tags, mentions] if x).strip()
    rules = campaign.get("rules", [])
    window = campaign.get("submit_window_minutes", 30)
    lines = [
        f"# {clip['name']}",
        "",
        f"- File: `{clip['name']}.mp4` ({duration:.0f}s)",
        f"- Campaign: {campaign.get('title', '?')} {campaign.get('url', '')}",
        f"- Pays: ${campaign.get('rate_per_1k', '?')}/1K views on {', '.join(campaign.get('platforms', [])) or '?'}",
        "",
        "## Caption (TikTok / Instagram / X)",
        "",
        caption or "(write one)",
        "",
        "## YouTube Shorts title",
        "",
        clip.get("title") or (clip.get("hook") or clip["name"]).strip()[:90],
        "",
        "## Before you post",
        "",
        *[f"- [ ] {r}" for r in rules],
        "- [ ] Posted from the account you linked to the campaign",
        f"- [ ] Submit the post link on the campaign page within {window} minutes of posting",
        "",
        "## What's said (for checking captions)",
        "",
        " ".join(w["w"] for w in words) or "(no speech detected)",
        "",
    ]
    (out_dir / "post.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("work")
    p.add_argument("--only", help="build just this clip name")
    p.add_argument("--no-captions", action="store_true")
    a = p.parse_args()

    need("ffmpeg")
    work = workdir(a.work)
    plan = load(work / "plan.json") or die(f"no plan.json in {work}")
    campaign = load(work / "campaign.json", {})
    defaults = plan.get("defaults", {})
    known = sources(work)["sources"]

    clips = [{**defaults, **c} for c in plan.get("clips", [])]
    if a.only:
        clips = [c for c in clips if c["name"] == a.only] or die(f"no clip named '{a.only}' in plan.json")
    names = [c["name"] for c in clips]
    if len(set(names)) != len(names):
        die("clip names in plan.json must be unique")
    for c in clips:
        if c.get("source") not in known:
            die(f"clip '{c['name']}': unknown source '{c.get('source')}'. Known: {', '.join(known)}")

    print(f"building {len(clips)} clip(s) ...")
    for c in clips:
        print(f"- {c['name']}")
        build(work, c, campaign, captions=not a.no_captions and c.get("captions", True))
    print(f"\ndone. Clips + post.md files are in {work / 'clips'}")


if __name__ == "__main__":
    main()
