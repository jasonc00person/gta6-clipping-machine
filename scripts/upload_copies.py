# /// script
# requires-python = ">=3.10"
# ///
"""Make small copies of finished clips for uploading through the browser.

Usage:
    uv run scripts/upload_copies.py work/<campaign> [--only NAME] [--max-mb 9.2]

Claude in Chrome's file upload takes at most 10 MB per file, and a 30-60 s 1080p clip is often
15-30 MB. This writes clips/<name>/<name>.upload.mp4 next to each clip: HEVC (H.265) at 30 fps,
two-pass to land just under the size limit. TikTok, Instagram and YouTube re-compress every upload
anyway, so the copy looks the same once posted. Falls back to H.264 if this ffmpeg has no libx265.
Clips already under the limit are copied as-is.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import die, need, probe, run, workdir  # noqa: E402


def has_encoder(name: str) -> bool:
    return name in run(["ffmpeg", "-hide_banner", "-encoders"], check=False).stdout


def shrink(src: Path, dst: Path, max_mb: float):
    info = probe(src)
    if src.stat().st_size <= max_mb * 1e6:
        shutil.copyfile(src, dst)
        return "copied (already small enough)"
    dur = info["duration"] or 1
    vkbps = max(400, int(max_mb * 1e6 * 8 / dur / 1000 - 128))
    hevc = has_encoder("libx265")

    with tempfile.TemporaryDirectory() as td:
        log = str(Path(td) / "pass")

        def codec(n: int) -> list:
            if hevc:  # x265 ignores -passlogfile; its stats file must be named or it lands in the cwd
                stats = Path(td, "x265.stats").as_posix().replace(":", "\\:")
                return ["-c:v", "libx265", "-x265-params", f"pass={n}:stats={stats}:log-level=error",
                        "-tag:v", "hvc1"]
            return ["-c:v", "libx264", "-pass", str(n)]

        common = ["-b:v", f"{vkbps}k", "-r", "30", "-pix_fmt", "yuv420p", "-preset", "medium", "-passlogfile", log]
        run(["ffmpeg", "-y", "-v", "error", "-i", src, *codec(1), *common, "-an", "-f", "null", "-"])
        run(["ffmpeg", "-y", "-v", "error", "-i", src, *codec(2), *common, "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", dst])
    return f"{'HEVC' if hevc else 'H.264'} {vkbps} kb/s"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("work")
    p.add_argument("--only", help="just this clip name")
    p.add_argument("--max-mb", type=float, default=9.2)
    a = p.parse_args()

    need("ffmpeg")
    work = workdir(a.work)
    clips = sorted((work / "clips").glob("*/")) if (work / "clips").exists() else []
    if a.only:
        clips = [c for c in clips if c.name == a.only]
    done = 0
    for d in clips:
        src = d / f"{d.name}.mp4"
        if not src.exists():
            continue
        dst = d / f"{d.name}.upload.mp4"
        how = shrink(src, dst, a.max_mb)
        size = dst.stat().st_size / 1e6
        flag = "" if size <= 10 else "  ⚠ still over 10 MB: lower --max-mb"
        print(f"  {d.name}: {size:.1f} MB, {how} -> {dst.relative_to(work)}{flag}")
        done += 1
    if not done:
        die("no finished clips found in clips/. Run make_clips.py first.")


if __name__ == "__main__":
    main()
