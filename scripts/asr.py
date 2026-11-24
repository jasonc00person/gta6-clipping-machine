"""Speech to text with word timestamps.

Apple Silicon Macs use mlx-whisper (runs on the GPU, fast). Everything else uses faster-whisper
(NVIDIA GPU when present, otherwise CPU). The first run downloads the model, about 0.5 to 1.6 GB.

Override the model with CLIP_WHISPER_MODEL (an mlx-community repo on Mac, a faster-whisper
model name elsewhere, e.g. "small", "medium", "large-v3-turbo").
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from common import is_apple_silicon, need, run

_model = None


def _extract(src: Path, start: float | None, end: float | None, out: Path):
    need("ffmpeg")
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", src]
    if end is not None:
        cmd += ["-t", f"{end - (start or 0):.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out]
    run(cmd)


# Whisper invents these over silence and music.
HALLUCINATIONS = {"thank you.", "thank you", "thanks for watching!", "thanks for watching.",
                  "thank you for watching.", "you", "bye.", "subtitles by the amara.org community"}


def _mlx(wav: Path) -> list[dict]:
    import mlx_whisper

    repo = os.environ.get("CLIP_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
    r = mlx_whisper.transcribe(
        str(wav), path_or_hf_repo=repo, word_timestamps=True,
        condition_on_previous_text=False, language=os.environ.get("CLIP_LANGUAGE"),
    )
    words = []
    for seg in r.get("segments", []):
        if seg.get("text", "").strip().lower() in HALLUCINATIONS:
            continue
        for w in seg.get("words", []):
            words.append({"w": w["word"].strip(), "s": float(w["start"]), "e": float(w["end"])})
    return words


def _faster(wav: Path) -> list[dict]:
    global _model
    from faster_whisper import WhisperModel

    if _model is None:
        name = os.environ.get("CLIP_WHISPER_MODEL")
        try:
            import ctranslate2
            cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            cuda = False
        name = name or ("large-v3-turbo" if cuda else "small")
        print(f"  loading whisper '{name}' on {'GPU' if cuda else 'CPU'} ...", flush=True)
        _model = WhisperModel(name, device="cuda" if cuda else "cpu",
                              compute_type="float16" if cuda else "int8")
    segs, _ = _model.transcribe(
        str(wav), word_timestamps=True, vad_filter=True,
        condition_on_previous_text=False, language=os.environ.get("CLIP_LANGUAGE"),
    )
    words = []
    for seg in segs:
        if seg.text.strip().lower() in HALLUCINATIONS:
            continue
        for w in seg.words or []:
            words.append({"w": w.word.strip(), "s": float(w.start), "e": float(w.end)})
    return words


def transcribe(src: Path, start: float | None = None, end: float | None = None) -> list[dict]:
    """Words of src[start:end] as [{"w", "s", "e"}], times in src seconds."""
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        _extract(Path(src), start, end, wav)
        words = _mlx(wav) if is_apple_silicon() else _faster(wav)
    off = start or 0.0
    clean = []
    for w in words:
        if not w["w"] or w["e"] - w["s"] > 3.0:  # drop empty tokens and stretched hallucinations
            continue
        clean.append({"w": w["w"], "s": round(w["s"] + off, 3), "e": round(w["e"] + off, 3)})
    return clean
