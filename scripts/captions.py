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

DEFAULT_LAYOUT = {"x": 0.5, "y": 0.25, "font_size": 0.045, "max_width": 0.86,
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
    top = min(max(0, round(height * layout["y"])), max(0, height - text_h))
    draw.multiline_text((left - bbox[0], top - bbox[1]), rendered, font=font, fill="white",
                        stroke_width=stroke, stroke_fill="black", spacing=spacing, align="center")
    image.save(destination)
    return {"lines": len(lines), "font_px": size, "bounds": [left, top, left + text_w, top + text_h]}


def probe(video):
    """ffprobe summary: width, height, duration, has_audio."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
                         capture_output=True, text=True, timeout=60, check=True).stdout
    info = json.loads(out)
    stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    return {"width": stream["width"], "height": stream["height"],
            "duration": round(float(info["format"]["duration"]), 3),
            "has_audio": any(s["codec_type"] == "audio" for s in info["streams"])}


def finish(source, output, width, height, caption=None, layout=None, font=None, trim=None):
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
            info = render_overlay(caption, width, height, layout, find_font(font), tmp / "caption.png")
            seconds = probe(source)["duration"]
            end = layout["end"] if layout["end"] is not None else (trim or seconds)
            extra_in = ["-i", "caption.png"]
            graph = ["-filter_complex",
                     f"[0:v]{base}[b];[b][1:v]overlay=0:0:enable='between(t,{layout['start']},{end})'[v]"]
            mapping = "[v]"
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(source.resolve()), *extra_in, *graph]
        if trim:
            cmd += ["-t", str(trim)]
        result = tmp / "result.mp4"
        cmd += ["-map", mapping, "-map", "0:a?", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-movflags", "+faststart", str(result)]
        done = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=600)
        if done.returncode != 0:
            raise RuntimeError("ffmpeg failed: " + done.stderr.strip()[-600:])
        shutil.move(str(result), str(output))
    return {"output": str(output), "caption": info or None, **probe(output)}
