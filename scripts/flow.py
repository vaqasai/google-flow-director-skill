#!/usr/bin/env python3
"""flow.py - helper CLI for driving Google Flow from any agent (Linux, Windows, macOS).

Every command prints one JSON object. Exit code 0 = ok, 2 = error (the JSON has "error" and "hint").
These are helpers, not gatekeepers: if one does not fit, use `eval`, `click`, `inspect` or your own
browser tool, and fix `selectors.json` / the config when the Flow UI changes.

Files live in ~/.flow-director (override with FLOW_DIRECTOR_HOME):
  config.json     your settings (project, characters, format, mode, credit cap ...)
  selectors.json  optional override of the skill's selectors.json (wins over it)
  profile/        the dedicated Chrome profile; the Google login lives here
  venv/           Python environment created by the bootstrap script
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path

VERSION = "0.2.1"
HOME = Path(os.environ.get("FLOW_DIRECTOR_HOME") or (Path.home() / ".flow-director"))
CONFIG_PATH = HOME / "config.json"
STATE_PATH = HOME / "state.json"
SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Tools the bootstrap script drops into ~/.flow-director/bin (and winget links) are found even in a fresh shell.
_extra_path = [str(HOME / "bin")]
if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
    _extra_path.append(str(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Links"))
os.environ["PATH"] = os.pathsep.join(_extra_path + [os.environ.get("PATH", "")])

DEFAULTS = {
    "chrome_path": None,
    "port": 9333,
    "profile_dir": str(HOME / "profile"),
    "project_url": None,
    "characters": [],
    "format": {"width": 1080, "height": 1920, "duration": 10},
    "captions": {"enabled": True, "x": 0.5, "y": "auto", "font_size": 0.045, "max_width": 0.86,
                 "start": 0.3, "end": None, "max_lines": 3},
    "font": None,
    "mode": "ask",          # "ask": confirm with the user before generating; "auto": proceed within max_credits
    "max_credits": 20,
    "strip_audio": False,   # true: captions/finish drop the audio track (Flow clips usually have sound)
    "output_dir": str(HOME / "videos"),
}


class FlowError(Exception):
    def __init__(self, message, hint=None):
        super().__init__(message)
        self.hint = hint


REQUIRED_FILES = ["SKILL.md", "selectors.json", "scripts/captions.py", "scripts/bootstrap.ps1", "scripts/bootstrap.sh",
                  "references/windows.md", "references/troubleshooting.md", "references/script-writing.md",
                  "references/captions.md"]
REPO_ZIP = "https://github.com/vaqasai/google-flow-director-skill/archive/refs/heads/main.zip"


def read_text_arg(path):
    """Read a UTF-8 file ('-' = stdin). utf-8-sig so PowerShell's BOM never leaks into messages."""
    if path == "-":
        return sys.stdin.read().lstrip("\ufeff")
    return Path(path).read_text(encoding="utf-8-sig")


def missing_files():
    return [f for f in REQUIRED_FILES if not (SKILL_DIR / f).is_file()]


def repair_install():
    """Some installers skip folders. Download the repo zip and copy only the files that are missing."""
    missing = missing_files()
    if not missing:
        return {"repaired": [], "still_missing": []}
    url = os.environ.get("FLOW_REPAIR_URL") or REPO_ZIP
    with tempfile.TemporaryDirectory(prefix="flow-repair-") as tmp:
        archive = Path(tmp) / "repo.zip"
        with urllib.request.urlopen(url, timeout=60) as response:
            archive.write_bytes(response.read())
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            root = names[0].split("/")[0] + "/"
            for member in names:
                rel = member[len(root):] if member.startswith(root) else member
                if not rel or member.endswith("/") or ".." in rel.split("/"):
                    continue
                target = SKILL_DIR / rel
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(member))
    return {"repaired": missing, "still_missing": missing_files()}


# ----------------------------------------------------------------------------- permission cards / names

APPROVE_RE = re.compile(r"^\s*(approve|confirm|allow|yes|ok|continue|generate)\b", re.I)


def parse_permission(text):
    """Pull cost / model / length out of a permission card's text. Missing pieces are None."""
    text = text or ""
    cost = re.search(r"(\d+(?:\.\d+)?)\s*credits?\b", text, re.I) or re.search(r"credits?\D{0,12}(\d+)", text, re.I)
    model = re.search(r"\b((?:Omni|Veo|Imagen|Lyria|Nano Banana)[A-Za-z]*(?:\s+[\d.]+)?(?:\s+(?:Flash|Pro|Fast|Lite|Quality))?)",
                      text)
    secs = re.search(r"(\d+)[-\s]?(?:s\b|sec\w*)", text, re.I)
    return {"cost": int(float(cost.group(1))) if cost else None,
            "model": model.group(1).strip() if model else None,
            "seconds": int(secs.group(1)) if secs else None}


def card_signature(count, text):
    return f"{count}:{hashlib.sha1((text or '').encode('utf-8')).hexdigest()[:12]}"


def apply_permission_state(raw, state):
    """Flow keeps old cards in the page. A card is pending only if it has not been handled and has an enabled button."""
    text, buttons = raw.get("permission_text") or "", raw.get("permission_buttons") or []
    sig = card_signature(raw.get("permission_count", 0), text)
    handled = sig in state.get("handled_cards", [])
    disabled = bool(buttons) and all(b.get("disabled") for b in buttons)
    pending = bool(text) and not handled and not disabled
    return {"permission": text if pending else "", "permission_buttons": [b["text"] or b.get("aria") or "" for b in buttons] if pending else [],
            "permission_info": parse_permission(text) if pending else None,
            "permission_resolved": bool(text) and not pending, "_card_sig": sig}


def video_key(url):
    return (url or "").split("?")[0]


def mark_card_handled(sig):
    state = load_state()
    state["handled_cards"] = (state.get("handled_cards", []) + [sig])[-50:]
    save_state(state)


def norm_name(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def match_name(wanted, candidates):
    """Return (candidate, how). Exact -> same ignoring case/punctuation -> close spelling. Raises FlowError with options."""
    names = list(dict.fromkeys(candidates))
    if wanted in names:
        return wanted, "exact"
    same = [n for n in names if norm_name(n) == norm_name(wanted)]
    if len(same) == 1:
        return same[0], "normalized"
    if not same:
        keys = {norm_name(n): n for n in names}
        close = difflib.get_close_matches(norm_name(wanted), list(keys), n=2, cutoff=0.6)
        if len(close) == 1 or (len(close) == 2 and
                               difflib.SequenceMatcher(None, norm_name(wanted), close[0]).ratio() -
                               difflib.SequenceMatcher(None, norm_name(wanted), close[1]).ratio() > 0.15):
            return keys[close[0]], "fuzzy"
        same = [keys[c] for c in close]
    raise FlowError(f"no unique Character matches {wanted!r}",
                    f"saved Characters seen: {names[:30]}; closest: {same}. Use `flow.py characters` and pass the exact name")


# ----------------------------------------------------------------------------- config / state

def _merge(base, extra):
    out = dict(base)
    for key, value in (extra or {}).items():
        out[key] = _merge(out[key], value) if isinstance(out.get(key), dict) and isinstance(value, dict) else value
    return out


def load_config():
    data = {}
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return _merge(DEFAULTS, data)


def save_config(cfg):
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def load_state():
    return json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"credits_used": 0}


def save_state(state):
    HOME.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def selectors():
    data = json.loads((SKILL_DIR / "selectors.json").read_text(encoding="utf-8"))
    override = HOME / "selectors.json"
    if override.exists():
        data = _merge(data, json.loads(override.read_text(encoding="utf-8")))
    return data


# ----------------------------------------------------------------------------- chrome / cdp

def find_chrome(configured=None):
    """Locate a Chromium-based browser. Chrome first, then Edge/Chromium."""
    if configured and Path(configured).exists():
        return str(configured)
    found = []
    if os.name == "nt":
        roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")]
        for root in filter(None, roots):
            found.append(Path(root) / "Google/Chrome/Application/chrome.exe")
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                        found.append(Path(winreg.QueryValue(key, None)))
                except OSError:
                    pass
        except ImportError:
            pass
        for root in filter(None, roots):
            found.append(Path(root) / "Microsoft/Edge/Application/msedge.exe")
    elif sys.platform == "darwin":
        found += [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                  Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                  Path("/Applications/Chromium.app/Contents/MacOS/Chromium")]
    for exe in found:
        if exe.exists():
            return str(exe)
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge"):
        path = shutil.which(name)
        if path:
            return path
    return None


def cdp_get(port, path, timeout=3):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as response:
        return json.loads(response.read(4_000_000))


def cdp_alive(port):
    try:
        cdp_get(port, "/json/version", timeout=1.5)
        return True
    except (OSError, ValueError):
        return False


def has_display():
    if os.name == "nt" or sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def browser_start(cfg, url=None):
    port = int(cfg["port"])
    if cdp_alive(port):
        return {"running": True, "started": False, "port": port}
    chrome = find_chrome(cfg.get("chrome_path"))
    if not chrome:
        raise FlowError("no Chrome/Edge/Chromium found",
                        "run the bootstrap script, or set chrome_path in config.json")
    profile = Path(cfg["profile_dir"])
    profile.mkdir(parents=True, exist_ok=True)
    args = [chrome, f"--remote-debugging-port={port}", f"--remote-allow-origins=http://127.0.0.1:{port}",
            f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", url or "about:blank"]
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)
    for _ in range(50):
        if cdp_alive(port):
            out = {"running": True, "started": True, "port": port, "chrome": chrome}
            if not has_display():
                out["warning"] = "no DISPLAY: the user cannot see or sign in to this window (see references/troubleshooting.md, 'headless')"
            return out
        time.sleep(0.5)
    raise FlowError(f"Chrome did not open debug port {port}",
                    "If a Chrome window already uses this profile, close it and retry; "
                    "if the port is taken, set a different `port` in config.json")


def login_state(cfg):
    """Best effort from the tab list only (no page access): signed_in | signed_out | unknown | no_browser."""
    port = int(cfg["port"])
    if not cdp_alive(port):
        return "no_browser"
    tabs = [t for t in cdp_get(port, "/json/list") if t.get("type") == "page"]
    if any("accounts.google.com" in t.get("url", "") for t in tabs):
        return "signed_out"
    if any(re.search(r"flow\.google\.com/.*project/", t.get("url", "")) for t in tabs):
        return "signed_in"
    if any("flow.google.com" in t.get("url", "") for t in tabs):
        return "unknown"
    return "unknown"


# ----------------------------------------------------------------------------- page access

@contextmanager
def browser_page(cfg, goto=True):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise FlowError("playwright is not installed in this Python",
                        "run the bootstrap script (scripts/bootstrap.ps1 or bootstrap.sh)")
    port = int(cfg["port"])
    if not cdp_alive(port):
        raise FlowError("the Flow browser is not running", "run: flow.py browser start")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        try:
            context = browser.contexts[0]
            yield _pick_page(context, cfg, goto)
        finally:
            browser.close()  # only disconnects; the real Chrome keeps running


def _project_id(url):
    match = re.search(r"project/([0-9a-fA-F-]{8,})", url or "")
    return match.group(1) if match else None


def _pick_page(context, cfg, goto):
    pid = _project_id(cfg.get("project_url"))
    pages = [p for p in context.pages if not p.url.startswith("devtools://")]
    if pid:
        for page in pages:
            if pid in page.url:
                return page
    for page in pages:
        if "flow.google.com" in page.url:
            chosen = page
            break
    else:
        chosen = pages[0] if pages else context.new_page()
    if goto and cfg.get("project_url") and (not pid or pid not in chosen.url):
        chosen.goto(cfg["project_url"], wait_until="domcontentloaded")
        try:
            chosen.wait_for_selector(selectors()["agent_panel"], timeout=15000)
        except Exception:
            pass
    return chosen


SNAPSHOT_JS = """(s) => {
  const deep = (root, css) => { const out = []; const walk = r => { out.push(...r.querySelectorAll(css)); r.querySelectorAll('*').forEach(e => { if (e.shadowRoot) walk(e.shadowRoot); }); }; if (root.shadowRoot) walk(root.shadowRoot); walk(root); return out; };
  const q = x => document.querySelector(x), qa = x => [...document.querySelectorAll(x)];
  const vis = e => !!e && e.getBoundingClientRect().width > 4 && e.getBoundingClientRect().height > 4;
  const flat = n => { let t = ''; n.childNodes.forEach(c => { if (c.nodeType === 3) t += c.textContent + ' '; else if (c.nodeType === 1) { if (c.shadowRoot) t += flat(c.shadowRoot); t += flat(c); } }); return t; };
  const cardText = c => ((c.innerText || '').trim() || (c.shadowRoot ? flat(c.shadowRoot) : '')).replace(/\\s+/g, ' ').trim().slice(0, 2000);
  const cards = qa(s.permission_card), card = cards.length ? cards[cards.length - 1] : null, composer = q(s.composer);
  const buttons = card ? deep(card, 'button, [role=button], [role=radio]').filter(vis).map(b => ({
      text: (b.getAttribute('aria-label') || b.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 40), aria: b.getAttribute('aria-label'),
      disabled: b.disabled === true || b.getAttribute('aria-disabled') === 'true' || b.classList.contains('read-only'),
      checked: b.getAttribute('aria-checked') === 'true'})) : [];
  const body = document.body ? document.body.innerText : '';
  const pct = new Set();
  deep(document, '*').forEach(e => { if (!e.children.length && /^\\d{1,3}%$/.test((e.textContent || '').trim()) && vis(e)) pct.add(parseInt(e.textContent)); });
  if (!pct.size && /generat|queue|creat/i.test(body)) { for (const m of body.matchAll(/(?<![\\d.])(\\d{1,3})%/g)) pct.add(parseInt(m[1])); }
  const progress = [...pct].filter(n => n < 100);
  const seen = new Set(), videos = [];
  qa('video').forEach(v => { const u = v.currentSrc || v.src; if (u && !seen.has(u)) { seen.add(u); videos.push({url: u, status: v.readyState >= 1 ? 'done' : 'loading'}); } });
  const bubbles = qa(s.chat_bubble), lastBubble = bubbles.length ? bubbles[bubbles.length - 1].innerText : '';
  let queued = false; try { queued = new RegExp(s.queue_patterns || 'a^', 'i').test(lastBubble); } catch (e) {}
  return {
    url: location.href, title: document.title,
    agent_panel: vis(q(s.agent_panel)), composer: vis(composer),
    composer_text: composer ? composer.innerText.trim() : '',
    chat_count: qa(s.chat_bubble).length,
    chat: qa(s.chat_bubble).slice(-12).map(e => e.innerText.slice(0, 4000)),
    permission_text: card ? cardText(card) : '', permission_count: cards.length, permission_buttons: buttons,
    dialog: (q(s.dialog) || {}).innerText || '',
    alerts: qa(s.alerts).map(e => e.innerText).join(' '),
    chips: qa(s.ingredient_chip).map(e => e.innerText),
    busy: !!q(s.busy_indicator), queued, progress, videos,
    page_text: body.slice(0, 500)
  };
}"""


def classify(snap, sel):
    """Advice only: a hint about what the page looks like. Nothing here blocks any action."""
    if "accounts.google.com" in snap["url"]:
        return "signed_out"
    text = f"{snap['dialog']} {snap['alerts']}"
    for name, pattern in sel["stop_patterns"].items():
        if re.search(pattern, text, re.I):
            return name
    if snap["permission"]:
        return "permission_card"
    if snap["agent_panel"] and snap["composer"]:
        return "ready"
    return "unknown"


def snapshot(page):
    sel = selectors()
    snap = page.evaluate(SNAPSHOT_JS, sel)
    snap.update(apply_permission_state(snap, load_state()))
    for key in ("permission_text", "permission_count"):
        snap.pop(key, None)
    snap["progress_pct"] = max(snap["progress"]) if snap["progress"] else None
    snap["videos"] = snap["videos"] + [{"url": None, "status": "generating", "progress": p} for p in snap["progress"]]
    baseline = load_state().get("baseline_videos")
    for v in snap["videos"]:
        if v["url"]:
            v["new"] = baseline is None or video_key(v["url"]) not in baseline
    fresh = [v for v in snap["videos"] if v["status"] == "done" and v.get("new")]
    loading = any(v["status"] == "loading" for v in snap["videos"])
    snap["queued"] = bool(snap["queued"]) and not fresh
    snap["generating"] = bool(snap["progress"]) or snap["queued"] or loading
    snap["job_state"] = ("generating" if snap["progress"] or loading else "queued" if snap["queued"]
                         else "done" if fresh else "idle")
    snap["status"] = classify(snap, sel)
    return snap


def click_selector(page, css, timeout=8000):
    locator = page.locator(css).first
    try:
        locator.wait_for(state="visible", timeout=timeout)
    except Exception:
        raise FlowError(f"control not found: {css}", "run `flow.py inspect`, then fix selectors.json")
    locator.scroll_into_view_if_needed()
    locator.click()


# ----------------------------------------------------------------------------- commands

def cmd_setup(args, cfg):
    changed = {}
    for key in ("project_url", "chrome_path", "mode", "max_credits", "output_dir", "port", "font"):
        value = getattr(args, key, None)
        if value is not None:
            cfg[key] = value
            changed[key] = value
    if args.characters is not None:
        cfg["characters"] = [c.strip() for c in args.characters.split(",") if c.strip()]
        changed["characters"] = cfg["characters"]
    for key in ("width", "height", "duration"):
        value = getattr(args, key)
        if value is not None:
            cfg["format"][key] = value
            changed["format." + key] = value
    if args.captions is not None:
        cfg["captions"]["enabled"] = args.captions == "on"
        changed["captions.enabled"] = cfg["captions"]["enabled"]
    if args.detect_project:
        tabs = cdp_get(int(cfg["port"]), "/json/list") if cdp_alive(int(cfg["port"])) else []
        urls = [t["url"] for t in tabs if re.search(r"flow\.google\.com/.*project/", t.get("url", ""))]
        if not urls:
            raise FlowError("no open Flow project tab found",
                            "ask the user to open their project in the Flow browser window, then retry")
        cfg["project_url"] = urls[0]
        changed["project_url"] = urls[0]
    save_config(cfg)
    Path(cfg["output_dir"]).mkdir(parents=True, exist_ok=True)
    result = {"ok": True, "config_path": str(CONFIG_PATH), "changed": changed, "config": cfg}
    if not args.no_browser:
        result["browser"] = browser_start(cfg, cfg.get("project_url") or "https://flow.google.com")
    result["login"] = login_state(cfg)
    result["doctor"] = run_doctor(cfg)
    result["next"] = _next_steps(cfg, result["login"])
    return result


def _next_steps(cfg, login):
    steps = []
    if login in ("signed_out", "unknown", "no_browser"):
        steps.append("Ask the user to sign in to Google in the Flow browser window that just opened "
                     "(the saved profile keeps the session; no password is ever stored here).")
    if not cfg.get("project_url"):
        steps.append("Ask which Flow project to use; have them open it in that window, then run `setup --detect-project`.")
    if not cfg.get("characters"):
        steps.append("Ask for the exact names of the saved Characters to use, then `setup --characters \"A,B\"`.")
    steps.append("Confirm format/length, captions on/off, mode (ask|auto) and credit cap with the user; re-run `setup` with flags.")
    return steps


def run_doctor(cfg):
    checks = []

    def add(name, ok, detail="", fix=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail), "fix": fix})

    add("python", sys.version_info >= (3, 10), sys.version.split()[0], "install Python 3.10+")
    gone = missing_files()
    add("skill_files", not gone, ", ".join(gone) or f"{len(REQUIRED_FILES)} required files present",
        "run `flow.py doctor --repair` (downloads the missing files from GitHub), or git clone the repo and copy them in")
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        add(tool, path, path or "", "run the bootstrap script")
    chrome = find_chrome(cfg.get("chrome_path"))
    add("chrome", chrome, chrome or "", "run the bootstrap script or set chrome_path")
    for module in ("playwright", "PIL"):
        try:
            __import__(module)
            add(module, True)
        except ImportError:
            add(module, False, "", "run the bootstrap script (creates ~/.flow-director/venv)")
    add("display", has_display(), os.environ.get("DISPLAY", ""), "headless: start Xvfb+VNC so the user can sign in")
    add("browser_running", cdp_alive(int(cfg["port"])), f"port {cfg['port']}", "flow.py browser start")
    add("project_configured", cfg.get("project_url"), cfg.get("project_url") or "", "flow.py setup --detect-project")
    add("characters_configured", cfg.get("characters"), ", ".join(cfg.get("characters") or []), "flow.py setup --characters A,B")
    return {"ok": all(c["ok"] for c in checks if c["name"] in ("python", "skill_files", "ffmpeg", "ffprobe", "chrome", "playwright", "PIL")),
            "checks": checks}


def cmd_doctor(args, cfg):
    repaired = repair_install() if args.repair else None
    result = run_doctor(cfg)
    if repaired:
        result["repair"] = repaired
    return result


def cmd_browser(args, cfg):
    port = int(cfg["port"])
    if args.action == "start":
        return browser_start(cfg, args.url or cfg.get("project_url") or "https://flow.google.com")
    if args.action == "status":
        alive = cdp_alive(port)
        tabs = [{"url": t["url"], "title": t.get("title")} for t in cdp_get(port, "/json/list") if t.get("type") == "page"] if alive else []
        return {"running": alive, "port": port, "login": login_state(cfg), "tabs": tabs}
    if not cdp_alive(port):
        return {"running": False}
    with browser_page(cfg, goto=False) as page:
        page.context.browser.new_browser_cdp_session().send("Browser.close")
    return {"running": False, "stopped": True}


def cmd_open(args, cfg):
    url = args.url or cfg.get("project_url") or "https://flow.google.com/"
    with browser_page(cfg, goto=False) as page:
        page.goto(url, wait_until="domcontentloaded")
        try:
            page.wait_for_selector(selectors()["agent_panel"], timeout=15000)
        except Exception:
            pass
        snap = snapshot(page)
        out = {"ok": True, "snapshot": snap}
        if snap["status"] == "unknown" and not cfg.get("project_url"):
            out["status_hint"] = ("needs_login_or_project: sign in to Google in this window, create/open a Flow project, "
                                  "then run `flow.py setup --detect-project` (Flow redirects to /about when signed out)")
        return out


def cmd_snapshot(args, cfg):
    with browser_page(cfg) as page:
        return snapshot(page)


INSPECT_JS = """() => {
  const deep = (root, css) => { const out = []; const walk = r => { out.push(...r.querySelectorAll(css)); r.querySelectorAll('*').forEach(e => { if (e.shadowRoot) walk(e.shadowRoot); }); }; if (root.shadowRoot) walk(root.shadowRoot); walk(root); return out; };
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 4 && r.height > 4; };
  const sel = 'button, [role=button], a[href], input, textarea, select, [contenteditable=true], [role=menuitem], [role=tab], [role=option], [role=radio]';
  return deep(document, sel).filter(vis).slice(0, 250).map(e => ({
    tag: e.tagName.toLowerCase(), aria: e.getAttribute('aria-label'),
    text: (e.innerText || e.value || '').trim().replace(/\\s+/g, ' ').slice(0, 70),
    role: e.getAttribute('role'), parent: e.parentElement ? e.parentElement.tagName.toLowerCase() : null
  }));
}"""


def cmd_inspect(args, cfg):
    with browser_page(cfg) as page:
        items = page.evaluate(INSPECT_JS)
        if args.filter:
            pattern = re.compile(args.filter, re.I)
            items = [i for i in items if pattern.search(f"{i['aria']} {i['text']} {i['tag']}")]
        return {"url": page.url, "count": len(items), "elements": items}


def cmd_new_session(args, cfg):
    sel = selectors()
    with browser_page(cfg) as page:
        click_selector(page, sel["new_session_button"])
        time.sleep(1)
        return {"ok": True, "snapshot": snapshot(page)}


def _chip_has(chips, name):
    return any(norm_name(c.split("\n")[0]) == norm_name(name) and "Character" in c for c in chips)


LIST_TILES_JS = """(sel) => [...document.querySelectorAll(sel)]
  .map((e, i) => ({i, l: e.innerText.split('\\n').map(x => x.trim()).filter(Boolean)}))
  .filter(x => x.l.length > 1 && x.l[x.l.length - 1] === 'Character').map(x => ({i: x.i, name: x.l[0]}))"""


def _open_add_menu(page, sel):
    click_selector(page, sel["add_ingredients_button"])
    search = page.locator(sel["add_menu_search"]).first
    search.wait_for(state="visible", timeout=8000)
    search.click()
    return search


def _menu_tiles(page, sel, search, terms):
    """Try each search term until the menu shows Character tiles. Returns the tile list."""
    for term in terms:
        search.fill(term)
        time.sleep(0.8)
        tiles = page.evaluate(LIST_TILES_JS, sel["add_menu_item"])
        if tiles:
            return tiles
    return []


def cmd_characters(args, cfg):
    sel = selectors()
    with browser_page(cfg) as page:
        search = _open_add_menu(page, sel)
        tiles = _menu_tiles(page, sel, search, [args.query or ""])
        page.keyboard.press("Escape")
    names = [t["name"] for t in tiles]
    return {"ok": True, "count": len(names), "characters": names, "configured": cfg.get("characters"),
            "note": "names are shown exactly as saved; `attach` also accepts close spellings"}


def cmd_attach(args, cfg):
    sel = selectors()
    from_config = not args.names
    names = args.names.split(",") if args.names else cfg.get("characters")
    names = [n.strip() for n in names if n.strip()]
    if not names:
        raise FlowError("no Character names", "pass --names \"A,B\" or set them with `setup --characters`")
    results, renamed = [], {}
    with browser_page(cfg) as page:
        for name in names:
            chips = snapshot(page)["chips"]
            if _chip_has(chips, name):
                results.append({"name": name, "status": "already_attached"})
                continue
            search = _open_add_menu(page, sel)
            words = sorted(re.findall(r"[A-Za-z0-9]+", name), key=len, reverse=True)
            tiles = _menu_tiles(page, sel, search, [name] + words[:1] + [""])
            if not tiles:
                page.keyboard.press("Escape")
                raise FlowError(f"no Character tiles visible while looking for {name!r}",
                                "run `flow.py characters`; make sure the Character exists in this project")
            try:
                matched, how = match_name(name, [t["name"] for t in tiles])
            except FlowError:
                page.keyboard.press("Escape")
                raise
            tile = next(t for t in tiles if t["name"] == matched)
            page.locator(sel["add_menu_item"]).nth(tile["i"]).click()
            add = page.locator(sel["add_to_prompt_button"])
            time.sleep(0.4)
            if add.count():
                add.first.click()
            time.sleep(0.8)
            after = snapshot(page)["chips"]
            entry = {"name": name, "status": "attached" if len(after) > len(chips) else "uncertain", "chips": after}
            if how != "exact":
                entry["matched_as"] = matched
                renamed[name] = matched
            results.append(entry)
    if renamed and from_config:
        cfg["characters"] = [renamed.get(n, n) for n in cfg["characters"]]
        save_config(cfg)
    return {"ok": all(r["status"] != "uncertain" for r in results), "results": results,
            **({"config_updated": renamed} if renamed and from_config else {})}


def cmd_send(args, cfg):
    sel = selectors()
    text = read_text_arg(args.file) if args.file else args.message
    if not text or not text.strip():
        raise FlowError("empty message", "pass a message or --file")
    with browser_page(cfg) as page:
        before = snapshot(page)
        if before["status"] in ("signed_out", "challenge"):
            raise FlowError(f"page status is {before['status']}", "ask the user to fix it in the browser window")
        composer = page.locator(sel["composer"]).first
        composer.wait_for(state="visible", timeout=10000)
        if before["composer_text"] and not args.replace:
            raise FlowError("the composer already has text", "use --replace to overwrite it")
        composer.click()
        if args.replace:
            page.keyboard.press("ControlOrMeta+a")
            page.keyboard.press("Backspace")
        if args.slow:
            page.keyboard.type(text, delay=8)
        else:
            page.keyboard.insert_text(text)
        time.sleep(0.4)
        typed = snapshot(page)["composer_text"]
        if " ".join(typed.split()) != " ".join(text.split()):
            raise FlowError("composer text differs from the message",
                            "retry with --slow or --replace; composer currently has: " + typed[:200])
        if args.no_submit:
            return {"ok": True, "submitted": False, "composer_text": typed}
        click_selector(page, sel["send_button"])
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            time.sleep(0.5)
            now = snapshot(page)
            if now["chat_count"] > before["chat_count"] or (not now["composer_text"] and now["busy"]):
                return {"ok": True, "submitted": True, "snapshot": now}
        raise FlowError("message may not have been sent",
                        "run `snapshot` to check the chat before re-sending (avoid duplicates and double spend)")


def cmd_wait(args, cfg):
    """Poll until Flow needs you (permission card / stop condition), or generation finishes, or the timeout."""
    sel = selectors()
    started = time.monotonic()
    deadline = started + args.timeout
    last, stable, seen_generating = None, 0, False
    with browser_page(cfg) as page:
        while True:
            snap = snapshot(page)
            seen_generating = seen_generating or snap["generating"]
            ready = [v for v in snap["videos"] if v["status"] == "done"]
            signature = json.dumps([snap["chat_count"], snap["chat"][-2:], snap["permission"], snap["videos"]])
            quiet = signature == last and not snap["busy"] and not snap["generating"]
            stable = stable + 1 if quiet else 0
            last = signature
            status = snap["status"]
            info = {"elapsed": round(time.monotonic() - started), "job_state": snap["job_state"],
                    "progress_pct": snap["progress_pct"], "snapshot": snap}
            if snap["permission"]:
                return {"status": "permission_card", **(snap["permission_info"] or {}),
                        "buttons": snap["permission_buttons"], **info,
                        "next": "decide per mode, then `flow.py approve` (or `click --text Reject`)"}
            if status in sel["stop_patterns"] or status == "signed_out":
                return {"status": status, **info}
            if args.videos and len(ready) >= args.videos and not snap["generating"]:
                return {"status": "done", "videos_ready": len(ready), **info}
            if not args.videos and stable >= args.stable:
                return {"status": "done" if seen_generating and ready else "settled", **info}
            if time.monotonic() >= deadline:
                return {"status": "timeout", **info,
                        "next": "still working: run `wait` again (queues can take several minutes); "
                                "download as soon as a video is done, its signed URL expires"}
            time.sleep(args.poll)


def _spend(cfg, label, info, card_sig, baseline=None):
    """Record a handled card; add its cost to the credit counter when the button was an approval."""
    mark_card_handled(card_sig)
    if label and APPROVE_RE.search(label) and baseline is not None:
        state = load_state()
        state["baseline_videos"] = sorted({video_key(u) for u in baseline})
        save_state(state)
    if label and APPROVE_RE.search(label) and info and info.get("cost"):
        state = load_state()
        state["credits_used"] = state.get("credits_used", 0) + info["cost"]
        save_state(state)
        return {"added": info["cost"], "used": state["credits_used"], "remaining": cfg["max_credits"] - state["credits_used"]}
    return None


def cmd_approve(args, cfg):
    """Press the approval button on the pending permission card and track its credit cost."""
    sel = selectors()
    with browser_page(cfg) as page:
        raw = page.evaluate(SNAPSHOT_JS, sel)
        card = apply_permission_state(raw, load_state())
        if not card["permission"]:
            raise FlowError("no pending permission card", "run `snapshot`; if a card is visible, `click --text <label>`")
        info = card["permission_info"]
        used = load_state().get("credits_used", 0)
        if info["cost"] and used + info["cost"] > cfg["max_credits"] and not args.over_cap:
            raise FlowError(f"cost {info['cost']} would exceed the credit cap ({used} used of {cfg['max_credits']})",
                            "tell the user; if they agree, raise it with `setup --max-credits N` or pass --over-cap")
        label = args.text or next((b for b in card["permission_buttons"] if re.fullmatch(r"\s*approve\s*", b, re.I)), None) \
            or next((b for b in card["permission_buttons"] if APPROVE_RE.search(b)), "Approve")
        pattern = re.compile(r"^\s*" + re.escape(label) + r"\s*$", re.I)
        scope = page.locator(sel["permission_card"]).last
        target = scope.get_by_role("radio", name=pattern)
        if not target.count():
            target = scope.get_by_role("button", name=pattern)
        if not target.count():
            target = page.get_by_role("button", name=pattern)
        if not target.count():
            raise FlowError(f"button {label!r} not found", f"buttons seen: {card['permission_buttons']}")
        target.first.click()
        credits = _spend(cfg, label, info, card["_card_sig"], [v["url"] for v in raw["videos"]])
        time.sleep(args.wait)
        return {"ok": True, "approved": label, **info, "credits": credits, "snapshot": snapshot(page)}


def cmd_click(args, cfg):
    sel = selectors()
    with browser_page(cfg) as page:
        raw = page.evaluate(SNAPSHOT_JS, sel)
        card = apply_permission_state(raw, load_state())
        if args.selector:
            click_selector(page, args.selector)
        elif args.text:
            pattern = re.compile(args.text, re.I)
            target = page.get_by_role("button", name=pattern)
            if not target.count():
                target = page.get_by_role("radio", name=pattern)
            if not target.count():
                target = page.get_by_text(pattern)
            if not target.count():
                raise FlowError(f"nothing matches {args.text!r}", "run `inspect --filter` to find the label")
            target.first.click()
        else:
            raise FlowError("give --selector or --text")
        credits = None
        if card["permission"] and args.text and any(re.search(args.text, b, re.I) for b in card["permission_buttons"]):
            label = next(b for b in card["permission_buttons"] if re.search(args.text, b, re.I))
            credits = _spend(cfg, label, card["permission_info"], card["_card_sig"], [v["url"] for v in raw["videos"]])
        time.sleep(args.wait)
        out = {"ok": True, "snapshot": snapshot(page)}
        if credits:
            out["credits"] = credits
        return out


def cmd_eval(args, cfg):
    expression = read_text_arg(args.file) if args.file else args.js
    with browser_page(cfg) as page:
        return {"ok": True, "result": page.evaluate(expression)}


def cmd_screenshot(args, cfg):
    path = Path(args.out) if args.out else HOME / "shots" / f"{int(time.time())}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    with browser_page(cfg) as page:
        page.screenshot(path=str(path))
    return {"ok": True, "path": str(path)}


def cmd_download(args, cfg):
    sel = selectors()
    out_dir = Path(args.out or Path(cfg["output_dir"]) / "downloads")
    out_dir.mkdir(parents=True, exist_ok=True)
    with browser_page(cfg) as page:
        if args.video_url:  # direct fetch using the page's own login cookies
            response = page.request.get(args.video_url)
            if not response.ok:
                raise FlowError(f"download failed with HTTP {response.status}")
            name = args.name or f"flow-{int(time.time())}.mp4"
            target = out_dir / name
            target.write_bytes(response.body())
            return {"ok": True, "path": str(target), "bytes": target.stat().st_size}
        try:
            with page.expect_download(timeout=args.timeout * 1000) as info:
                if not args.no_click:
                    click_selector(page, args.selector or sel["download_button"])
            download = info.value
        except FlowError:
            raise
        except Exception:
            menu = page.evaluate(INSPECT_JS)[:60]
            raise FlowError("no download started",
                            "a menu (e.g. resolution) may need a click: use `click --text ...` then "
                            "`download --no-click`; or pass --video-url from `snapshot` videos. "
                            f"Visible controls: {json.dumps(menu)[:1500]}")
        target = out_dir / (args.name or download.suggested_filename)
        download.save_as(str(target))
        return {"ok": True, "path": str(target), "bytes": target.stat().st_size}


def cmd_credits(args, cfg):
    state = load_state()
    if args.reset:
        state["credits_used"] = 0
    if args.add:
        state["credits_used"] = state.get("credits_used", 0) + args.add
    save_state(state)
    used, cap = state["credits_used"], cfg["max_credits"]
    return {"used": used, "max": cap, "remaining": cap - used, "mode": cfg["mode"],
            "note": "`approve` adds each card's cost automatically; use --add only for spend it did not see"}


def cmd_captions(args, cfg):
    import captions
    fmt = cfg["format"]
    layout = {k: v for k, v in cfg["captions"].items() if k != "enabled"}
    for key in ("x", "font_size", "start", "end"):
        value = getattr(args, key, None)
        if value is not None:
            layout[key] = value
    if args.y is not None:
        layout["y"] = args.y if args.y == "auto" else float(args.y)
    text = read_text_arg(args.text_file) if args.text_file else args.text
    out = Path(args.out) if args.out else Path(cfg["output_dir"]) / (Path(args.video).stem + "-final.mp4")
    return {"ok": True, **captions.finish(args.video, out, args.width or fmt["width"], args.height or fmt["height"],
                                          caption=text, layout=layout, font=cfg.get("font"),
                                          trim=args.trim if args.trim else None,
                                          strip_audio=True if args.strip_audio else (False if args.keep_audio else cfg.get("strip_audio", False)))}


def cmd_probe(args, cfg):
    import captions
    return {"ok": True, **captions.probe(args.video)}


# ----------------------------------------------------------------------------- main

def build_parser():
    p = argparse.ArgumentParser(prog="flow.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("setup", help="save settings, open the Flow browser, report what is still needed (safe to re-run)")
    s.add_argument("--project-url"); s.add_argument("--detect-project", action="store_true")
    s.add_argument("--characters", help="comma-separated exact saved Character names")
    s.add_argument("--width", type=int); s.add_argument("--height", type=int); s.add_argument("--duration", type=float)
    s.add_argument("--captions", choices=["on", "off"]); s.add_argument("--mode", choices=["ask", "auto"])
    s.add_argument("--max-credits", type=int); s.add_argument("--output-dir"); s.add_argument("--chrome-path")
    s.add_argument("--port", type=int); s.add_argument("--font"); s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_setup)

    s = sub.add_parser("doctor", help="check dependencies, config and that all skill files are installed")
    s.add_argument("--repair", action="store_true", help="download any missing skill files from GitHub"); s.set_defaults(fn=cmd_doctor)
    s = sub.add_parser("browser", help="start | status | stop the dedicated Flow browser")
    s.add_argument("action", choices=["start", "status", "stop"]); s.add_argument("--url"); s.set_defaults(fn=cmd_browser)
    s = sub.add_parser("open", help="navigate to the project (or --url)"); s.add_argument("--url"); s.set_defaults(fn=cmd_open)
    sub.add_parser("snapshot", help="current Flow page state as JSON (chat, composer, permission card, videos)").set_defaults(fn=cmd_snapshot)
    s = sub.add_parser("inspect", help="list visible buttons/inputs so you can adapt selectors"); s.add_argument("--filter"); s.set_defaults(fn=cmd_inspect)
    sub.add_parser("new-session", help="start a fresh Flow agent session").set_defaults(fn=cmd_new_session)
    s = sub.add_parser("characters", help="list the saved Character names exactly as Flow shows them"); s.add_argument("--query"); s.set_defaults(fn=cmd_characters)
    s = sub.add_parser("attach", help="attach saved Characters (case/punctuation/spelling tolerant)"); s.add_argument("--names"); s.set_defaults(fn=cmd_attach)
    s = sub.add_parser("send", help="type a message into the Flow agent composer and send it")
    s.add_argument("message", nargs="?"); s.add_argument("--file", help="UTF-8 file, or - for stdin"); s.add_argument("--replace", action="store_true")
    s.add_argument("--slow", action="store_true"); s.add_argument("--no-submit", action="store_true")
    s.add_argument("--timeout", type=int, default=15); s.set_defaults(fn=cmd_send)
    s = sub.add_parser("wait", help="wait for Flow to finish, show a permission card, or hit a stop condition")
    s.add_argument("--timeout", type=int, default=300); s.add_argument("--stable", type=int, default=4)
    s.add_argument("--poll", type=float, default=3, help="seconds between checks"); s.add_argument("--videos", type=int, help="wait until N videos are done")
    s.set_defaults(fn=cmd_wait)
    s = sub.add_parser("approve", help="press Approve on the pending permission card; tracks its credit cost")
    s.add_argument("--text", help="button label if not Approve"); s.add_argument("--over-cap", action="store_true", help="user agreed to exceed max_credits")
    s.add_argument("--wait", type=float, default=1.5); s.set_defaults(fn=cmd_approve)
    s = sub.add_parser("click", help="click by --selector or visible --text (regex)")
    s.add_argument("--selector"); s.add_argument("--text"); s.add_argument("--wait", type=float, default=1.0); s.set_defaults(fn=cmd_click)
    s = sub.add_parser("eval", help="run JavaScript on the page and print the result"); s.add_argument("js", nargs="?"); s.add_argument("--file"); s.set_defaults(fn=cmd_eval)
    s = sub.add_parser("screenshot", help="save a PNG of the page"); s.add_argument("--out"); s.set_defaults(fn=cmd_screenshot)
    s = sub.add_parser("download", help="download a generated video (button click, or --video-url)")
    s.add_argument("--out"); s.add_argument("--name"); s.add_argument("--selector"); s.add_argument("--video-url")
    s.add_argument("--no-click", action="store_true"); s.add_argument("--timeout", type=int, default=60); s.set_defaults(fn=cmd_download)
    s = sub.add_parser("credits", help="track credits used against max_credits"); s.add_argument("--add", type=int); s.add_argument("--reset", action="store_true"); s.set_defaults(fn=cmd_credits)
    s = sub.add_parser("captions", help="scale/pad to the target format and burn in an optional caption")
    s.add_argument("video"); s.add_argument("--text"); s.add_argument("--text-file"); s.add_argument("--out")
    s.add_argument("--width", type=int); s.add_argument("--height", type=int); s.add_argument("--trim", type=float)
    s.add_argument("--x", type=float); s.add_argument("--y", help="fraction of height, or auto"); s.add_argument("--font-size", dest="font_size", type=float)
    s.add_argument("--start", type=float); s.add_argument("--end", type=float)
    s.add_argument("--strip-audio", action="store_true"); s.add_argument("--keep-audio", action="store_true"); s.set_defaults(fn=cmd_captions)
    s = sub.add_parser("probe", help="ffprobe width/height/duration/audio"); s.add_argument("video"); s.set_defaults(fn=cmd_probe)
    return p


def _reexec_in_venv():
    """If the bootstrap venv exists and we are not in it, run this script with the venv's Python."""
    venv = HOME / "venv"
    exe = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if exe.exists() and Path(sys.prefix).resolve() != venv.resolve() and not os.environ.get("FLOW_NO_REEXEC"):
        env = dict(os.environ, FLOW_NO_REEXEC="1")
        sys.exit(subprocess.call([str(exe), str(Path(__file__).resolve()), *sys.argv[1:]], env=env))


def main(argv=None):
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    _reexec_in_venv()
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config()
        result = args.fn(args, cfg)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except FlowError as error:
        print(json.dumps({"ok": False, "error": str(error), "hint": error.hint}, indent=2, ensure_ascii=False))
        return 2
    except Exception as error:  # keep the JSON contract; the agent decides what to do
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}",
                          "hint": "unexpected failure; run `doctor`, `snapshot`, `inspect`, and see references/troubleshooting.md"},
                         indent=2, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
