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

Three signals, strongest first:
  👥 viewer clips  (Twitch VODs) clips the stream's own viewers made, with view counts. People
                   only clip what made them laugh or gasp.
  💬 chat          (Twitch VODs) moments where chat suddenly floods, weighted toward
                   "LMAOOO / KEKW / 💀 / NO WAY" messages.
  ⚡ loudness      (any source) the streamer, or the game, suddenly getting much louder than the
                   3 minutes around it. Weakest signal: gunfire and cutscenes are loud too.

Each candidate gets a window (the setup before and the reaction after), transcribed with the chat
messages from that moment mixed in. Short videos (20 min or less) are transcribed whole.

Writes moments/<source>.json (data) and moments/<source>.md (the digest Claude reads to pick clips),
best-scoring windows first.
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import twitch  # noqa: E402
from asr import transcribe  # noqa: E402
from common import die, fmt_time, load, need, parse_time, save, workdir  # noqa: E402
from media import abs_path, sources  # noqa: E402

HOP = 0.5          # seconds per loudness sample
SR = 8000
SHORT = 20 * 60    # transcribe whole sources up to this long
MAX_WINDOW = 120   # never merge candidates into a window longer than this


# ---------- loudness ----------

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
    while True:
        data = proc.stdout.read(hop * 4 * 600)
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
    return 20 * np.log10(np.maximum(np.concatenate(out), 1e-5))


def rolling_median(x: np.ndarray, win: int) -> np.ndarray:
    pad = win // 2
    xp = np.pad(x, pad, mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(xp, win)[: len(x)]
    out = np.empty(len(x))
    for i in range(0, len(x), 4000):  # in blocks to keep memory flat on long streams
        out[i:i + 4000] = np.median(view[i:i + 4000], axis=1)
    return out


def pick_peaks(score: np.ndarray, top: int, gap: int, floor: float) -> list[tuple[int, float]]:
    found, e = [], score.copy()
    for _ in range(top):
        i = int(np.argmax(e))
        if e[i] < floor:
            break
        found.append((i, float(e[i])))
        e[max(0, i - gap): i + gap] = -1e9
    return found


def loud_spikes(db: np.ndarray, t0: float, top: int) -> list[tuple[float, float]]:
    smooth = np.convolve(db, np.ones(3) / 3, mode="same")
    excite = smooth - rolling_median(db, int(180 / HOP))
    # A spike right after a mostly silent minute is usually the streamer coming back from AFK,
    # not a moment: take off up to 15 dB for the share of the last minute that was silent.
    silent = np.concatenate([[0], np.cumsum(db < -50)])
    win = int(60 / HOP)
    idx = np.arange(len(db))
    excite -= 15 * (silent[idx] - silent[np.maximum(0, idx - win)]) / win
    excite[db < -50] = -99
    return [(t0 + i * HOP, s) for i, s in pick_peaks(excite, top, int(75 / HOP), 3)]


# ---------- chat ----------

def chat_spikes(msgs: list[dict], length: float, top: int) -> list[dict]:
    """Moments where chat floods. Works for small chats too (a few messages a minute)."""
    bin_s = 5
    n = int(length // bin_s) + 1
    w = np.zeros(n)
    for m in msgs:
        i = int(m["t"] // bin_s)
        if 0 <= i < n:
            w[i] += 2.0 if twitch.is_hype(m["m"]) else 1.0
    s30 = np.convolve(w, np.ones(6), mode="same")                 # weighted messages per 30 s
    base = np.maximum(rolling_median(s30, 120), 2.0)              # usual rate over 10 min
    ratio = s30 / base
    ratio[s30 < 6] = 0
    out = []
    for i, r in pick_peaks(ratio, top, int(90 / bin_s), 2.0):
        t = i * bin_s
        near = [m for m in msgs if t - 15 <= m["t"] <= t + 15]
        out.append({"t": float(t), "ratio": round(r, 1), "msgs": len(near),
                    "hype": sum(twitch.is_hype(m["m"]) for m in near)})
    return out


# ---------- candidates ----------

def candidates(clips, chats, louds, r0, r1) -> list[dict]:
    c = []
    for cl in clips:
        if r0 <= cl["start"] <= r1:
            c.append({"a": cl["start"] - 12, "b": cl["start"] + cl["dur"] + 8, "sig": [("clip", cl)]})
    for ch in chats:
        if r0 <= ch["t"] <= r1:
            # chat reacts 5-15 s after the moment, so most of the window sits before the flood
            c.append({"a": ch["t"] - 50, "b": ch["t"] + 12, "sig": [("chat", ch)]})
    for t, db in louds:
        c.append({"a": t - 40, "b": t + 20, "sig": [("loud", (t, db))]})

    c.sort(key=lambda x: x["a"])
    merged = []
    for x in c:
        x["a"], x["b"] = max(r0, x["a"]), min(r1, x["b"])
        m = merged[-1] if merged else None
        if m and x["a"] <= m["b"] and max(m["b"], x["b"]) - m["a"] <= MAX_WINDOW:
            m["b"] = max(m["b"], x["b"])
            m["sig"] += x["sig"]
        else:
            merged.append({"a": x["a"], "b": x["b"], "sig": list(x["sig"])})
    for m in merged:
        m["score"] = score(m["sig"])
    return merged


def score(sig: list) -> float:
    """Points per window. Viewer clips count by their views (campaign clippers post lots of
    zero-view test clips), chat by how far it jumps over its usual rate, loudness least."""
    clip_pts = min(5.0, sum(1.5 * math.log10(1 + s[1]["views"]) for s in sig if s[0] == "clip"))
    chat_pts = max((min(3.0, (s[1]["ratio"] - 1) / 2) + min(2.0, s[1]["hype"] / 3)
                    for s in sig if s[0] == "chat"), default=0)
    loud_pts = max((max(0.0, min(3.0, (s[1][1] - 15) / 6)) for s in sig if s[0] == "loud"), default=0)
    return round(clip_pts + chat_pts + loud_pts, 2)


def describe(sig: list) -> str:
    parts = []
    clips = [s[1] for s in sig if s[0] == "clip"]
    if clips:
        views = sum(c["views"] for c in clips)
        parts.append(f"👥 {len(clips)} viewer clip{'s' if len(clips) > 1 else ''} ({views} views)")
    chats = [s[1] for s in sig if s[0] == "chat"]
    if chats:
        best = max(chats, key=lambda c: c["ratio"])
        parts.append(f"💬 chat x{best['ratio']} ({best['hype']} hype msgs)")
    louds = [s[1] for s in sig if s[0] == "loud"]
    if louds:
        parts.append(f"⚡ +{max(l[1] for l in louds):.0f} dB")
    return " · ".join(parts) or "no signal"


def marks_for(sig: list, msgs: list[dict], a: float, b: float, max_chat: int = 18) -> list[tuple[float, str]]:
    marks = []
    for kind, s in sig:
        if kind == "clip":
            marks.append((s["start"], f"👥 viewer clip starts: \"{s['title']}\" ({s['views']} views, {s['dur']:.0f}s)"))
        elif kind == "loud":
            marks.append((s[0], f"⚡ loudness spike +{s[1]:.0f} dB"))
    near = [m for m in msgs if a <= m["t"] <= b]
    if len(near) > max_chat:  # busy chat: keep the hype messages first
        near = sorted(near, key=lambda m: (not twitch.is_hype(m["m"]), m["t"]))[:max_chat]
    marks += [(m["t"], f"💬 {m['m'][:90]}") for m in near]
    return sorted(marks, key=lambda x: x[0])


def lines(words: list[dict], marks: list[tuple[float, str]]) -> list[str]:
    """Group words into timestamped lines; insert marks where they fall."""
    out, cur, t0 = [], [], None
    pending = list(marks)

    def flush():
        nonlocal cur, t0
        if cur:
            out.append(f"[{fmt_time(t0)}] {' '.join(cur)}")
        cur, t0 = [], None

    prev_end = None
    for w in words:
        while pending and pending[0][0] <= w["s"]:
            flush()
            t, label = pending.pop(0)
            out.append(f"      [{fmt_time(t)}] {label}")
        if t0 is not None and (w["s"] - t0 > 10 or (prev_end and w["s"] - prev_end > 1.2)):
            flush()
        if t0 is None:
            t0 = w["s"]
        cur.append(w["w"])
        prev_end = w["e"]
        if w["w"].endswith((".", "?", "!")) and w["s"] - t0 > 3:
            flush()
    flush()
    out += [f"      [{fmt_time(t)}] {label}" for t, label in pending]
    return out


# ---------- main ----------

def twitch_signals(work: Path, sid: str, src: dict, refresh: bool) -> tuple[list, list]:
    vid = twitch.vod_id(src.get("url"))
    if not vid:
        return [], []
    cache = work / "moments" / f"{sid}.twitch.json"
    data = None if refresh else load(cache)
    if data is None:
        print(f"[{sid}] reading Twitch viewer clips and chat replay ...", flush=True)
        try:
            data = {"clips": twitch.viewer_clips(vid),
                    "chat": twitch.chat(vid, float(src.get("duration") or 0))}
        except Exception as e:  # Twitch is optional: fall back to loudness alone
            print(f"[{sid}] couldn't read Twitch data ({e}); using loudness only", flush=True)
            return [], []
        save(cache, data)
    print(f"[{sid}] {len(data['clips'])} viewer clips, {len(data['chat'])} chat messages", flush=True)
    return data["clips"], data["chat"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("work")
    p.add_argument("--source", help="source id (default: every source)")
    p.add_argument("--top", type=int, default=25, help="how many windows to transcribe on long sources")
    p.add_argument("--range", nargs=2, metavar=("START", "END"), help="only scan this part of a long stream")
    p.add_argument("--refresh", action="store_true", help="re-download Twitch clips and chat")
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
        dur = float(src.get("duration") or 0)
        r0 = parse_time(a.range[0]) if a.range else 0.0
        r1 = parse_time(a.range[1]) if a.range else dur
        span = r1 - r0

        clips, msgs = twitch_signals(work, sid, src, a.refresh)
        print(f"[{sid}] scanning loudness over {fmt_time(span)} ...", flush=True)
        louds = loud_spikes(loudness(audio, r0 or None, r1), r0, a.top)
        chats = [c for c in chat_spikes(msgs, dur, a.top) if r0 <= c["t"] <= r1] if msgs else []

        if span <= SHORT:
            print(f"[{sid}] short source: transcribing all of it ...", flush=True)
            sig = [("clip", c) for c in clips] + [("loud", l) for l in louds]
            windows = [{"n": 1, "start": r0, "end": r1, "score": None, "signals": describe(sig),
                        "sig": sig, "words": transcribe(audio, r0 or None, r1)}]
        else:
            cands = sorted(candidates(clips, chats, louds, r0, r1), key=lambda c: -c["score"])[: a.top]
            cands.sort(key=lambda c: c["a"])
            windows = []
            for n, c in enumerate(cands, 1):
                print(f"[{sid}] transcribing window {n}/{len(cands)} at {fmt_time(c['a'])} ({describe(c['sig'])}) ...",
                      flush=True)
                windows.append({"n": n, "start": round(c["a"], 2), "end": round(c["b"], 2), "score": c["score"],
                                "signals": describe(c["sig"]), "sig": c["sig"],
                                "words": transcribe(audio, c["a"], c["b"])})

        out_dir = work / "moments"
        save(out_dir / f"{sid}.json", {"source": sid, "windows": [{k: v for k, v in w.items() if k != "sig"}
                                                                   for w in windows]})
        md = [f"# Moments in '{sid}': {src.get('title', '')}",
              f"Source length {fmt_time(dur)}. All times are SOURCE times (use them in plan.json).",
              "Signals: 👥 viewer clip (people clipped this) > 💬 chat flood > ⚡ loudness (weakest: game audio is loud too).",
              "Transcript lines mix the streamer, the game's dialogue and music; 💬 lines are chat.", ""]
        if len(windows) == 1 and windows[0]["score"] is None:
            w = windows[0]
            marks = marks_for(w["sig"], [m for m in msgs if twitch.is_hype(m["m"])], r0, r1, max_chat=200)
            md += ["## Full transcript", ""] + lines(w["words"], marks)
        else:
            for w in sorted(windows, key=lambda w: -w["score"]):
                md += [f"## W{w['n']} · score {w['score']} · {w['signals']} · "
                       f"{fmt_time(w['start'])}-{fmt_time(w['end'])}", ""]
                body = lines(w["words"], marks_for(w["sig"], msgs, w["start"], w["end"]))
                md += (body or ["(no speech: game audio only. Peek at it before using.)"]) + [""]
        (out_dir / f"{sid}.md").write_text("\n".join(md), encoding="utf-8")
        print(f"[{sid}] {len(windows)} window(s), best first -> {out_dir / f'{sid}.md'}")


if __name__ == "__main__":
    main()
