# Google Flow Director Skill

Published by **[vaqasai.in](https://vaqasai.in)**. Community skill, not affiliated with Google.

An Agent Skill that lets any coding/automation agent make short videos with Google Flow: it sets itself up, helps you write the script, drives Flow's built-in agent in a browser session you signed in to once, downloads the clips and adds captions. Works on **Windows, Linux and macOS** with any agent that can run shell commands (Claude Code, Codex, Hermes, others).

## Install
```bash
npx skills add vaqasai/google-flow-director-skill
```
(or clone this repo into your agent's skills folder). Then tell your agent: *"set up the Google Flow Director skill"*. It will:

1. run the bootstrap script, which installs anything missing (Python packages in a private venv, ffmpeg, Chrome) on Windows (`scripts/bootstrap.ps1`) or Linux/macOS (`scripts/bootstrap.sh`);
2. ask you which Flow project, which saved Characters, video format/length, captions, `ask`/`auto` mode and credit cap;
3. open a dedicated Chrome window. **You sign in to Google there once**; the browser profile keeps the session. No password is stored anywhere.

After that: *"make a 10 second video about ..."*.

## What you do yourself
Sign in to Google, create your Flow project and your saved Characters (original or rights-cleared), and have Flow credits. On a headless server you need a way to see the browser once (VNC / remote desktop); see `references/troubleshooting.md`.

## Modes
- `ask` (default): the agent tells you what it is about to generate and the cost, and waits for your yes.
- `auto`: the agent proceeds on its own within your `max_credits` and stops when something needs a human (CAPTCHA, policy block, out of credits, signed out).

These are conventions the agent follows, not hard locks: the agent can adapt, fix selectors and recover from errors. Only enable `auto` with a credit cap you are comfortable spending.

## Layout
`SKILL.md` workflow · `scripts/flow.py` helper CLI · `scripts/captions.py` ffmpeg finishing · `scripts/bootstrap.*` installers · `selectors.json` Flow UI selectors (agent-editable) · `references/` script writing, captions, Windows, troubleshooting · `tests/` offline tests (`python -m unittest discover -s tests`).

## Status
v0.2.1. Field-tested end to end on **Windows 11 + PowerShell 5.1 with a real Flow account** (bootstrap, sign-in, Character, storyboard, 15-credit generation, captions). The fixes made after that run (permission card handling, `approve`, polling `wait`, `characters`, auto caption placement) are verified offline only; see `docs/TEST_REPORT.md`. Not yet verified: macOS, Linux with a real account. Flow has no public API and its UI changes; selectors live in one file for that reason.

## Need help with AI agents?
For consulting, custom video workflows or AI agent builds: **[hire us at vaqasai.in](https://vaqasai.in)**.

## Licence
Fully open source under the **[MIT License](LICENSE)**: use it, change it, sell things made with it, no restrictions beyond keeping the copyright notice. Copyright (c) 2026 Vaqas AI ([vaqasai.in](https://vaqasai.in)). Not affiliated with Google, Anthropic, OpenAI or Nous Research. See `PROVENANCE.txt` before redistributing.
