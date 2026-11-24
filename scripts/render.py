"""The look of a clip: 9:16 layouts and on-screen text. Kept deliberately basic.

Layouts (all 1080x1920):
  fit    the whole 16:9 frame in the middle, a blurred copy behind it. Safe default, nothing cut off.
  split  the streamer's facecam on top, gameplay underneath. Needs "cam": [x, y, w, h] as fractions
         of the source frame (peek.py draws a grid to read them off).
  crop   a 9:16 slice of the frame, centred on "x" (0 = left edge, 1 = right edge). Most zoomed in.

On-screen text copies TikTok's own text tool: TikTok Sans (bundled in assets/fonts, OFL licensed)
in the "background" style, black text on white boxes that merge into one rounded shape, with emoji
inline. The hook sits on the seam between facecam and gameplay for the whole clip. Word-by-word
speech captions are optional (off by default, like most native clips).

Emoji come from the computer's own emoji font: Apple's on a Mac, Microsoft's on Windows, Noto on
Linux. Single-character emoji work everywhere; combined ones (skin tones, families, flags) show
their first character only.

All text is drawn with Pillow into transparent PNGs and laid over the video with ffmpeg's overlay
filter, so it works with any ffmpeg build (no drawtext or libass needed).
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from common import ROOT, find_font

W, H = 1080, 1920
TIKTOK_SANS = ROOT / "assets" / "fonts" / "TikTokSans.ttf"
EMOJI_FONTS = [
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "C:/Windows/Fonts/seguiemj.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf",
]


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
        return f, {"hook_y": int(H * 0.30), "cap_y": int(H * 0.68)}

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
        return f, {"hook_y": cam_h, "cap_y": cam_h + int(game_h * 0.70)}

    # fit
    fgw = even(W * clamp(zoom, 1.0, 1.8))
    fgh = even(fgw * sh / sw)
    top = (H - fgh) // 2
    f = (f"[vin]split=2[b0][f0];"
         f"[b0]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=12:2,"
         f"scale={W}:{H},eq=brightness=-0.12[bg];"
         f"[f0]scale={fgw}:{fgh},crop={min(fgw, W)}:{fgh}[fg];"
         f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[vl]")
    return f, {"hook_y": top, "cap_y": top + fgh + 170}


# ---------- emoji ----------

def _is_emoji(cp: int) -> bool:
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF
            or cp in (0x203C, 0x2049, 0x2194, 0x2195, 0x21A9, 0x21AA, 0x231A, 0x231B, 0x23F0, 0x23F3))


def split_runs(text: str) -> list[tuple[str, str]]:
    """'no way 😭😭' -> [('t', 'no way '), ('e', '😭'), ('e', '😭')]. Emoji runs hold the base character."""
    runs, buf, i = [], "", 0
    cps = [ord(c) for c in text]
    while i < len(cps):
        cp = cps[i]
        if _is_emoji(cp) and not 0x1F3FB <= cp <= 0x1F3FF:
            if buf:
                runs.append(("t", buf))
                buf = ""
            runs.append(("e", chr(cp)))
            i += 1
            while i < len(cps):  # swallow variation selectors, skin tones, keycaps, ZWJ joins
                c = cps[i]
                if c in (0xFE0F, 0x20E3) or 0x1F3FB <= c <= 0x1F3FF:
                    i += 1
                elif c == 0x200D and i + 1 < len(cps):
                    i += 2
                else:
                    break
            continue
        if cp not in (0xFE0F, 0x200D):
            buf += chr(cp)
        i += 1
    if buf:
        runs.append(("t", buf))
    return runs


class Emoji:
    """Color emoji from the system emoji font, as RGBA images of a given height."""

    def __init__(self):
        self.font = None
        for path in EMOJI_FONTS:
            if not Path(path).exists():
                continue
            for size in (160, 137, 109, 96, 72):  # bitmap emoji fonts only load at their own sizes
                try:
                    self.font, self.size = ImageFont.truetype(path, size), size
                    break
                except OSError:
                    continue
            if self.font:
                break
        self.cache: dict = {}

    def get(self, ch: str, height: int) -> Image.Image | None:
        if not self.font:
            return None
        key = (ch, height)
        if key not in self.cache:
            s = self.size
            im = Image.new("RGBA", (s * 2, s * 2), (0, 0, 0, 0))
            try:
                ImageDraw.Draw(im).text((s // 2, s // 2), ch, font=self.font, embedded_color=True)
            except Exception:
                self.cache[key] = None
                return None
            box = im.getbbox()
            if not box:
                self.cache[key] = None
                return None
            im = im.crop(box)
            self.cache[key] = im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)
        return self.cache[key]


# ---------- text blocks ----------

def tiktok_font(size: int, weight: str) -> ImageFont.FreeTypeFont:
    if TIKTOK_SANS.exists():
        f = ImageFont.truetype(str(TIKTOK_SANS), size)
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
        return f
    return ImageFont.truetype(find_font(), size)


class TextBlock:
    """Lays out text with inline emoji: wrapping, measuring, drawing."""

    def __init__(self, font: ImageFont.FreeTypeFont, emoji: Emoji):
        self.font, self.emoji = font, emoji
        self.size = font.size
        self.em_h = round(self.size * 1.02)
        cap = font.getbbox("H")
        self.cap_h = cap[3] - cap[1]

    def width(self, text: str) -> float:
        w = 0.0
        for kind, s in split_runs(text):
            if kind == "t":
                w += self.font.getlength(s)
            else:
                im = self.emoji.get(s, self.em_h)
                w += (im.width if im else 0) + self.size * 0.06
        return w

    def wrap(self, text: str, max_w: int) -> list[str]:
        lines = []
        for para in text.split("\n"):
            line = ""
            for word in para.split():
                test = f"{line} {word}".strip()
                if line and self.width(test) > max_w:
                    lines.append(line)
                    line = word
                else:
                    line = test
            if line:
                lines.append(line)
        return lines

    def draw_line(self, img: Image.Image, text: str, x: float, baseline: float, fill, stroke=0, stroke_fill=None):
        d = ImageDraw.Draw(img)
        for kind, s in split_runs(text):
            if kind == "t":
                d.text((x, baseline), s, font=self.font, fill=fill, anchor="ls",
                       stroke_width=stroke, stroke_fill=stroke_fill)
                x += self.font.getlength(s)
            else:
                im = self.emoji.get(s, self.em_h)
                if im:
                    x += self.size * 0.03
                    img.alpha_composite(im, (int(x), int(baseline + self.size * 0.14 - im.height)))
                    x += im.width + self.size * 0.03


def tiktok_box(img: Image.Image, block: TextBlock, text: str, center_y: int, max_w: int = 800):
    """TikTok's 'background' text: black text on white boxes, one per line, merged into one shape."""
    lines = block.wrap(text, max_w)[:4]
    if not lines:
        return
    line_h = round(block.size * 1.28)
    pad_x = round(block.size * 0.42)
    total = line_h * len(lines)
    top = int(clamp(center_y - total / 2, 40, H - total - 40))

    # one rectangle per line, then blur + threshold: rounds the outer corners and fills the
    # inner ones, which is exactly how TikTok joins the boxes of lines with different widths
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    widths = [block.width(l) for l in lines]
    for i, w in enumerate(widths):
        x0 = (W - w) / 2 - pad_x
        md.rectangle((x0, top + i * line_h, x0 + w + 2 * pad_x, top + (i + 1) * line_h), fill=255)
    r = block.size * 0.20
    mask = mask.filter(ImageFilter.GaussianBlur(r)).point(
        lambda v: 0 if v < 105 else 255 if v > 150 else int((v - 105) * 255 / 45))
    white = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    img.paste(white, (0, 0), mask)

    for i, (line, w) in enumerate(zip(lines, widths)):
        baseline = top + i * line_h + line_h / 2 + block.cap_h / 2
        block.draw_line(img, line, (W - w) / 2, baseline, fill=(0, 0, 0, 255))


def outline_text(img: Image.Image, block: TextBlock, text: str, center_y: int, max_w: int = 900):
    """TikTok's plain text style: white with a thin black outline. Used for speech captions."""
    lines = block.wrap(text, max_w)[:2]
    line_h = round(block.size * 1.2)
    top = center_y - line_h * len(lines) / 2
    for i, line in enumerate(lines):
        w = block.width(line)
        baseline = top + i * line_h + line_h / 2 + block.cap_h / 2
        block.draw_line(img, line, (W - w) / 2, baseline, fill=(255, 255, 255, 255),
                        stroke=max(3, block.size // 14), stroke_fill=(0, 0, 0, 255))


class Painter:
    def __init__(self, spots: dict, logo: dict | None, work: Path):
        emoji = Emoji()
        self.hook = TextBlock(tiktok_font(58, "SemiBold"), emoji)
        self.cap = TextBlock(tiktok_font(66, "Bold"), emoji)
        self.spots = spots
        self.logo = None
        if logo and logo.get("path"):
            lp = Path(logo["path"])
            lp = lp if lp.is_absolute() else work / lp
            if lp.exists():
                im = Image.open(lp).convert("RGBA")
                lw = int(logo.get("width", 220))
                self.logo = (im.resize((lw, int(im.height * lw / im.width))), logo.get("corner", "top-right"))

    def frame(self, hook: str | None, caption: str | None) -> Image.Image:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if caption:
            outline_text(img, self.cap, caption, self.spots["cap_y"])
        if hook:
            tiktok_box(img, self.hook, hook, self.spots["hook_y"])
        if self.logo:
            lg, corner = self.logo
            m = 48
            x = m if "left" in corner else W - lg.width - m
            y = m + 60 if "top" in corner else H - lg.height - m - 260
            img.alpha_composite(lg, (x, y))
        return img


# ---------- captions timing ----------

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunks(words: list[dict], max_words: int = 4, max_chars: int = 22) -> list[dict]:
    """Group words into short on-screen captions: [{"t": "text", "s", "e"}] in clip seconds."""
    out, cur = [], []

    def close():
        if cur:
            out.append({"t": " ".join(w["t"] for w in cur), "s": cur[0]["s"], "e": cur[-1]["e"]})
        cur.clear()

    for w in words:
        t = clean(w["w"]).strip(",.;:\"“”")
        if not any(ch.isalnum() for ch in t):  # lone dashes, ellipses, etc.
            continue
        item = {"t": t, "s": w["s"], "e": w["e"]}
        if cur and (len(cur) >= max_words
                    or len(" ".join(x["t"] for x in cur)) + len(t) + 1 > max_chars
                    or w["s"] - cur[-1]["e"] > 0.45
                    or w["s"] - cur[0]["s"] > 1.6):
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
