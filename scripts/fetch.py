# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["yt-dlp", "gdown"]
# ///
"""Add campaign footage to a campaign folder.

Usage:
    uv run scripts/fetch.py work/<campaign> <url-or-file> [--id NAME] [--full]
    uv run scripts/fetch.py work/<campaign> <channel-or-playlist-url> --list

Handles YouTube, Twitch and Kick VODs (anything yt-dlp supports), Google Drive files and
folders, Dropbox links, direct video links, and files already on your computer.

Videos up to 40 minutes are downloaded whole. Longer streams only get their audio downloaded:
find_moments.py scans that audio, and the video for each clip is fetched later, just the
seconds you need. --full forces a whole download.

--list prints the latest videos on a channel or playlist so you can pick a VOD.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import WORK, die, fmt_time, need, probe  # noqa: E402
from media import (  # noqa: E402
    FORMAT, FULL_DOWNLOAD_MAX, VIDEO_EXT, http_download, new_id, rel_path,
    save_sources, sources, unzip_media, ytdlp, ytdlp_download,
)


def register(work: Path, sid: str, entry: dict):
    data = sources(work)
    data["sources"][sid] = entry
    save_sources(work, data)
    dur = entry.get("duration") or 0
    mode = "full video" if entry.get("video") else "audio only (video fetched per clip)"
    print(f"added source '{sid}': {entry.get('title', '')} [{fmt_time(dur)}] {mode}")


def add_local_file(work: Path, path: Path, sid: str | None, url: str | None = None):
    info = probe(path)
    if not info.get("width"):
        print(f"  skipping {path.name}: no video stream")
        return
    sid = sid or new_id(work, path.stem)
    register(work, sid, {
        "url": url, "title": path.stem, "duration": round(info["duration"], 3),
        "width": info["width"], "height": info["height"], "fps": round(info.get("fps", 30), 3),
        "video": rel_path(work, path), "audio": rel_path(work, path), "sections": [],
    })


def keep_files(work: Path, files: list[Path], sid: str | None):
    """Videos become sources; anything else (logos, briefs) goes to refs/."""
    refs = work / "refs"
    for f in files:
        if f.suffix.lower() in VIDEO_EXT:
            add_local_file(work, f, sid if len(files) == 1 else None)
        else:
            refs.mkdir(exist_ok=True)
            dest = refs / f.name
            if f.resolve() != dest.resolve():
                shutil.move(str(f), dest)
            print(f"  saved reference file: {rel_path(work, dest)}")


def fetch_drive(work: Path, url: str, sid: str | None):
    import gdown

    dest = work / "video"
    dest.mkdir(parents=True, exist_ok=True)
    if "/folders/" in url:
        paths = gdown.download_folder(url, output=str(dest), quiet=False, remaining_ok=True) or []
        files = [Path(p) for p in paths]
    else:
        p = gdown.download(url, output=str(dest) + "/", quiet=False, fuzzy=True)
        files = [Path(p)] if p else []
    if not files:
        die("Google Drive download failed. Is the link shared as 'Anyone with the link'?")
    keep_files(work, files, sid)


def fetch_http(work: Path, url: str, sid: str | None):
    if "dropbox.com" in url:
        url = re.sub(r"([?&])dl=0", r"\1dl=1", url)
        if "dl=1" not in url:
            url += ("&" if "?" in url else "?") + "dl=1"
    name = Path(url.split("?")[0]).name or "download"
    dest = http_download(url, work / "video" / name)
    if dest.suffix.lower() == ".zip" or (dest.read_bytes()[:2] == b"PK" and dest.suffix.lower() not in VIDEO_EXT):
        files = unzip_media(dest, work / "video")
        dest.unlink()
        keep_files(work, files, sid)
    else:
        keep_files(work, [dest], sid)


def list_channel(url: str):
    r = ytdlp(["--flat-playlist", "--playlist-end", "15", "-J", url])
    import json

    data = json.loads(r.stdout)
    entries = data.get("entries") or []
    if not entries:
        die("nothing listed. Is this a channel/videos page or a playlist?")
    print(f"{data.get('title', url)}: latest {len(entries)}")
    for e in entries:
        dur = fmt_time(e["duration"]) if e.get("duration") else "?"
        when = e.get("upload_date") or (str(e.get("timestamp")) if e.get("timestamp") else "")
        print(f"  [{dur:>8}] {when:>10}  {e.get('title', '')[:70]}")
        print(f"             {e.get('url') or e.get('webpage_url') or e.get('id')}")


def fetch_ytdlp(work: Path, url: str, sid: str | None, full: bool):
    import json

    r = ytdlp(["-J", "--no-playlist", url])
    info = json.loads(r.stdout)
    if info.get("_type") == "playlist":
        die("that link is a channel or playlist. Run again with --list and pick one video.")
    if info.get("is_live") or info.get("live_status") == "is_live":
        die("that stream is still live. Use the VOD once it ends (or a past broadcast).")
    title = info.get("title") or info.get("id") or "video"
    dur = float(info.get("duration") or 0)
    sid = sid or new_id(work, title)
    entry = {
        "url": info.get("webpage_url") or url, "title": title, "duration": dur,
        "width": info.get("width"), "height": info.get("height"), "fps": info.get("fps"),
        "uploader": info.get("uploader") or info.get("channel"),
        "video": None, "audio": None, "sections": [],
    }
    if full or (dur and dur <= FULL_DOWNLOAD_MAX):
        print(f"downloading video ({fmt_time(dur)}) ...", flush=True)
        path = ytdlp_download(url, str(work / "video" / f"{sid}.%(ext)s"),
                              ["--no-playlist", "-f", FORMAT, "--merge-output-format", "mp4"])
        pi = probe(path)
        entry.update(video=rel_path(work, path), audio=rel_path(work, path), duration=round(pi["duration"], 3),
                     width=pi["width"], height=pi["height"], fps=round(pi.get("fps", 30), 3))
    else:
        print(f"long video ({fmt_time(dur)}): downloading audio only ...", flush=True)
        path = ytdlp_download(url, str(work / "audio" / f"{sid}.%(ext)s"),
                              ["--no-playlist", "-f", "ba/ba*/worst"])
        entry["audio"] = rel_path(work, path)
    register(work, sid, entry)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("work")
    p.add_argument("source")
    p.add_argument("--id")
    p.add_argument("--full", action="store_true", help="download the whole video even if it is long")
    p.add_argument("--list", action="store_true", help="list a channel's or playlist's latest videos")
    a = p.parse_args()

    need("ffmpeg")
    if a.list:
        list_channel(a.source)
        return

    work = Path(a.work)
    if not work.is_absolute() and not str(a.work).startswith("work"):
        work = WORK / a.work
    work = work.resolve()
    work.mkdir(parents=True, exist_ok=True)

    src = a.source.strip()
    local = Path(src).expanduser()
    if local.exists():
        if local.is_dir():
            keep_files(work, sorted(f for f in local.iterdir() if f.suffix.lower() in VIDEO_EXT), None)
        else:
            add_local_file(work, local.resolve(), a.id)
    elif "drive.google.com" in src:
        fetch_drive(work, src, a.id)
    elif "dropbox.com" in src or Path(src.split("?")[0]).suffix.lower() in VIDEO_EXT | {".zip"}:
        fetch_http(work, src, a.id)
    else:
        fetch_ytdlp(work, src, a.id, a.full)


if __name__ == "__main__":
    main()
