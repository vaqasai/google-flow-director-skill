# Where to publish this skill

What is known, and what is not. Re-check each before relying on it.

## skills.sh (Vercel's skills directory)
- There is **no submission form**. The site ranks skills from anonymous install telemetry sent by the `skills` CLI, so a skill appears after people install it with:
  `npx skills add vaqasai/google-flow-director-skill`
- The CLI finds a `SKILL.md` in the repo root, so this repo needs nothing extra. Checked: a fresh install copies all files (SKILL.md, scripts, references, selectors.json) into `.claude/skills/google-flow-director`.
- A README badge shows the install count: `[![skills.sh](https://skills.sh/b/vaqasai/google-flow-director-skill)](https://skills.sh/vaqasai/google-flow-director-skill)` (already in the README).
- Pages: https://skills.sh/docs. Your own first installs (and a launch post linking the install command) are what get it listed; there is nothing to apply for.

## GitHub (do this first, it feeds every other directory)
- Set a repo description and topics, e.g. `agent-skill`, `claude-code`, `google-flow`, `ai-video`, `video-generation`, `codex`, `hermes-agent`, `playwright`.
- Create a release `v0.2.1` with a short changelog and, if wanted, a social preview image.

## Status (2026-10-13)

- **skills.sh**: LIVE at https://skills.sh/vaqasai/google-flow-director-skill (1 skill, installs start at 0; ranking follows install telemetry).
- **GitHub**: public, description + topics set, release `v0.2.1` cut.
- **Claude Code marketplace**: DONE. `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` added, `claude plugin validate` passes, and a live `marketplace add` + `plugin install google-flow-director@vaqasai-marketplace` (v0.2.1) was verified. Users install with:
  `/plugin install google-flow-director --marketplace vaqasai/google-flow-director-skill`
- **ComposioHQ/awesome-claude-skills**: PR open → https://github.com/ComposioHQ/awesome-claude-skills/pull/2207 (one line in Creative & Media).
- **ClawHub**: package validated (`skill publish --dry-run` → `would-publish`), but publishing needs an interactive login. Run:
  `npx -y clawhub@latest login` then
  `npx -y clawhub@latest skill publish <a folder WITHOUT .claude-plugin> --slug google-flow-director --version 0.2.1 --source-repo vaqasai/google-flow-director-skill`
  (The repo root classifies as a plugin because of `.claude-plugin/`; publish the skill files `SKILL.md README.md LICENSE selectors.json scripts references` as the skill folder.)
- **Gated (do after traction)**: travisvn/awesome-claude-skills needs 10+ GitHub stars (auto-close below that; currently 1) and human-submitted PRs; VoltAgent/awesome-agent-skills rejects brand-new skills without community usage.
- **Hermes**: the CLI recognises `.hermes/skills`; copying the folder into `~/.hermes/skills/` works today.
- **Communities**: a short demo clip plus the one-line install command is the best launch post (X, Reddit r/ClaudeAI, r/LocalLLaMA-style agent forums, Discord servers for the agents you support). Show a real result, not a promise.

## Before announcing
1. Settle the provenance question in `PROVENANCE.txt` (selector names learned from an unlicensed reference).
2. Re-run the Windows flow with v0.2.1+ and update `docs/TEST_REPORT.md`.
3. Record a 30-60 second demo of a real run.
