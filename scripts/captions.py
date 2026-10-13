"""Finish a clip with ffmpeg: scale/pad to the target format and optionally burn in a caption.

The caption is drawn with Pillow into a transparent PNG and overlaid by ffmpeg, so no
user text is ever placed inside an ffmpeg filter string (no escaping problems on any OS).
Layout problems are fixed automatically where possible (the font shrinks to fit) instead of failing.
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

DEFAULT_LAYOUT = {"x": 0.5, "y": "auto", "font_size": 0.045, "max_width": 0.86,
                  "start": 0.3, "end": None, "max_lines": 3}


def find_font(configured=None):
    """Return a usable font path, or None (Pillow's built-in font is then used)."""
    if configured and Path(configured).is_file():
        return str(configured)
    candidates = []
    if os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates = [fonts / "segoeui.ttf", fonts / "arial.ttf", fonts / "calibri.ttf"]
    elif os.uname().sysname == "Darwin":
        candidates = [Path("/System/Library/Fonts/Helvetica.ttc"), Path("/Library/Fonts/Arial.ttf")]
    else:
        if shutil.which("fc-match"):
            try:
                out = subprocess.run(["fc-match", "-f", "%{file}", "sans"], capture_output=True,
                                     text=True, timeout=10).stdout.strip()
                if out:
                    candidates.append(Path(out))
            except (OSError, subprocess.SubprocessError):
                pass
        candidates += [Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                       Path("/usr/share/fonts/TTF/DejaVuSans.ttf")]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _wrap(draw, text, font, limit):
    lines = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            candidate = (line + " " + word).strip()
            if draw.textlength(candidate, font=font) > limit and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
    return lines


def render_overlay(text, width, height, layout, font_path, destination):
    """Draw the caption onto a transparent frame-sized PNG. Returns a small info dict."""
    from PIL import Image, ImageDraw, ImageFont
    layout = {**DEFAULT_LAYOUT, **(layout or {})}
    size = max(8, int(height * layout["font_size"]))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for _ in range(14):  # shrink until it fits the width and line budget
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default(size)
        stroke = max(1, round(height * 0.0025))
        limit = int(width * layout["max_width"]) - 2 * stroke
        too_wide = any(draw.textlength(w, font=font) > limit for w in text.split())
        lines = _wrap(draw, text, font, limit)
        if not too_wide and len(lines) <= layout["max_lines"]:
            break
        size = max(8, int(size * 0.9))
    rendered = "\n".join(lines)
    spacing = max(2, round(height * 0.012))
    bbox = draw.multiline_textbbox((0, 0), rendered, font=font, spacing=spacing, stroke_width=stroke)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    left = min(max(0, round(width * layout["x"] - text_w / 2)), max(0, width - text_w))
    y = FALLBACK_Y if layout["y"] == "auto" else layout["y"]
    top = min(max(0, round(height * y)), max(0, height - text_h))
    draw.multiline_text((left - bbox[0], top - bbox[1]), rendered, font=font, fill="white",
                        stroke_width=stroke, stroke_fill="black", spacing=spacing, align="center")
    image.save(destination)
    return {"lines": len(lines), "font_px": size, "bounds": [left, top, left + text_w, top + text_h]}


FALLBACK_Y = 0.32


def auto_y(source, width, height, block_frac, start, end, base_filter, duration):
    """Pick the caption's top edge where the picture is calmest and least face/skin-like, so it avoids faces.

    Samples a few frames with ffmpeg, scores horizontal bands (edge density + skin-tone share) and
    returns (y_fraction, reason). Any problem falls back to FALLBACK_Y. Pillow only, no OpenCV.
    """
    try:
        from PIL import Image, ImageFilter
        sw, sh = max(24, width // 12), max(24, height // 12)
        lo, hi = max(0.0, start), min(end if end is not None else duration, duration)
        times = [lo + (hi - lo) * f for f in (0.1, 0.35, 0.6, 0.9)] if hi > lo else [0.0]
        frames = []
        with tempfile.TemporaryDirectory(prefix="flow-auto-y-") as tmp:
            for i, t in enumerate(times):
                out = Path(tmp) / f"f{i}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{t:.2f}", "-i", str(Path(source).resolve()),
                                "-frames:v", "1", "-vf", f"{base_filter},scale={sw}:{sh}", str(out)],
                               capture_output=True, timeout=60)
                if out.is_file():
                    frames.append(Image.open(out).convert("RGB"))
        if not frames:
            return FALLBACK_Y, "no frames; fallback"
        rows = max(1, round(block_frac * sh))
        best = None
        for y_frac in [x / 100 for x in range(8, 71, 2)]:       # keep clear of the top bar and the bottom UI zone
            top = round(y_frac * sh)
            if top + rows > sh:
                continue
            score = 0.0
            for frame in frames:
                box = frame.crop((0, top, sw, top + rows))
                edges = box.convert("L").filter(ImageFilter.FIND_EDGES)
                edge = sum(edges.tobytes()) / (255 * sw * rows)
                ycc = box.convert("YCbCr").tobytes()
                skin = sum(1 for i in range(0, len(ycc), 3) if 77 <= ycc[i + 1] <= 127 and 133 <= ycc[i + 2] <= 173) / (sw * rows)
                score += 2.5 * skin + 2.0 * edge
            score = score / len(frames) + 0.25 * abs(y_frac - FALLBACK_Y)   # mild pull toward the usual spot
            if best is None or score < best[0]:
                best = (score, y_frac)
        return (best[1], "calmest band") if best else (FALLBACK_Y, "no band fits; fallback")
    except Exception as error:  # never fail a render over placement
        return FALLBACK_Y, f"auto failed ({type(error).__name__}); fallback"


def probe(video):
    """ffprobe summary: width, height, duration, has_audio."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
                         capture_output=True, text=True, timeout=60, check=True).stdout
    info = json.loads(out)
    stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    return {"width": stream["width"], "height": stream["height"],
            "duration": round(float(info["format"]["duration"]), 3),
            "has_audio": any(s["codec_type"] == "audio" for s in info["streams"])}


def finish(source, output, width, height, caption=None, layout=None, font=None, trim=None, strip_audio=False):
    """Scale+pad `source` to width x height, optionally burn in `caption`, write `output` (mp4)."""
    source, output = Path(source), Path(output)
    if not source.is_file():
        raise FileNotFoundError(f"input video not found: {source}")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH; run the bootstrap script")
    output.parent.mkdir(parents=True, exist_ok=True)
    base = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1")
    info = {}
    with tempfile.TemporaryDirectory(prefix="flow-finish-") as tmp:
        tmp = Path(tmp)
        extra_in, graph, mapping = [], ["-vf", base], "0:v:0"
        if caption:
            layout = {**DEFAULT_LAYOUT, **(layout or {})}
            seconds = probe(source)["duration"]
            if layout["y"] == "auto":
                probe_info = render_overlay(caption, width, height, {**layout, "y": 0.0}, find_font(font), tmp / "probe.png")
                block = (probe_info["bounds"][3] - probe_info["bounds"][1]) / height
                chosen, why = auto_y(source, width, height, block, layout["start"], layout["end"] or trim or seconds, base, seconds)
                layout = {**layout, "y": chosen}
            else:
                why = None
            info = render_overlay(caption, width, height, layout, find_font(font), tmp / "caption.png")
            info["y"] = layout["y"]
            if why:
                info["y_auto"] = why
            end = layout["end"] if layout["end"] is not None else (trim or seconds)
            extra_in = ["-i", "caption.png"]
            graph = ["-filter_complex",
                     f"[0:v]{base}[b];[b][1:v]overlay=0:0:enable='between(t,{layout['start']},{end})'[v]"]
            mapping = "[v]"
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(source.resolve()), *extra_in, *graph]
        if trim:
            cmd += ["-t", str(trim)]
        result = tmp / "result.mp4"
        cmd += ["-map", mapping, *([] if strip_audio else ["-map", "0:a?"]), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                *(["-an"] if strip_audio else ["-c:a", "aac"]), "-movflags", "+faststart", str(result)]
        done = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=600)
        if done.returncode != 0:
            raise RuntimeError("ffmpeg failed: " + done.stderr.strip()[-600:])
        shutil.move(str(result), str(output))
    return {"output": str(output), "caption": info or None, "audio_stripped": bool(strip_audio), **probe(output)}
