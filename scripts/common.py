"""Shared helpers for the clipping machine scripts. Standard library only."""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"

# Windows consoles default to a legacy code page when output is piped; titles and ✓ marks need UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def need(tool: str):
    if not shutil.which(tool):
        die(f"{tool} not found. Run: uv run scripts/doctor.py")


def run(cmd: list, quiet: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    cmd = [str(c) for c in cmd]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        tail = "\n".join((r.stderr or r.stdout or "").strip().splitlines()[-12:])
        die(f"command failed: {' '.join(cmd[:4])} ...\n{tail}")
    if not quiet and r.stdout.strip():
        pass
    return r


def load(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def slug(text: str, n: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n].strip("-") or "clip"


def parse_time(t) -> float:
    """'1:02:03.5', '62:03', '3723.5' or a number -> seconds."""
    if isinstance(t, (int, float)):
        return float(t)
    parts = str(t).strip().split(":")
    secs = 0.0
    for p in parts:
        secs = secs * 60 + float(p)
    return secs


def fmt_time(s: float) -> str:
    s = max(0.0, float(s))
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def probe(path: Path) -> dict:
    need("ffprobe")
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    data = json.loads(r.stdout)
    info = {"duration": float(data.get("format", {}).get("duration") or 0), "has_audio": False}
    for st in data.get("streams", []):
        if st.get("codec_type") == "video" and "width" not in info:
            info["width"], info["height"] = int(st["width"]), int(st["height"])
            num, _, den = (st.get("avg_frame_rate") or st.get("r_frame_rate") or "30/1").partition("/")
            try:
                info["fps"] = float(num) / float(den or 1)
            except (ValueError, ZeroDivisionError):
                info["fps"] = 30.0
        if st.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


def find_font() -> str:
    """A heavy sans font that exists on the machine. Arial Black ships with macOS and Windows."""
    env = os.environ.get("CLIP_FONT")
    candidates = [env] if env else []
    candidates += [
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/Library/Fonts/Arial Black.ttf",
        "C:/Windows/Fonts/ariblk.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial_Black.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    die("no bold font found. Set CLIP_FONT=/path/to/font.ttf")


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def workdir(arg: str) -> Path:
    """Accept 'work/<slug>' or just '<slug>'."""
    p = Path(arg)
    if not p.is_absolute() and not p.exists() and (WORK / arg).exists():
        p = WORK / arg
    if not p.exists():
        die(f"campaign folder not found: {arg} (expected work/<campaign-slug>)")
    return p.resolve()
