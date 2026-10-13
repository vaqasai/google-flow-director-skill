# Captions and finishing

`python scripts/flow.py captions CLIP.mp4 --text "Your line here" [--out final.mp4]`

What it does: scales and pads the clip to the configured `format` (letterbox, no stretching), draws the caption into a transparent PNG with Pillow, overlays it with ffmpeg, re-encodes to H.264/AAC mp4, then prints the probed result (size, duration, audio). The text never goes inside an ffmpeg filter string, so quotes, colons and emoji are safe on every OS.

## Options
- `--text` or `--text-file` (UTF-8), none = just scale/pad.
- `--x`, `--y` fractions of the frame (x = centre, y = top of the text block), `--font-size` fraction of height, `--start`/`--end` seconds. Defaults come from `config.json` -> `captions` (`x 0.5, y 0.25, font_size 0.045, max_width 0.86, start 0.3, max_lines 3`).
- `--trim SECONDS` cuts the output to a length. `--width/--height` override the configured format for this run.
- `font` in config: any .ttf/.otf path. Default: Segoe UI/Arial (Windows), Helvetica (macOS), fontconfig sans / DejaVu (Linux), else Pillow's built-in font.

## Behaviour to know
- If the text is too long for `max_lines`/`max_width` the font shrinks automatically (up to 14 steps). If it is still ugly, shorten the text.
- Placement is clamped inside the frame instead of failing.
- Always look at one frame afterwards: `ffmpeg -ss 1.5 -i final.mp4 -frames:v 1 frame.png`, then view it.
- Several captions over time: run `captions` once per segment on the result of the previous run with different `--start/--end` and `--y`.
- Captions are optional. For clips with burned-in speech or text from Flow, skip them.
