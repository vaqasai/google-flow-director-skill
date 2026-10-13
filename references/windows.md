# Windows

Windows is a first-class target. `scripts/bootstrap.ps1` installs everything for the current user (no admin needed in the normal case):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```
`-ExecutionPolicy Bypass` applies to that one process only; no system setting changes. The script prints a JSON report; fix any item with `found: false` using its `fix_if_failed`, then re-run (it is idempotent).

## What it installs, in order of preference
| Need | Detection | Install |
|---|---|---|
| Python 3.10+ | `py -3`, `python` (ignores the Microsoft Store stub in `WindowsApps`), `%LocalAppData%\Programs\Python` | `winget install Python.Python.3.12 --scope user`, else python.org installer in silent per-user mode |
| ffmpeg + ffprobe | PATH, `~\.flow-director\bin` | `winget install Gyan.FFmpeg`, else the gyan.dev "essentials" zip copied into `~\.flow-director\bin` |
| Chrome | registry App Paths, Program Files, LocalAppData; Edge accepted | `winget install Google.Chrome` |
| Python packages | in `~\.flow-director\venv` | `pip install playwright pillow` (no browser download: we drive your Chrome over CDP) |

After any install the script refreshes PATH inside its own process, so nothing needs a terminal restart. `flow.py` also adds `~\.flow-director\bin` and the winget Links folder to its own PATH, and re-launches itself with the venv's Python, so afterwards `python scripts\flow.py ...` works with any Python 3.10+ (or use the path from the report: `~\.flow-director\venv\Scripts\python.exe`).

## The browser window
`flow.py setup` / `browser start` launches Chrome (detached) with its own profile at `%USERPROFILE%\.flow-director\profile` and a debug port on `127.0.0.1:9333`. That is a separate profile from the user's everyday Chrome, so nothing of theirs is touched, and the Google login is saved in it.

## Windows-specific problems and fixes
- **winget not found / disabled**: the script falls back to direct downloads. If the machine blocks downloads, tell the user which file to get (see the table).
- **"running scripts is disabled"**: use the `-ExecutionPolicy Bypass -File` form above.
- **A UAC prompt appears** (Chrome or Python installer wants admin): ask the user to accept it once, or use Edge, or install per-user.
- **Chrome starts but port 9333 never answers**: another Chrome is already using that profile (close it), or the port is taken (set another `port` in `config.json`), or security software blocks the loopback debug port (allow `chrome.exe` on 127.0.0.1).
- **Window minimised/locked or RDP disconnected**: Chrome throttles hidden pages and sessions that are locked can stop rendering. Keep the window visible, and keep the RDP session connected (disconnecting through "sign out" kills it; closing the RDP window keeps it).
- **`python` opens the Microsoft Store**: that is the app-execution-alias stub. Use `py -3` or the venv python from the report.
- **Paths with spaces or non-ASCII characters**: always quote paths. All files are read and written as UTF-8.
- **Fonts**: captions use `C:\Windows\Fonts\segoeui.ttf` or `arial.ttf` automatically; set `font` in config.json for another one.
- **Display scaling (125-150%)**: not an issue, clicks are made through the page's DOM, not by screen coordinates.
