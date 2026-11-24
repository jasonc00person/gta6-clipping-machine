"""Footage sources: downloading, the per-campaign source list, and finding local video for a time span.

A campaign folder keeps every source in sources.json:

    {"sources": {"<id>": {"url": ..., "title": ..., "duration": 1234.5,
                          "video": "video/<id>.mp4" | null,       # full local video, if downloaded
                          "audio": "audio/<id>.m4a",               # what the moment finder listens to
                          "sections": [{"start": 3600.0, "end": 3700.0, "path": "video/..."}]}}}

Long streams are never downloaded whole: the finder scans the audio, and only the spans that
become clips (or get previewed) are downloaded as video.
"""
from __future__ import annotations

import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from common import die, load, probe, run, save, slug

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".ts"}
FULL_DOWNLOAD_MAX = 40 * 60  # videos up to 40 min are downloaded whole
FORMAT = "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"


# ---------- sources.json ----------

def sources(work: Path) -> dict:
    return load(work / "sources.json", {"sources": {}})


def save_sources(work: Path, data: dict):
    save(work / "sources.json", data)


def get_source(work: Path, sid: str) -> dict:
    data = sources(work)
    if sid not in data["sources"]:
        known = ", ".join(data["sources"]) or "none yet"
        die(f"unknown source '{sid}'. Known: {known}")
    return data["sources"][sid]


def new_id(work: Path, title: str) -> str:
    base = slug(title, 24)
    existing = sources(work)["sources"]
    sid, n = base, 2
    while sid in existing:
        sid, n = f"{base}-{n}", n + 1
    return sid


def abs_path(work: Path, rel: str | None) -> Path | None:
    if not rel:
        return None
    p = Path(rel)
    return p if p.is_absolute() else work / p


def rel_path(work: Path, p: Path) -> str:
    try:
        return Path(p).resolve().relative_to(work.resolve()).as_posix()
    except ValueError:
        return str(Path(p).resolve())


# ---------- yt-dlp ----------

def ytdlp(args: list, check: bool = True) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-progress", *map(str, args)]
    return run(cmd, check=check)


def ytdlp_download(url: str, out_template: str, extra: list) -> Path:
    r = ytdlp([*extra, "-N", "8", "-o", out_template, "--print", "after_move:filepath", url])
    lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
    if not lines:
        die(f"yt-dlp did not report a file for {url}")
    return Path(lines[-1].strip())


def download_section(work: Path, src: dict, sid: str, start: float, end: float) -> dict:
    """Download [start, end] of a remote source as a 1080p mp4 with exact cut points."""
    out_dir = work / "video"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{sid}__{int(start)}-{int(end + 0.999)}"
    print(f"  downloading {sid} {start:.1f}s-{end:.1f}s ...", flush=True)
    path = ytdlp_download(
        src["url"], str(out_dir / f"{name}.%(ext)s"),
        ["-f", FORMAT, "--merge-output-format", "mp4",
         "--download-sections", f"*{start:.2f}-{end:.2f}", "--force-keyframes-at-cuts"],
    )
    info = probe(path)
    return {"start": round(start, 3), "end": round(start + info["duration"], 3), "path": rel_path(work, path)}


def local_span(work: Path, sid: str, a: float, b: float, margin: float = 3.0) -> tuple[Path, float]:
    """Local video file covering source seconds [a, b], and the source time at which that file starts.

    file_time = source_time - offset
    """
    data = sources(work)
    src = data["sources"].get(sid) or die(f"unknown source '{sid}'")
    if src.get("video"):
        return abs_path(work, src["video"]), 0.0
    for sec in src.get("sections", []):
        if sec["start"] <= a + 0.01 and sec["end"] >= b - 0.01 and abs_path(work, sec["path"]).exists():
            return abs_path(work, sec["path"]), float(sec["start"])
    s = max(0.0, a - margin)
    e = min(float(src.get("duration") or b + margin), b + margin)
    sec = download_section(work, src, sid, s, e)
    data = sources(work)  # reload: another step may have written meanwhile
    data["sources"][sid].setdefault("sections", []).append(sec)
    save_sources(work, data)
    return abs_path(work, sec["path"]), float(sec["start"])


# ---------- plain downloads ----------

def http_download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (clipping-machine)"})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)
    return dest


def unzip_media(zpath: Path, dest: Path) -> list[Path]:
    out = []
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            if name.endswith("/") or ".." in Path(name).parts:
                continue
            target = dest / Path(name).name
            with z.open(name) as src, open(target, "wb") as f:
                f.write(src.read())
            out.append(target)
    return out
