# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "numpy",
#   "mlx-whisper>=0.4.2; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "faster-whisper>=1.1.0; sys_platform != 'darwin' or platform_machine != 'arm64'",
# ]
# ///
"""Find the clippable moments in a source.

Usage:
    uv run scripts/find_moments.py work/<campaign> [--source ID] [--top 25] [--range 1:00:00 3:00:00]

How it works:
  1. Listens to the whole audio and measures loudness every half second.
  2. Compares each moment to the 3 minutes around it. Streamers get loud when something happens
     (a crash, a chase, a scream, a laugh), so the biggest jumps over the local baseline are the
     candidate moments.
  3. Transcribes a window around each spike (the setup before it and the reaction after).
     Short videos (20 min or less) are transcribed whole instead.

Writes moments/<source>.json (data) and moments/<source>.md (the digest Claude reads to pick clips).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asr import transcribe  # noqa: E402
from common import die, fmt_time, need, parse_time, save, workdir  # noqa: E402
from media import abs_path, sources  # noqa: E402

HOP = 0.5          # seconds per loudness sample
SR = 8000
SHORT = 20 * 60    # transcribe whole sources up to this long


def loudness(audio: Path, start: float | None, end: float | None) -> np.ndarray:
    """dBFS per HOP seconds for audio[start:end]."""
    need("ffmpeg")
    cmd = ["ffmpeg", "-v", "error"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(audio)]
    if end is not None:
        cmd += ["-t", str(end - (start or 0))]
    cmd += ["-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    hop = int(SR * HOP)
    out, buf = [], b""
    chunk = hop * 4 * 600
    while True:
        data = proc.stdout.read(chunk)
        if not data:
            break
        buf += data
        n = len(buf) // (hop * 4)
        if n:
            x = np.frombuffer(buf[: n * hop * 4], dtype=np.float32).reshape(n, hop)
            out.append(np.sqrt(np.mean(x.astype(np.float64) ** 2, axis=1)))
            buf = buf[n * hop * 4:]
    proc.wait()
    if not out:
        die(f"could not read audio from {audio}")
    rms = np.concatenate(out)
    return 20 * np.log10(np.maximum(rms, 1e-5))


def rolling_median(x: np.ndarray, win: int) -> np.ndarray:
    pad = win // 2
    xp = np.pad(x, pad, mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(xp, win)[: len(x)]
    out = np.empty(len(x))
    for i in range(0, len(x), 4000):  # in blocks to keep memory flat on long streams
        out[i:i + 4000] = np.median(view[i:i + 4000], axis=1)
    return out


def peaks(db: np.ndarray, top: int, gap_s: float) -> list[tuple[int, float]]:
    smooth = np.convolve(db, np.ones(3) / 3, mode="same")
    excite = smooth - rolling_median(db, int(180 / HOP))
    # A spike right after a mostly silent minute is usually the streamer coming back from AFK,
    # not a moment: take off up to 15 dB for the share of the last minute that was silent.
    silent = np.concatenate([[0], np.cumsum(db < -50)])
    win = int(60 / HOP)
    idx = np.arange(len(db))
    excite -= 15 * (silent[idx] - silent[np.maximum(0, idx - win)]) / win
    excite[db < -50] = -99  # silence is never a moment
    gap = int(gap_s / HOP)
    found, e = [], excite.copy()
    for _ in range(top):
        i = int(np.argmax(e))
        if e[i] < 3:  # less than 3 dB over baseline: nothing left worth a look
            break
        found.append((i, float(e[i])))
        e[max(0, i - gap): i + gap] = -99
    return found


def lines(words: list[dict], marks: dict[float, str]) -> list[str]:
    """Group words into timestamped lines; insert marks (time -> label) where they fall."""
    out, cur, t0 = [], [], None
    pending = sorted(marks.items())

    def flush():
        nonlocal cur, t0
        if cur:
            out.append(f"[{fmt_time(t0)}] {' '.join(cur)}")
        cur, t0 = [], None

    prev_end = None
    for w in words:
        while pending and pending[0][0] <= w["s"]:
            flush()
            out.append(f"      {pending.pop(0)[1]}")
        if t0 is not None and (w["s"] - t0 > 10 or (prev_end and w["s"] - prev_end > 1.2)):
            flush()
        if t0 is None:
            t0 = w["s"]
        cur.append(w["w"])
        prev_end = w["e"]
        if w["w"].endswith((".", "?", "!")) and w["s"] - t0 > 3:
            flush()
    flush()
    for _, label in pending:
        out.append(f"      {label}")
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("work")
    p.add_argument("--source", help="source id (default: every source)")
    p.add_argument("--top", type=int, default=25, help="how many spikes to transcribe on long sources")
    p.add_argument("--before", type=float, default=40, help="seconds of setup kept before a spike")
    p.add_argument("--after", type=float, default=20, help="seconds kept after a spike")
    p.add_argument("--range", nargs=2, metavar=("START", "END"), help="only scan this part of a long stream")
    a = p.parse_args()

    work = workdir(a.work)
    srcs = sources(work)["sources"]
    if not srcs:
        die("no sources yet. Add footage with scripts/fetch.py first.")
    ids = [a.source] if a.source else list(srcs)

    for sid in ids:
        src = srcs.get(sid) or die(f"unknown source '{sid}'")
        audio = abs_path(work, src.get("audio"))
        if not audio or not audio.exists():
            die(f"source '{sid}' has no audio file. Re-run fetch.py.")
        r0 = parse_time(a.range[0]) if a.range else 0.0
        r1 = parse_time(a.range[1]) if a.range else None
        dur = float(src.get("duration") or 0)
        span = (r1 or dur) - r0

        print(f"[{sid}] scanning loudness over {fmt_time(span)} ...", flush=True)
        db = loudness(audio, r0 or None, r1)
        spikes = [(r0 + i * HOP, s) for i, s in peaks(db, a.top, gap_s=75)]

        if span <= SHORT:
            print(f"[{sid}] short source: transcribing all of it ...", flush=True)
            words = transcribe(audio, r0 or None, r1)
            windows = [{"n": 1, "start": r0, "end": r0 + span, "peak": None, "score": None, "words": words}]
        else:
            raw = sorted((max(r0, t - a.before), min(r0 + span, t + a.after), t, s) for t, s in spikes)
            merged = []
            for s0, s1, t, sc in raw:
                if merged and s0 <= merged[-1][1]:
                    m = merged[-1]
                    merged[-1] = (m[0], max(m[1], s1), m[2] if m[3] >= sc else t, max(m[3], sc))
                else:
                    merged.append((s0, s1, t, sc))
            windows = []
            for n, (s0, s1, t, sc) in enumerate(merged, 1):
                print(f"[{sid}] transcribing window {n}/{len(merged)} at {fmt_time(t)} ...", flush=True)
                windows.append({"n": n, "start": round(s0, 2), "end": round(s1, 2), "peak": round(t, 2),
                                "score": round(sc, 1), "words": transcribe(audio, s0, s1)})

        out_dir = work / "moments"
        save(out_dir / f"{sid}.json", {"source": sid, "spikes": [[round(t, 2), round(s, 1)] for t, s in spikes],
                                       "windows": windows})

        md = [f"# Moments in '{sid}': {src.get('title', '')}",
              f"Source length {fmt_time(dur)}. Times below are SOURCE times (use them in plan.json).",
              "⚡ marks a loudness spike: dB over the surrounding 3 minutes. Bigger = bigger reaction.", ""]
        if len(windows) == 1 and windows[0]["peak"] is None:
            marks = {t: f"⚡ spike +{s:.0f} dB" for t, s in spikes}
            md += ["## Full transcript", ""] + lines(windows[0]["words"], marks)
        else:
            ranked = sorted(windows, key=lambda w: -w["score"])
            md += ["Windows by spike size: " + ", ".join(f"W{w['n']} (+{w['score']:.0f})" for w in ranked), ""]
            for w in windows:
                md += [f"## W{w['n']} · spike at {fmt_time(w['peak'])} (+{w['score']:.0f} dB) · "
                       f"{fmt_time(w['start'])}-{fmt_time(w['end'])}", ""]
                body = lines(w["words"], {w["peak"]: f"⚡ SPIKE +{w['score']:.0f} dB"})
                md += (body or ["(no speech: game audio only. Peek at it before using.)"]) + [""]
        (out_dir / f"{sid}.md").write_text("\n".join(md), encoding="utf-8")
        print(f"[{sid}] {len(windows)} window(s) -> {out_dir / f'{sid}.md'}")


if __name__ == "__main__":
    main()
