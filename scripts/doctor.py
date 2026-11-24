# /// script
# requires-python = ">=3.10"
# ///
"""Check that this computer can run the clipping machine, and say how to fix what's missing.

Usage:
    uv run scripts/doctor.py
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, find_font  # noqa: E402

OS = {"darwin": "mac", "win32": "windows"}.get(sys.platform, "linux")
FIX = {
    "ffmpeg": {"mac": "brew install ffmpeg",
               "windows": "winget install --id Gyan.FFmpeg -e   (then close and reopen the terminal)",
               "linux": "sudo apt install ffmpeg"},
    "brew": {"mac": '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'},
}

ok = True


def check(label: str, good: bool, fix: str = ""):
    global ok
    print(f"  {'✓' if good else '✗'} {label}")
    if not good:
        ok = False
        if fix:
            print(f"      fix: {fix}")


def main():
    print(f"Clipping machine setup check ({platform.system()} {platform.machine()}, Python {platform.python_version()})\n")

    if OS == "mac":
        check("Homebrew", bool(shutil.which("brew")), FIX["brew"]["mac"])

    has_ffmpeg = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))
    check("ffmpeg + ffprobe", has_ffmpeg, FIX["ffmpeg"][OS])
    if has_ffmpeg:
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        check("ffmpeg has libx264 (H.264 encoder)", "libx264" in enc,
              "install a full ffmpeg build: " + FIX["ffmpeg"][OS])

    check("uv", bool(shutil.which("uv")),
          "mac/linux: curl -LsSf https://astral.sh/uv/install.sh | sh    windows: winget install --id astral-sh.uv -e")

    try:
        font = find_font()
        check(f"caption font ({Path(font).name})", True)
    except SystemExit:
        check("caption font", False, "set CLIP_FONT to any bold .ttf file")

    free = shutil.disk_usage(ROOT).free / 1e9
    check(f"free disk space: {free:.0f} GB", free > 10, "free up space: stream footage is big (keep 10 GB+)")

    if OS == "mac" and platform.machine() == "arm64":
        print("  ✓ Apple Silicon: transcription runs on the GPU (mlx-whisper)")
    else:
        print("  • transcription uses faster-whisper (NVIDIA GPU if you have one, otherwise CPU; slower but works)")

    print("\nAlso needed (can't be checked from here):")
    print("  • Claude Code, signed in")
    print("  • Claude in Chrome extension, connected (for finding campaigns and reading briefs)")
    print("  • A Content Rewards account (contentrewards.com) and/or a Clipping account (clipping.net)")
    print("  • TikTok / YouTube / Instagram accounts to post from")
    print("\n" + ("All good. Run /gta in Claude Code." if ok else "Fix the ✗ items above, then run this again."))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
