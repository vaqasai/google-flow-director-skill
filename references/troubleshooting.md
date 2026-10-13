# Troubleshooting (you are expected to fix these yourself)

Every `flow.py` failure prints `{"ok": false, "error": ..., "hint": ...}`. Start with the hint, then `doctor`, `snapshot`, `screenshot`.

| Symptom | Likely cause | What to do |
|---|---|---|
| `doctor`: playwright / PIL missing | bootstrap not run, or run with another Python | run the bootstrap script; use the venv python it prints |
| `the Flow browser is not running` | Chrome was closed | `flow.py browser start` (login is kept in the profile) |
| `Chrome did not open debug port` | another Chrome uses the same profile; port taken; security software | close that Chrome, or change `port` in config.json, then `browser start` |
| `snapshot` status `signed_out` | session expired or never signed in | ask the user to sign in in the Flow window; re-run `snapshot` |
| status `unknown`, `agent_panel`/`composer` false | wrong page, project not open, or UI changed | `open`, then `screenshot`; if the page looks right, the selectors drifted (next row) |
| `control not found: <selector>` | Flow UI changed | `inspect --filter <word>` to find the real element, put the new selector in `~/.flow-director/selectors.json`, retry |
| `composer text differs from the message` | rich editor ate characters | retry `send --slow`; very long messages: split them |
| `message may not have been sent` | slow page or UI change | `snapshot` to see the chat; only re-send if the text is not in `chat` (avoid double spend) |
| `attach`: `no unique Character matches` | name unlike any saved Character, or two are equally close | `flow.py characters` lists the saved names; `attach` already ignores case/punctuation (`mr bear` = `Mr. bear`) and fixes the config name for you |
| `download`: no download started | a menu (resolution/format) is in the way, or the button label differs | read the visible controls in the error, `click --text "..."`, then `download --no-click`; or `snapshot` -> `videos` -> `download --video-url` |
| `wait` returns `permission_card` | Flow asks to confirm a paid action | read `cost`/`model`, decide per mode (see SKILL.md), then `approve` |
| `wait` returns `timeout` while `job_state` is queued/generating | Flow queues jobs under high demand (minutes) | `wait --timeout 600` again; download when `videos` shows `done` |
| `approve`: `would exceed the credit cap` | cost + used > `max_credits` | ask the user; `setup --max-credits N` or `approve --over-cap` after they agree |
| `open` lands on flow.google.com/about, status `unknown` | not signed in, or no project yet | sign in in that window, create/open a project, `setup --detect-project` |
| tests fail with exit 0 instead of 2 | a real Flow browser is on the port | fixed: tests use their own free port; update the repo |
| `wait` returns `challenge`/`policy`/`credits`/`signed_out` | Flow blocked or needs the human | stop and tell the user exactly what the page says |
| `ffmpeg failed` | bad/corrupt input, or ffmpeg missing | `probe` the file; `doctor` for ffmpeg |
| Caption looks wrong | text too long or placement | shorten; adjust `--y`, `--font-size`; see `captions.md` |

## Headless Linux (no display)
The user must be able to see and use the Chrome window once to sign in.
- Start a virtual display and expose it: e.g. `Xvfb :1 -screen 0 1440x900x24 &`, `export DISPLAY=:1`, then a VNC server on it (`x11vnc -display :1 -forever -nopw -localhost`, reached through an SSH tunnel; or TigerVNC/noVNC). Only expose it through an authenticated tunnel.
- Run `flow.py setup`, have the user connect, sign in, open the project. After that the profile keeps the session and the agent can run with the same `DISPLAY`.

## Rules of thumb
- Prefer `snapshot`/`screenshot` over guessing what the page shows.
- Change one thing at a time and re-test; record selector changes you made in your reply.
- Never print, copy or commit anything from `~/.flow-director/profile` (it holds the login).
- If you hit a bot check, stop. Do not try to get around it.
