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

## Other places (unverified, check each one's current rules)
- **Claude Code plugin marketplace**: add `.claude-plugin/marketplace.json` (the `skills` CLI also reads this format) so people can add the repo as a marketplace. Not added yet.
- **"Awesome" lists** for agent skills / Claude Code skills / Hermes skills: open a PR adding one line with a link.
- **Hermes**: the CLI recognises `.hermes/skills`; copying the folder into `~/.hermes/skills/` works today.
- **Communities**: a short demo clip plus the one-line install command is the best launch post (X, Reddit r/ClaudeAI, r/LocalLLaMA-style agent forums, Discord servers for the agents you support). Show a real result, not a promise.

## Before announcing
1. Settle the provenance question in `PROVENANCE.txt` (selector names learned from an unlicensed reference).
2. Re-run the Windows flow with v0.2.1+ and update `docs/TEST_REPORT.md`.
3. Record a 30-60 second demo of a real run.
