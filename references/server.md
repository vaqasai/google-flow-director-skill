# Running on a Linux server (VPS, GCP, EC2 ...)

A cloud VM has no screen, but Chrome needs one, and the user must see it once to sign in to Google. Solution: a **virtual display** (Xvfb) with a **VNC server** that only listens on localhost, reached through an SSH tunnel. After the one-time sign-in the agent works unattended: the profile keeps the login and Chrome keeps running on the virtual screen.

## One-time setup (the agent does 1-3, the user does 4)
1. **Bootstrap** as usual: `bash scripts/bootstrap.sh` (Python, ffmpeg, Chrome). Run everything as a normal user, not root. Do not disable Chrome's sandbox.
2. **Install the display pieces** (needs root or passwordless sudo): `bash scripts/server-display.sh install`  (Xvfb, x11vnc, openbox, fonts).
3. **Start the display**: `bash scripts/server-display.sh start`. It prints the display (`:99`), the VNC address (`127.0.0.1:5900`) and where the generated password is stored. If the display or port is taken it says so and never attaches to someone else's: set `FLOW_DISPLAY_NUM` / `FLOW_VNC_PORT` to free values. It writes `~/.flow-director/display.env`, which `flow.py` reads, so `flow.py setup` / `browser start` opens Chrome on that screen with no `DISPLAY` to set.
4. **The user connects** from their own computer:
   - `ssh -L 5900:localhost:5900 <user>@<server-ip>` (GCP: `gcloud compute ssh <vm> -- -L 5900:localhost:5900`; EC2: `ssh -i key.pem -L 5900:localhost:5900 ubuntu@<ip>`)
   - open any VNC viewer at `localhost:5900`; the password is in `~/.flow-director/server/vnc-password.txt` (the user reads it; do not paste it into chat or logs).
   - sign in to Google in the Chrome window, finish any 2-step prompt, open the Flow project. Then the agent runs `setup --detect-project` and carries on.

## Rules
- **Never open the VNC port (5900) or the debug port (9333) in the cloud firewall / security group.** Both are localhost-only on purpose; the SSH tunnel is the only way in.
- Keep the VM's screen at 1440x900 or larger so Flow's layout does not collapse into the mobile view (`FLOW_SCREEN=1920x1080x24`).
- Rule of thumb: 2 vCPU and 4 GB RAM is comfortable for Chrome plus ffmpeg; 1-2 GB machines struggle.
- Check state any time: `bash scripts/server-display.sh status`; look at the screen without VNC: `DISPLAY=:99 scrot /tmp/s.png` (or `flow.py screenshot`).

## Survive reboots (optional, untested template)
`~/.config/systemd/user/flow-display.service`:
```ini
[Unit]
Description=Virtual display + VNC for Google Flow Director
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash %h/.agents/skills/google-flow-director/scripts/server-display.sh start
ExecStop=/bin/bash %h/.agents/skills/google-flow-director/scripts/server-display.sh stop
[Install]
WantedBy=default.target
```
Then `systemctl --user enable --now flow-display` and `sudo loginctl enable-linger $USER` so it starts without a login. After a reboot run `flow.py browser start` (the login is still in the profile).

## Caveats to tell the user honestly
- Google may treat a login from a datacenter IP as unusual: expect an extra verification once, which is why the user signs in through VNC themselves. If Flow later shows "unusual activity" or a CAPTCHA, stop and tell the user. Do not try to get around it, and do not install VPN/proxy tricks to hide the server.
- The profile directory holds the login. Keep the VM's disk private and the account's 2-step verification on.
- Everything the agent does on Flow still costs the user's credits; the `ask`/`auto` modes and `max_credits` apply the same as on a laptop.
