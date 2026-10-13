#!/usr/bin/env bash
# Linux/macOS bootstrap for the Google Flow Director skill. Idempotent: run it as often as you like.
#
#   bash scripts/bootstrap.sh
#
# Installs only what is missing, never asks questions, prints ONE JSON report at the end:
# items[] with found / version / installed_now / fix_if_failed, plus the python to use.
# System packages need root or passwordless sudo; without that the report says exactly what to install.
set -u

FLOW_HOME="${FLOW_DIRECTOR_HOME:-$HOME/.flow-director}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$FLOW_HOME/bin"
export PATH="$FLOW_HOME/bin:$PATH" PYTHONUTF8=1
ITEMS=()

add() { ITEMS+=("$1|$2|$3|$4|$5"); }   # item|found(1/0)|version|installed_now(1/0)|fix

if [ "$(id -u)" = "0" ]; then SUDO=""; elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then SUDO="sudo -n"; else SUDO="__none__"; fi

PM=""
for m in apt-get dnf pacman zypper brew; do command -v "$m" >/dev/null 2>&1 && { PM="$m"; break; }; done

pkg_install() {  # pkg_install <apt-name> <dnf-name> <pacman-name> <zypper-name> <brew-name>
    [ -z "$PM" ] && return 1
    if [ "$PM" != "brew" ] && [ "$SUDO" = "__none__" ]; then return 1; fi
    case "$PM" in
        apt-get) $SUDO apt-get update -qq >/dev/null 2>&1; $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $1 >/dev/null 2>&1 ;;
        dnf)     $SUDO dnf install -y -q $2 >/dev/null 2>&1 ;;
        pacman)  $SUDO pacman -S --noconfirm --needed $3 >/dev/null 2>&1 ;;
        zypper)  $SUDO zypper -n install $4 >/dev/null 2>&1 ;;
        brew)    brew install $5 >/dev/null 2>&1 ;;
    esac
}

find_python() {
    for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
            command -v "$c"; return 0
        fi
    done
    return 1
}

# ---- Python 3.10+ ---------------------------------------------------------------------------
PY="$(find_python)"; NEW=0
if [ -z "$PY" ]; then
    pkg_install "python3 python3-venv python3-pip" "python3 python3-pip" "python python-pip" "python3 python3-pip" "python" && NEW=1
    PY="$(find_python)"
fi
if [ -n "$PY" ]; then add python 1 "$("$PY" -c 'import sys;print(sys.version.split()[0])')" "$NEW" ""
else add python 0 "" 0 "Install Python 3.10+ (e.g. sudo apt install python3 python3-venv python3-pip) and re-run."; fi

# ---- ffmpeg + ffprobe -------------------------------------------------------------------------
NEW=0
if ! { command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; }; then
    pkg_install "ffmpeg" "ffmpeg-free" "ffmpeg" "ffmpeg" "ffmpeg" && NEW=1
fi
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
    add ffmpeg+ffprobe 1 "$(ffmpeg -version 2>/dev/null | head -1 | awk '{print $3}')" "$NEW" ""
else add ffmpeg+ffprobe 0 "" 0 "Install ffmpeg (sudo apt install ffmpeg | brew install ffmpeg) and re-run."; fi

# ---- Chrome / Chromium ---------------------------------------------------------------------------
find_browser() {
    for c in google-chrome google-chrome-stable chromium chromium-browser; do command -v "$c" >/dev/null 2>&1 && { command -v "$c"; return 0; }; done
    [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ] && { echo "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; return 0; }
    return 1
}
BR="$(find_browser)"; NEW=0
if [ -z "$BR" ]; then
    if [ "$PM" = "apt-get" ] && [ "$SUDO" != "__none__" ] && [ "$(uname -m)" = "x86_64" ]; then
        DEB="$(mktemp --suffix=.deb 2>/dev/null || echo /tmp/chrome.deb)"
        if command -v curl >/dev/null 2>&1 && curl -fsSL -o "$DEB" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb; then
            $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$DEB" >/dev/null 2>&1 && NEW=1
        fi
        rm -f "$DEB"
    elif [ "$PM" = "brew" ]; then
        brew install --cask google-chrome >/dev/null 2>&1 && NEW=1
    fi
    BR="$(find_browser)"
    if [ -z "$BR" ]; then pkg_install "chromium" "chromium" "chromium" "chromium" "chromium" && NEW=1; BR="$(find_browser)"; fi
fi
if [ -n "$BR" ]; then add browser 1 "$(basename "$BR")" "$NEW" ""
else add browser 0 "" 0 "Install Google Chrome (https://www.google.com/chrome/) or Chromium and re-run."; fi

# ---- private venv with playwright + pillow ----------------------------------------------------------
VENV="$FLOW_HOME/venv"; VPY="$VENV/bin/python"; DEPS=0; NEW=0
if [ -n "$PY" ]; then
    if [ ! -x "$VPY" ]; then
        "$PY" -m venv "$VENV" >/dev/null 2>&1 || { pkg_install "python3-venv" "python3" "python" "python3" "python" ; "$PY" -m venv "$VENV" >/dev/null 2>&1; }
        NEW=1
    fi
    if [ -x "$VPY" ]; then
        if ! "$VPY" -c 'import playwright, PIL' 2>/dev/null; then
            "$VPY" -m pip install --upgrade pip -q >/dev/null 2>&1
            "$VPY" -m pip install -q playwright pillow >/dev/null 2>&1; NEW=1
        fi
        "$VPY" -c 'import playwright, PIL' 2>/dev/null && DEPS=1
    fi
fi
if [ "$DEPS" = 1 ]; then add "python-deps (playwright, pillow)" 1 "" "$NEW" ""
else add "python-deps (playwright, pillow)" 0 "" 0 "python3 -m venv ~/.flow-director/venv && ~/.flow-director/venv/bin/python -m pip install playwright pillow"; fi

# ---- display (Linux only): the user must be able to SEE the browser to sign in ------------------------------
if [ "$(uname -s)" = "Linux" ]; then
    if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then add display 1 "${DISPLAY:-wayland}" 0 ""
    else add display 0 "" 0 "Headless machine: start a virtual display the user can reach (e.g. Xvfb :1 + x11vnc/TigerVNC, or noVNC), export DISPLAY=:1, then run flow.py setup. See references/troubleshooting.md."; fi
fi

REPORT_ITEMS="$(printf '%s\n' "${ITEMS[@]}")" SKILL_DIR="$SKILL_DIR" VPY="$VPY" DEPS="$DEPS" PYBIN="${PY:-python3}" \
"${PY:-python3}" - <<'PYEOF'
import json, os
items = []
for line in os.environ["REPORT_ITEMS"].splitlines():
    name, found, version, new, fix = (line.split("|", 4) + [""] * 5)[:5]
    items.append({"item": name, "found": found == "1", "version": version, "installed_now": new == "1", "fix_if_failed": fix})
flow = os.path.join(os.environ["SKILL_DIR"], "scripts", "flow.py")
vpy = os.environ["VPY"]
core = {"python", "ffmpeg+ffprobe", "browser", "python-deps (playwright, pillow)"}
print(json.dumps({
    "ok": all(i["found"] for i in items if i["item"] in core),
    "items": items,
    "python": vpy,
    "flow": flow,
    "next": f'Run: "{vpy}" "{flow}" setup   (flow.py also runs under any Python 3.10+ and re-launches itself in the venv)',
}, indent=2))
PYEOF
