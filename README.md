<div align="center">

# 🎬 Google Flow Director

**Tell your AI agent what video you want. It writes the script, makes it in Google Flow with your own characters, adds captions, and hands you the finished file.**

<p>
  <img src="https://img.shields.io/badge/version-0.2.1-blue?style=flat-square" alt="Version 0.2.1">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT">
  <img src="https://img.shields.io/badge/Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square" alt="Platforms">
  <img src="https://img.shields.io/badge/Agent%20Skill-any%20agent-8A2BE2?style=flat-square" alt="Agent Skill">
  <img src="https://img.shields.io/badge/python-3.10%2B-yellow?style=flat-square" alt="Python 3.10+">
  <a href="https://skills.sh/vaqasai/google-flow-director-skill"><img src="https://skills.sh/b/vaqasai/google-flow-director-skill" alt="skills.sh installs"></a>
</p>

[What you can do](#-what-you-can-do) •
[How it works](#-how-it-works) •
[Install](#-install) •
[Examples](#-things-to-say-to-your-agent) •
[Cost and safety](#️-cost-and-safety) •
[FAQ](#-faq)

</div>

---

## 🎯 What you can do

You talk to your AI agent (Claude Code, Codex, Hermes, or any agent that can run commands). This skill gives it the know-how and the tools to make short videos with **[Google Flow](https://flow.google.com)**:

| You say | The agent does |
|---|---|
| "Make a 10 second reel about my bear stealing honey" | Writes a script with you, then drives Flow's own agent to build the storyboard and the video |
| "Use my characters Mia and Leo in the kitchen" | Attaches **one or several** of your saved Flow Characters |
| "Here's a photo of the location, use it" | Uploads your **scene or reference images** and attaches them |
| "Make her smile at the end instead" | Sends the fix in the **same Flow session**, so it keeps the context and references |
| "Add the caption 'POV: honey first, manners later'" | Resizes to 1080x1920 and burns in readable captions, placed away from faces |
| "Post it to Instagram and TikTok" | Optional: helps publish through Buffer (see [publishing](references/publishing.md)) |

You never hand over a password. You sign in to Google once, in a browser window the skill opens, and that window remembers you.

## 🧭 How it works

```
 you ──► your agent ──► this skill ──► a dedicated Chrome window ──► Google Flow
                │                         (your login is saved here)
                └──► ffmpeg ──► captioned MP4 on your disk
```

1. **Set up (once).** The agent installs what is missing (Python packages, ffmpeg, Chrome) by itself. You sign in to Google in the window that opens and open your Flow project.
2. **Plan.** It asks a few questions: which Characters, any reference images, video length and shape, captions, and how careful to be with credits.
3. **Make.** It writes the script, talks to Flow's agent, waits through the queue, and downloads the clip.
4. **Check and finish.** It looks at frames itself, adds captions, and gives you the final path.
5. **Fix.** Ask for changes in plain words. They go to the same Flow session.

## ✨ Why it is different

- **An agent playbook, not a rigid script.** If Flow's page changes or something breaks, the agent is expected to look at the page, repair the selector file and carry on. There are no hard locks to fight.
- **Windows is a first-class citizen.** One PowerShell command installs everything for the current user, with no admin rights needed in the normal case.
- **Your account, your session.** No API keys, no stored passwords. The login lives in a private browser profile on your machine.
- **Credit aware.** The agent tells you the cost before it spends (`ask` mode), or stays under a cap you set (`auto` mode).
- **Small and readable.** One helper script, one captions script, plain-text guides the agent reads when it needs them.

## 🚀 Install

### What you need
| Need | Notes |
|---|---|
| An AI agent that can run shell commands | Claude Code, Codex, Hermes, OpenCode and similar |
| A Google account with **Google Flow** access and credits | Yours. You create your own project and Characters in Flow |
| Windows 10/11, Linux or macOS | The agent installs Python packages, ffmpeg and Chrome if missing |

### 1. Add the skill
```bash
npx skills add vaqasai/google-flow-director-skill
```
Or inside Claude Code (v2.1.275+):
```
/plugin install google-flow-director --marketplace vaqasai/google-flow-director-skill
```
Or copy the folder yourself into your agent's skills folder:

| Agent | Folder |
|---|---|
| Claude Code | `~/.claude/skills/google-flow-director` |
| Codex / generic | `~/.agents/skills/google-flow-director` |
| Hermes | `~/.hermes/skills/google-flow-director` |

```bash
git clone https://github.com/vaqasai/google-flow-director-skill.git ~/.claude/skills/google-flow-director
```
> The `skills` CLI copies the whole folder (checked on Linux). If another installer leaves `scripts/` or `references/` empty (seen once on Windows), run `python scripts/flow.py doctor --repair` if `flow.py` exists, or clone the repo as above.

### 2. Tell your agent
> **"Set up the Google Flow Director skill."**

It runs the installer for your system:

| System | Command the agent runs |
|---|---|
| Windows | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1` |
| Linux / macOS | `bash scripts/bootstrap.sh` |

Then a Chrome window opens. **Sign in to Google there and open your Flow project.** That is the only manual step. On a server with no screen, see the [remote-browser notes](references/troubleshooting.md).

### 3. Make a video
> **"Make a 10 second vertical video with Mia in a kitchen, funny, with a caption."**

## 💬 Things to say to your agent

- "Set up Google Flow Director and ask me what project and characters to use."
- "Write three 10-second ideas for a Mr. Bear series, then make the best one."
- "Attach Mia and Leo and this kitchen photo, then make a storyboard first. Don't generate until I say yes."
- "The ending is too fast, redo just the last beat in the same session."
- "Add captions, strip the audio, and give me the file path."
- "Stay under 30 credits and don't ask me again unless something blocks you." (auto mode)

## 🛡️ Cost and safety

- Flow generations **cost credits** on your account. In the field test one 10-second clip cost 15 credits.
- **`ask` mode (default):** the agent states what it will make and what it costs, then waits for your yes.
- **`auto` mode:** it proceeds on its own up to your `max_credits` cap and stops if something needs a human.
- `approve` refuses to go past the cap unless you agree. These are conventions the agent follows, not a lock. Only use `auto` with a cap you are happy to spend.
- The agent **stops and tells you** on a CAPTCHA, an "unusual activity" notice, a policy block, running out of credits, or being signed out. It does not try to get around them.
- Your login stays in `~/.flow-director/profile` on your machine. Never share that folder.
- Use original characters and scenes, or ones you have rights to. Flow decides what it will generate.

## 🧰 What is inside

| Part | What it does |
|---|---|
| `SKILL.md` | The playbook your agent reads: the workflow, when to stop, how to adapt |
| `scripts/flow.py` | Helper commands: `setup`, `doctor`, `browser`, `open`, `snapshot`, `characters`, `attach`, `upload`, `send`, `wait`, `approve`, `download`, `captions`, `credits`, `inspect`, `eval` |
| `scripts/captions.py` | ffmpeg finishing: resize, caption placement, audio options |
| `scripts/bootstrap.ps1` / `.sh` | One-command installers for Windows / Linux and macOS |
| `selectors.json` | Where Flow's buttons are, in one editable file (so a UI change is a small fix) |
| `references/` | Guides the agent loads on demand: script writing, captions, publishing, Windows, troubleshooting |

Run `python scripts/flow.py --help` for every command. All commands print JSON.

## ❓ FAQ

**Do I need to code?** No. You talk to your agent. The commands are for the agent.

**Does it work on Windows?** Yes. It was field-tested on Windows 11 with PowerShell 5.1 and a real Flow account, making a captioned 1080x1920 reel.

**Will it log into my Google account for me?** No. You sign in once, yourself, in the skill's own Chrome window. It is separate from your everyday Chrome.

**Is this official?** No. It is a community skill, not affiliated with Google, Anthropic, OpenAI or Nous Research. Flow has no public API, so the skill drives the website, and the site can change. When it does, the fix is usually one line in `selectors.json`, which the agent can make.

**Which videos can I make?** Whatever Flow can make with your plan, in the shape you pick (for example 9:16 reels). Flow clips come with sound; the captions step can strip it.

**Can it post my videos?** Optionally. It can help you set up publishing with Buffer; see [`references/publishing.md`](references/publishing.md). The agent works out the details with you.

## ✅ Status

Field-tested end to end on **Windows 11 + a real Flow account** (setup, sign-in, Character, storyboard, generation, captions). Later changes (multiple characters and scenes, uploads, automatic credit tracking, smarter waiting) are checked on a mock page and read-only against the real Flow page, but not yet re-run on Windows. **Not yet verified:** macOS, uploads on real Flow. Details in [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md). Found a problem? Open an issue and include the JSON the command printed.

## 🤝 Need help with AI agents?

Custom video workflows, agent builds and consulting: **[vaqasai.in](https://vaqasai.in)**.

## 📄 Licence

[MIT](LICENSE) © 2026 [Vaqas AI](https://vaqasai.in). See [`PROVENANCE.txt`](PROVENANCE.txt) before redistributing.
