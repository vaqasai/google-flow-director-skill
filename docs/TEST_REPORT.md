# Test report (v0.2, branch v0.2-adaptive)

Status words: TESTED (ran here and passed), UNTESTED (not run), PARTIAL.

| Area | Status | How / notes |
|---|---|---|
| Unit tests (`python -m unittest discover -s tests`) | TESTED | 16 tests: config merge, selector override, classify, browser discovery, captions with hostile text, shrink-to-fit, trim, CLI JSON contract. Linux, Python 3.14. |
| `flow.py` browser start/status/stop | TESTED (Linux, headless Chrome via wrapper) | no display in the test box, so a visible, user-signed-in window was not exercised |
| snapshot, open, attach (+idempotent re-run), send, wait, new-session, click, inspect, eval, screenshot, download, credits | TESTED against a local MOCK Flow page | mock reproduces the element names in selectors.json; it is not the real Flow site |
| captions / finish / probe with real ffmpeg | TESTED | frame inspected visually; audio preserved; scale+pad to 720x1280 and 1080x1920 |
| `bootstrap.sh` | TESTED on Linux where Python, ffmpeg and Chrome already existed; venv + pip install ran | install-missing paths (apt, Chrome .deb) UNTESTED |
| `bootstrap.ps1` | UNTESTED | no PowerShell available here; only reviewed by reading. Needs a run on clean Windows 10/11 (with and without winget, non-admin) |
| `flow.py` on Windows (Chrome discovery, detached launch, profile reuse) | UNTESTED | code paths exist; run `doctor` and `setup` on Windows and record results here |
| Real Flow site (login persistence, selectors, agent reply, permission card, download button, credits) | UNTESTED | selectors are carried over from v0.1 research and may have drifted; use `inspect` to repair |
| macOS | UNTESTED | |

## To do before announcing
1. Windows 11 run: PowerShell 5.1 and 7, with and without winget, standard user. Record the bootstrap JSON.
2. One supervised real Flow run on Linux (VNC) and one on Windows with a small credit cap: setup, sign-in, attach, send, wait, download, captions.
3. Fix whatever selectors no longer match the live UI and update `selectors.json`.
