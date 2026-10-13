#!/usr/bin/env bash
# Give a headless Linux server (VPS, GCP, EC2 ...) a virtual screen you can reach over VNC.
#
#   bash scripts/server-display.sh install   # apt/dnf: xvfb, x11vnc, openbox (needs root or passwordless sudo)
#   bash scripts/server-display.sh start     # virtual display + window manager + VNC bound to localhost only
#   bash scripts/server-display.sh status
#   bash scripts/server-display.sh stop
#
# Settings (env): FLOW_DISPLAY_NUM=99  FLOW_VNC_PORT=5900  FLOW_SCREEN=1440x900x24
# flow.py reads ~/.flow-director/display.env, so Chrome opens on this display with no DISPLAY set.
# VNC listens on 127.0.0.1 only. Reach it through an SSH tunnel; never open the port to the internet.
set -u
FLOW_HOME="${FLOW_DIRECTOR_HOME:-$HOME/.flow-director}"
D="$FLOW_HOME/server"; mkdir -p "$D"
NUM="${FLOW_DISPLAY_NUM:-99}"; PORT="${FLOW_VNC_PORT:-5900}"; SCREEN="${FLOW_SCREEN:-1440x900x24}"
PASSFILE="$D/vnc-password.txt"; RFB="$D/vnc.rfb"

alive() { [ -f "$D/$1.pid" ] && kill -0 "$(cat "$D/$1.pid")" 2>/dev/null; }
sudo_cmd() { if [ "$(id -u)" = 0 ]; then "$@"; elif command -v sudo >/dev/null && sudo -n true 2>/dev/null; then sudo -n "$@"; else return 1; fi; }

case "${1:-status}" in
install)
    if command -v apt-get >/dev/null; then sudo_cmd env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq xvfb x11vnc openbox fonts-liberation fonts-noto-color-emoji xdg-utils
    elif command -v dnf >/dev/null; then sudo_cmd dnf install -y -q xorg-x11-server-Xvfb x11vnc openbox liberation-fonts
    else echo '{"ok":false,"error":"unknown package manager","hint":"install Xvfb, x11vnc and openbox yourself"}'; exit 2; fi || { echo '{"ok":false,"error":"needs root or passwordless sudo","hint":"ask the user to run: sudo apt install xvfb x11vnc openbox"}'; exit 2; }
    echo '{"ok":true}' ;;
start)
    for t in Xvfb x11vnc; do command -v $t >/dev/null || { echo "{\"ok\":false,\"error\":\"$t missing\",\"hint\":\"run: bash scripts/server-display.sh install\"}"; exit 2; }; done
    if [ ! -f "$RFB" ]; then
        umask 077
        python3 -c 'import secrets;print(secrets.token_urlsafe(9))' > "$PASSFILE"
        x11vnc -storepasswd "$(cat "$PASSFILE")" "$RFB" >/dev/null 2>&1
    fi
    if ! alive xvfb; then
        if [ -e "/tmp/.X11-unix/X$NUM" ] || [ -e "/tmp/.X$NUM-lock" ]; then
            echo "{\"ok\":false,\"error\":\"display :$NUM is already used by another program\",\"hint\":\"pick a free one: FLOW_DISPLAY_NUM=<other number> bash scripts/server-display.sh start (this script never attaches to a display it did not create)\"}"; exit 2
        fi
        setsid Xvfb ":$NUM" -screen 0 "$SCREEN" -nolisten tcp >"$D/xvfb.log" 2>&1 & echo $! > "$D/xvfb.pid"
        for _ in $(seq 40); do [ -S "/tmp/.X11-unix/X$NUM" ] && break; sleep 0.25; done
        alive xvfb || { echo '{"ok":false,"error":"Xvfb did not start","hint":"see '"$D"'/xvfb.log"}'; exit 2; }
    fi
    if command -v openbox >/dev/null && ! alive wm; then DISPLAY=":$NUM" setsid openbox >"$D/wm.log" 2>&1 & echo $! > "$D/wm.pid"; fi
    if ! alive vnc; then
        if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
            echo "{\"ok\":false,\"error\":\"port $PORT is already in use\",\"hint\":\"FLOW_VNC_PORT=<free port> bash scripts/server-display.sh start\"}"; exit 2
        fi
        setsid x11vnc -display ":$NUM" -localhost -rfbport "$PORT" -rfbauth "$RFB" -forever -shared -noxdamage -o "$D/x11vnc.log" >/dev/null 2>&1 & echo $! > "$D/vnc.pid"
        sleep 1.5; alive vnc || { echo '{"ok":false,"error":"x11vnc did not start","hint":"see '"$D"'/x11vnc.log"}'; exit 2; }
    fi
    echo "DISPLAY=:$NUM" > "$FLOW_HOME/display.env"
    echo "{\"ok\":true,\"display\":\":$NUM\",\"vnc\":\"127.0.0.1:$PORT\",\"password_file\":\"$PASSFILE\",\"connect\":\"on your own computer run: ssh -L $PORT:localhost:$PORT <user>@<server-ip>, then open a VNC viewer at localhost:$PORT and enter the password from the file (read it yourself; do not paste it into chat)\"}" ;;
stop)
    for n in vnc wm xvfb; do alive $n && kill "$(cat "$D/$n.pid")" 2>/dev/null; rm -f "$D/$n.pid"; done
    rm -f "$FLOW_HOME/display.env"; echo '{"ok":true,"stopped":true}' ;;
status)
    s() { alive "$1" && echo true || echo false; }
    echo "{\"display\":\":$NUM\",\"xvfb\":$(s xvfb),\"window_manager\":$(s wm),\"vnc\":$(s vnc),\"vnc_port\":$PORT,\"display_env\":\"$([ -f "$FLOW_HOME/display.env" ] && cat "$FLOW_HOME/display.env")\"}" ;;
*) echo "usage: server-display.sh install|start|stop|status"; exit 2 ;;
esac
