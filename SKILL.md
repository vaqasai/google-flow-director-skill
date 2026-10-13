---
name: google-flow-director
description: Make short videos with Google Flow end to end - one-time setup, script/storyboard writing, driving Flow's built-in agent in a saved browser session, attaching saved Characters, downloading the clips and burning in captions with ffmpeg. Use when the user wants to create, script, generate or caption a video, reel, short or cartoon with Google Flow (flow.google.com), or asks to set up or fix this workflow. Works on Windows, Linux and macOS with any agent that can run shell commands.
---
# Google Flow Director

Published by [vaqasai.in](https://vaqasai.in). Community skill, not affiliated with Google. This is a playbook plus small helpers, not a cage: you are expected to adapt, inspect the page, fix selectors and recover from errors yourself. `references/troubleshooting.md` lists the usual problems.

All commands are `python scripts/flow.py <command>` run from this skill's folder and print JSON. If `python` is not on PATH (Windows right after installing), use the python path printed by the bootstrap script. `flow.py --help` lists everything.

## 1. First time: install and set up (you do this, the user only signs in)
0. **Check the install.** Some installers skip folders: if `scripts/` or `references/` is empty, run `git clone --depth 1 https://github.com/vaqasai/google-flow-director-skill $TMP/fd` and copy the missing folders in (or, once `flow.py` exists, `flow.py doctor --repair`). `doctor` reports `skill_files`.
1. **Bootstrap** installs whatever is missing (Python deps in a private venv, ffmpeg, Chrome) and prints a JSON report:
   - Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1`
   - Linux/macOS: `bash scripts/bootstrap.sh`

   Read `items`; for any item not found, do its `fix_if_failed` and re-run. Details per OS: `references/windows.md`.
2. **Ask the user** (one short message, defaults in brackets): which Flow project (or "I'll open it for you"), which saved Characters (one or several; `flow.py characters` lists them, spelling/case need not match), any scene/location reference images (saved Scenes, or files they will give you to `upload`), format [1080x1920, 10s], captions on/off [on], mode `ask` or `auto` [ask], credit cap [20].
3. `python scripts/flow.py setup --characters "A,B" --width 1080 --height 1920 --duration 10 --mode ask --max-credits 20` opens a dedicated Chrome window with a persistent profile and prints `next` steps. Re-run `setup` any time to change settings.
4. **The user signs in to Google in that window** (on a headless server run `bash scripts/server-display.sh install` then `start`, and follow `references/server.md`: virtual screen, VNC over an SSH tunnel) and opens their Flow project. The profile keeps the session, so you never see or store a password. Then run `setup --detect-project` to save the project URL. Never copy cookies out of the profile.
5. `python scripts/flow.py doctor` should be all green, and `snapshot` should show `"status": "ready"`.

## 2. Each video
1. **Write the script** with the user: read `references/script-writing.md`. Keep it short and concrete; in `ask` mode get an OK before spending credits.
2. **Start clean** for a new video: `new-session`, then `attach` (all configured Characters and Scenes, or `--names "A,B" --scenes "Kitchen"`). Reference images from the user: `upload file.png ...`, then `characters --kind all` to see what Flow now has, and `attach --scenes` or just tell Flow's agent to use them.
3. **Talk to Flow's agent**: `send "<message>"`, or for multi-line text `--file msg.txt` (PowerShell: write the file, or pipe `@"..."@ | python scripts\flow.py send --file -`; never use `<<` there), then `wait`. Read the reply with `snapshot` (`chat`). Ask for staging advice, then a storyboard, then the clips, like a person would. Use `screenshot` to look at results.
4. **Spending**: modes are a convention between you and the user.
   - `ask`: before any generation, tell the user what you are about to make and the cost, and wait for a yes.
   - `auto`: proceed yourself, but stay under `max_credits` (`credits` shows used/remaining; `credits --add N` after each generation).
   - When Flow shows a confirmation card, `wait` returns `permission_card` with `cost`, `model`, `seconds` and `buttons`. Decide per the mode, then `approve` presses Approve, adds the cost to the counter and refuses if it would pass `max_credits` (tell the user; `--over-cap` only after they agree). To decline: `click --text Reject`. Flow's own "confirm before generating" setting is a useful second guard.
   - After approving, `wait --timeout 600` keeps polling through the queue (`job_state` queued/generating, `progress_pct`) until a video is `done` in `videos`. Download promptly: the signed URL expires.
5. **Corrections stay in the same session** by default: if something is off, `send` a focused fix to the same Flow agent thread (what to change, what to keep) instead of `new-session`, so it keeps the context and references. Start a new session only for a new video, or if the user prefers; it is their call.
6. **Download** the finished clip: `download` (or `download --video-url <url from snapshot.videos>`). If a menu appears first, `click --text "<option>"` then `download --no-click`.
7. **Check it yourself**: `probe` the file, extract a few frames with ffmpeg and look at them. Do not assume a clip is good because it exists.
8. **Finish**: `captions CLIP --text "..."` scales/pads to the configured format and burns the caption (omit `--text` for no caption). `y` is `auto` by default: it picks the calmest band away from faces; `--y 0.3` to force. Flow clips carry audio even if you asked for silence: add `--strip-audio` if you want none. Flow renders 720x1280; 1080x1920 is an upscale. Output lands in `output_dir`. Tell the user the final path and what you checked.
9. **Publish (optional)**: if the user wants it posted, offer Buffer and read `references/publishing.md`. You work out the API details yourself; ask for the token, keep it out of files, and show them what will go out before it does.

## Stop and tell the user when
Flow shows a CAPTCHA or "unusual activity", a policy block, out-of-credits, or the browser is signed out (`wait`/`snapshot` status: `challenge`, `policy`, `credits`, `signed_out`); or you are about to exceed the credit cap; or the same step fails twice after you tried to fix it. Do not retry a send blindly: check `snapshot` first so you do not double-send or double-spend.

## Adapting (you are allowed to)
- Flow's UI changes. If a command says a control was not found: `inspect --filter <word>` lists what is on the page, then edit the selector in `~/.flow-director/selectors.json` (overrides the shipped `selectors.json`, survives updates) and retry. `eval "<js>"` and `click --selector/--text` are escape hatches; your own browser tool works too.
- Edit `~/.flow-director/config.json` directly for anything `setup` does not expose (caption layout, font, port, chrome_path).
- If you fix something others would hit, say so in your reply so the user can update the skill.

## Files
`scripts/flow.py` CLI · `scripts/captions.py` ffmpeg finishing · `scripts/bootstrap.*` installers · `selectors.json` Flow UI selectors · `references/` script-writing, captions, publishing, windows, troubleshooting · state in `~/.flow-director` (config, profile, venv, credit count).

Need help with AI agents or a custom video workflow? **[vaqasai.in](https://vaqasai.in)**, hire us for consulting.
