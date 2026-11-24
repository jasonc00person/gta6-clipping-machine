"""The look of a clip: 9:16 layouts, captions, hook text, logo. Kept deliberately basic.

Layouts (all 1080x1920):
  fit    the whole 16:9 frame in the middle, a blurred copy behind it. Safe default, nothing cut off.
  split  the streamer's facecam on top, gameplay underneath. Needs "cam": [x, y, w, h] as fractions
         of the source frame (peek.py draws a grid to read them off).
  crop   a 9:16 slice of the frame, centred on "x" (0 = left edge, 1 = right edge). Most zoomed in.

All text is drawn with Pillow into transparent PNGs and laid over the video with ffmpeg's overlay
filter, so it works with any ffmpeg build (no drawtext or libass needed).
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import find_font

W, H = 1080, 1920


def even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------- layouts ----------

def layout(clip: dict, sw: int, sh: int) -> tuple[str, dict]:
    """ffmpeg filter from [vin] to [vl], plus where the text goes."""
    kind = clip.get("layout", "fit")
    zoom = float(clip.get("zoom", 1.0))

    if kind == "crop":
        cw = min(sw, even(sh * 9 / 16))
        cx = int(clamp(sw * float(clip.get("x", 0.5)) - cw / 2, 0, sw - cw))
        f = f"[vin]crop={cw}:{sh}:{cx}:0,scale={W}:{H},setsar=1[vl]"
        return f, {"hook_top": 230, "cap_y": int(H * 0.66)}

    if kind == "split":
        cam = clip.get("cam")
        if not cam or len(cam) != 4:
            raise ValueError(f"clip '{clip.get('name')}': layout split needs \"cam\": [x, y, w, h]")
        cx, cy, cw, ch = cam[0] * sw, cam[1] * sh, cam[2] * sw, cam[3] * sh
        cam_h = even(clamp(W * ch / cw, 560, 880))
        aspect = W / cam_h
        if cw / ch > aspect:          # too wide: trim the sides
            nw = ch * aspect
            cx, cw = cx + (cw - nw) / 2, nw
        else:                          # too tall: trim top and bottom
            nh = cw / aspect
            cy, ch = cy + (ch - nh) / 2, nh
        cx, cy, cw, ch = int(cx), int(cy), even(cw), even(ch)
        cx, cy = int(clamp(cx, 0, sw - cw)), int(clamp(cy, 0, sh - ch))

        game_h = H - cam_h
        g_aspect = W / game_h
        gh = sh / max(zoom, 1.0)
        gw = gh * g_aspect
        if gw > sw:
            gw, gh = sw, sw / g_aspect
        gw, gh = even(gw), even(gh)
        gx = int(clamp(sw * float(clip.get("game_x", 0.5)) - gw / 2, 0, sw - gw))
        gy = int(clamp(sh * float(clip.get("game_y", 0.5)) - gh / 2, 0, sh - gh))
        f = (f"[vin]split=2[c0][g0];"
             f"[c0]crop={cw}:{ch}:{cx}:{cy},scale={W}:{cam_h},setsar=1[cam];"
             f"[g0]crop={gw}:{gh}:{gx}:{gy},scale={W}:{game_h},setsar=1[game];"
             f"[cam][game]vstack=2[vl]")
        return f, {"hook_top": cam_h + 36, "cap_y": cam_h + int(game_h * 0.64)}

    # fit
    fgw = even(W * clamp(zoom, 1.0, 1.8))
    fgh = even(fgw * sh / sw)
    top = (H - fgh) // 2
    f = (f"[vin]split=2[b0][f0];"
         f"[b0]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=12:2,"
         f"scale={W}:{H},eq=brightness=-0.12[bg];"
         f"[f0]scale={fgw}:{fgh},crop={min(fgw, W)}:{fgh}[fg];"
         f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[vl]")
    return f, {"hook_bottom": top - 40, "cap_y": top + fgh + 170}


# ---------- text ----------

_EMOJI = re.compile("[\U00010000-\U0010FFFF☀-➿️]")


def plain(text: str) -> str:
    """Strip emoji: the caption font has no emoji glyphs. Put emoji in the post caption instead."""
    return re.sub(r"\s+", " ", _EMOJI.sub("", text)).strip()


def wrap(draw, text: str, font, max_w: int) -> list[str]:
    out = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            test = f"{line} {word}".strip()
            if line and draw.textlength(test, font=font) > max_w:
                out.append(line)
                line = word
            else:
                line = test
        if line:
            out.append(line)
    return out


class Painter:
    def __init__(self, spots: dict, logo: dict | None, work: Path):
        font = find_font()
        self.cap_font = ImageFont.truetype(font, 82)
        self.hook_font = ImageFont.truetype(font, 54)
        self.spots = spots
        self.logo = None
        if logo and logo.get("path"):
            lp = Path(logo["path"])
            lp = lp if lp.is_absolute() else work / lp
            if lp.exists():
                img = Image.open(lp).convert("RGBA")
                lw = int(logo.get("width", 220))
                self.logo = (img.resize((lw, int(img.height * lw / img.width))), logo.get("corner", "top-right"))

    def frame(self, hook: str | None, caption: str | None) -> Image.Image:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if hook:
            self._hook(d, hook)
        if caption:
            self._caption(d, caption)
        if self.logo:
            lg, corner = self.logo
            m = 48
            x = m if "left" in corner else W - lg.width - m
            y = m + 60 if "top" in corner else H - lg.height - m - 260
            img.alpha_composite(lg, (x, y))
        return img

    def _hook(self, d, text: str):
        f, pad_x, pad_y = self.hook_font, 28, 14
        lines = wrap(d, text, f, 900)[:3]
        lh = f.size + 2 * pad_y
        if "hook_top" in self.spots:
            y = self.spots["hook_top"]
        else:
            y = self.spots["hook_bottom"] - lh * len(lines)
        y = max(60, y)
        for line in lines:
            tw = d.textlength(line, font=f)
            x0 = (W - tw) / 2 - pad_x
            d.rounded_rectangle((x0, y, x0 + tw + 2 * pad_x, y + lh), radius=16, fill=(255, 255, 255, 255))
            d.text((W / 2, y + lh / 2), line, font=f, fill=(0, 0, 0, 255), anchor="mm")
            y += lh

    def _caption(self, d, text: str):
        f = self.cap_font
        lines = wrap(d, text, f, 980)[:2]
        y = self.spots["cap_y"] - (len(lines) - 1) * f.size * 0.55
        for line in lines:
            d.text((W / 2, y), line, font=f, fill=(255, 255, 255, 255), anchor="mm",
                   stroke_width=8, stroke_fill=(0, 0, 0, 255))
            y += f.size * 1.1


# ---------- captions timing ----------

def chunks(words: list[dict], max_words: int = 3, max_chars: int = 16) -> list[dict]:
    """Group words into short on-screen captions: [{"t": "TEXT", "s", "e"}] in clip seconds."""
    out, cur = [], []

    def close():
        if cur:
            text = " ".join(w["t"] for w in cur)
            out.append({"t": text, "s": cur[0]["s"], "e": cur[-1]["e"]})
        cur.clear()

    for w in words:
        t = plain(w["w"]).upper().strip(",.;:\"“”")
        if not any(ch.isalnum() for ch in t):  # lone dashes, ellipses, etc.
            continue
        item = {"t": t, "s": w["s"], "e": w["e"]}
        if cur and (len(cur) >= max_words
                    or len(" ".join(x["t"] for x in cur)) + len(t) + 1 > max_chars
                    or w["s"] - cur[-1]["e"] > 0.45
                    or w["s"] - cur[0]["s"] > 1.4):
            close()
        cur.append(item)
        if w["w"].rstrip().endswith((".", "?", "!")):
            close()
    close()
    for i, c in enumerate(out):  # hold each caption until the next one, up to 0.5 s of silence
        nxt = out[i + 1]["s"] if i + 1 < len(out) else c["e"] + 0.5
        c["e"] = min(nxt, c["e"] + 0.5)
    return out


def overlay_track(out_dir: Path, painter: Painter, duration: float, caps: list[dict],
                  hook: str | None, hook_secs: float | None) -> Path:
    """Write one PNG per on-screen state and an ffconcat file that plays them on time."""
    out_dir.mkdir(parents=True, exist_ok=True)
    hook_end = duration if hook_secs is None else min(duration, float(hook_secs))
    cuts = {0.0, duration, hook_end}
    for c in caps:
        cuts.update((clamp(c["s"], 0, duration), clamp(c["e"], 0, duration)))
    cuts = sorted(cuts)

    cache: dict[tuple, str] = {}
    entries = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 0.001:
            continue
        mid = (a + b) / 2
        cap = next((c["t"] for c in caps if c["s"] <= mid < c["e"]), None)
        hk = hook if (hook and mid < hook_end) else None
        key = (hk, cap)
        if key not in cache:
            name = f"o{len(cache):04d}.png"
            painter.frame(hk, cap).save(out_dir / name)
            cache[key] = name
        entries.append((cache[key], b - a))

    lines = ["ffconcat version 1.0"]
    for name, dur in entries:
        lines += [f"file {name}", f"duration {dur:.4f}"]
    lines.append(f"file {entries[-1][0]}")  # the last image must be listed twice
    path = out_dir / "overlay.ffconcat"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
