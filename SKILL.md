---
name: google-flow-director
description: Make short videos with Google Flow end to end - one-time setup, script/storyboard writing, driving Flow's built-in agent in a saved browser session, attaching saved Characters, downloading the clips and burning in captions with ffmpeg. Use when the user wants to create, script, generate or caption a video, reel, short or cartoon with Google Flow (flow.google.com), or asks to set up or fix this workflow. Works on Windows, Linux and macOS with any agent that can run shell commands.
---
# Google Flow Director

Published by [vaqasai.in](https://vaqasai.in). Community skill, not affiliated with Google. This is a playbook plus small helpers, not a cage: you are expected to adapt, inspect the page, fix selectors and recover from errors yourself. `references/troubleshooting.md` lists the usual problems.

All commands are `python scripts/flow.py <command>` run from this skill's folder and print JSON. If `python` is not on PATH (Windows right after installing), use the python path printed by the bootstrap script. `flow.py --help` lists everything.

## 1. First time: install and set up (you do this, the user only signs in)
1. **Bootstrap** installs whatever is missing (Python deps in a private venv, ffmpeg, Chrome) and prints a JSON report:
   - Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1`
   - Linux/macOS: `bash scripts/bootstrap.sh`

   Read `items`; for any item not found, do its `fix_if_failed` and re-run. Details per OS: `references/windows.md`.
2. **Ask the user** (one short message, defaults in brackets): which Flow project (or "I'll open it for you"), the exact saved Character names, format [1080x1920, 10s], captions on/off [on], mode `ask` or `auto` [ask], credit cap [20].
3. `python scripts/flow.py setup --characters "A,B" --width 1080 --height 1920 --duration 10 --mode ask --max-credits 20` opens a dedicated Chrome window with a persistent profile and prints `next` steps. Re-run `setup` any time to change settings.
4. **The user signs in to Google in that window** (remote desktop/VNC if the machine is headless) and opens their Flow project. The profile keeps the session, so you never see or store a password. Then run `setup --detect-project` to save the project URL. Never copy cookies out of the profile.
5. `python scripts/flow.py doctor` should be all green, and `snapshot` should show `"status": "ready"`.

## 2. Each video
1. **Write the script** with the user: read `references/script-writing.md`. Keep it short and concrete; in `ask` mode get an OK before spending credits.
2. **Start clean**: `new-session`, then `attach` (uses the configured Characters).
3. **Talk to Flow's agent**: `send "<message>"` (or `--file msg.txt`), then `wait`. Read the reply with `snapshot` (`chat`). Ask for staging advice, then a storyboard, then the clips, like a person would. Use `screenshot` to look at results.
4. **Spending**: modes are a convention between you and the user.
   - `ask`: before any generation, tell the user what you are about to make and the cost, and wait for a yes.
   - `auto`: proceed yourself, but stay under `max_credits` (`credits` shows used/remaining; `credits --add N` after each generation).
   - When Flow shows a confirmation card, `wait` returns `permission_card` with its text. Read the quoted cost, decide per the mode, then confirm with `click --text "<button label>"`. Flow's own agent setting "confirm before generating" is a useful second guard in `ask` mode.
5. **Download** the finished clip: `download` (or `download --video-url <url from snapshot.videos>`). If a menu appears first, `click --text "<option>"` then `download --no-click`.
6. **Check it yourself**: `probe` the file, extract a few frames with ffmpeg and look at them. Do not assume a clip is good because it exists.
7. **Finish**: `captions CLIP --text "..."` scales/pads to the configured format and burns the caption (omit `--text` for no caption). Output lands in `output_dir`. Tell the user the final path and what you checked.

## Stop and tell the user when
Flow shows a CAPTCHA or "unusual activity", a policy block, out-of-credits, or the browser is signed out (`wait`/`snapshot` status: `challenge`, `policy`, `credits`, `signed_out`); or you are about to exceed the credit cap; or the same step fails twice after you tried to fix it. Do not retry a send blindly: check `snapshot` first so you do not double-send or double-spend.

## Adapting (you are allowed to)
- Flow's UI changes. If a command says a control was not found: `inspect --filter <word>` lists what is on the page, then edit the selector in `~/.flow-director/selectors.json` (overrides the shipped `selectors.json`, survives updates) and retry. `eval "<js>"` and `click --selector/--text` are escape hatches; your own browser tool works too.
- Edit `~/.flow-director/config.json` directly for anything `setup` does not expose (caption layout, font, port, chrome_path).
- If you fix something others would hit, say so in your reply so the user can update the skill.

## Files
`scripts/flow.py` CLI · `scripts/captions.py` ffmpeg finishing · `scripts/bootstrap.*` installers · `selectors.json` Flow UI selectors · `references/` script-writing, captions, windows, troubleshooting · state in `~/.flow-director` (config, profile, venv, credit count).

Need help with AI agents or a custom video workflow? **[vaqasai.in](https://vaqasai.in)**, hire us for consulting.
