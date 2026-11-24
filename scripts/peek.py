# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["pillow", "yt-dlp"]
# ///
"""See what happens in a span of footage without watching it.

Usage:
    uv run scripts/peek.py work/<campaign> <source> <start> <end> [--n 6]
    uv run scripts/peek.py --video path/to/clip.mp4 [--n 6]

Writes two images to sheets/ and prints their paths:
  <name>.jpg       a contact sheet: n frames across the span, each stamped with its source time
  <name>_grid.jpg  one full frame with a 10% grid, for reading off the facecam box for "split"
                   ([x, y, w, h] as fractions: x=0.72 means 72% of the way across)

For a long stream this downloads just that span (it is reused later when the clip is built).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import find_font, fmt_time, need, parse_time, probe, run, workdir  # noqa: E402
from media import local_span  # noqa: E402


def grab(video: Path, t: float, out: Path, width: int | None = 480):
    vf = ["-vf", f"scale={width}:-2"] if width else []
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", video, "-frames:v", "1", *vf,
         "-q:v", "3", out])


def contact_sheet(video: Path, times: list[float], labels: list[str], out: Path, cols: int = 3):
    need("ffmpeg")
    font = ImageFont.truetype(find_font(), 26)
    with tempfile.TemporaryDirectory() as td:
        frames = []
        for i, t in enumerate(times):
            f = Path(td) / f"{i}.jpg"
            grab(video, t, f)
            if f.exists():
                frames.append(Image.open(f).convert("RGB"))
        if not frames:
            return None
        fw, fh = frames[0].size
        rows = (len(frames) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * fw, rows * fh), "black")
        d = ImageDraw.Draw(sheet)
        for i, (fr, label) in enumerate(zip(frames, labels)):
            x, y = (i % cols) * fw, (i // cols) * fh
            sheet.paste(fr.resize((fw, fh)), (x, y))
            d.rectangle((x, y, x + d.textlength(label, font=font) + 16, y + 36), fill="black")
            d.text((x + 8, y + 4), label, font=font, fill="yellow")
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out, quality=85)
    return out


def grid_frame(video: Path, t: float, out: Path):
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "f.jpg"
        grab(video, t, f, width=1280)
        img = Image.open(f).convert("RGB")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(find_font(), 20)
    w, h = img.size
    for i in range(1, 10):
        x, y = w * i / 10, h * i / 10
        d.line((x, 0, x, h), fill=(255, 255, 0), width=1)
        d.line((0, y, w, y), fill=(255, 255, 0), width=1)
        d.text((x + 3, 3), f".{i}", font=font, fill=(255, 255, 0), stroke_width=2, stroke_fill="black")
        d.text((3, y + 3), f".{i}", font=font, fill=(255, 255, 0), stroke_width=2, stroke_fill="black")
    img.save(out, quality=88)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("work", nargs="?")
    p.add_argument("source", nargs="?")
    p.add_argument("start", nargs="?")
    p.add_argument("end", nargs="?")
    p.add_argument("--video", help="peek at any video file instead (e.g. a finished clip)")
    p.add_argument("--n", type=int, default=6)
    a = p.parse_args()

    if a.video:
        video = Path(a.video).resolve()
        dur = probe(video)["duration"]
        times = [dur * (i + 0.5) / a.n for i in range(a.n)]
        out = video.with_name(video.stem + "_sheet.jpg")
        print(contact_sheet(video, times, [fmt_time(t) for t in times], out))
        return

    if not (a.work and a.source and a.start and a.end):
        p.error("need: work source start end (or --video)")
    work = workdir(a.work)
    s, e = parse_time(a.start), parse_time(a.end)
    video, offset = local_span(work, a.source, s, e)
    times = [s + (e - s) * (i + 0.5) / a.n for i in range(a.n)]
    name = f"{a.source}_{int(s)}-{int(e)}"
    sheet = contact_sheet(video, [t - offset for t in times], [fmt_time(t) for t in times],
                          work / "sheets" / f"{name}.jpg")
    grid = grid_frame(video, (s + e) / 2 - offset, work / "sheets" / f"{name}_grid.jpg")
    print(sheet)
    print(grid)


if __name__ == "__main__":
    main()
