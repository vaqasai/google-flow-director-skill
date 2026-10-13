# Test report (v0.2.1)

Status words: TESTED (ran and passed), PARTIAL, UNTESTED.

## Field test, Windows 11 + PowerShell 5.1, real Flow account (2026-10-13, reported by the owner, run by an agent)
Result: end-to-end success. 10s 9:16 cartoon with a saved Character, 15 credits (Omni 1.1 Flash), captioned 1080x1920 file verified from 3 frames.

| Area | Status | Notes |
|---|---|---|
| `bootstrap.ps1` (Python 3.14 venv, ffmpeg 8.1.1 via winget, Chrome, playwright, pillow) | TESTED on Windows 11 | all 5 items found, JSON `ok: true` |
| `flow.py` on Windows: setup, browser start, open, snapshot, new-session, attach, send, wait, click, download `--video-url`, probe, captions | TESTED on Windows 11, real Flow | login persists in the profile |
| Real Flow site: agent panel, composer, permission card, queue, signed video URL | TESTED | queue under high demand took ~2 minutes |
| `npx skills add` full tree | FAILED once: `scripts/`, `references/`, `tests/` were empty | added `doctor` check `skill_files` and `doctor --repair` |
| Unit tests | 15/16 on Windows | the failing one assumed no browser on the port; the machine had the real Flow browser running. Fixed: test picks a free port |

## v0.2.1 changes made from that test (offline-verified on Linux, not yet re-run on Windows)
| Change | Verified how |
|---|---|
| Permission card: buttons found inside shadow DOM (`inspect`, `snapshot`); cost/model/seconds parsed; card cleared once handled (stale `permission_card` fixed) | unit tests + mock page with a shadow-DOM card |
| `approve` command: presses Approve, adds cost to the counter automatically, refuses over `max_credits` unless `--over-cap` | mock page (cap refusal, credits 15/20) |
| `wait` polls through queue/generating (`job_state`, `progress_pct`, `videos[].status`), `--videos N`, `--poll`; "high demand" is no longer a stop condition | mock page (generating 3%) |
| `characters` command; `attach` tolerant of case/punctuation/spelling, saves the real name back to config | mock page (`mr bear` -> `Mr. bear`) + unit tests |
| `send/captions/eval --file -` (stdin) and UTF-8 BOM ignored; PowerShell examples in `references/windows.md` | unit test |
| Captions: `y: auto` (calmest band, away from faces), `--strip-audio/--keep-audio`, `audio_stripped` in output | unit test on a synthetic clip; face avoidance is a heuristic, not checked on real faces |
| `open` hint when signed out / no project | code only |

## Linux, real Flow account, read-only (2026-10-13, existing shared VNC Chrome on CDP 9224)
Attached `flow.py` to the running Flow browser without navigating or sending anything.
| Result | Detail |
|---|---|
| `snapshot`, `inspect`, `eval`, `screenshot`, `characters`, `wait` | TESTED: `characters` returned `["V","Popo"]` and the add menu closed cleanly |
| Real permission card DOM | options are `div[role=radio]` (Approve / Always approve / Reject), not buttons; once handled they are `read-only` + `aria-disabled`. Handling now matches this; an old card reads as resolved |
| Queue text | "waiting in the queue due to high demand" stays in chat history; `queued` now looks at the last message only and ignores videos that existed before approval |
| Not exercised on the real site | `send`, `approve`, `attach`, generation (spends credits; needs the owner's go-ahead) |

## Multiple characters, scene references, upload (2026-10-13)
| Item | Status |
|---|---|
| `attach` with several names (`mr bear, leo`), kind-aware matching | TESTED on mock page |
| `characters --kind all` lists Character/Image/Video tiles | TESTED on the real Flow page (read-only) |
| Attaching a Scene tile on real Flow | UNTESTED (the tile label for Scenes is not confirmed; attach falls back to searching all kinds) |
| `upload` (file input or add-media menu) | UNTESTED on real Flow; on the mock it fails with a clear message |

## Installer check (2026-10-13, Linux)
`npx skills add vaqasai/google-flow-director-skill -a claude-code` into an empty folder copied all 16 files including `scripts/` and `references/`. The empty-folder install seen on Windows came from the agent's own installer, not from the `skills` CLI; `doctor --repair` covers it.

## Still UNTESTED
- Windows re-run of v0.2.1 (all of the above), PowerShell 7, machines without winget, non-admin user.
- macOS. Linux with a real Flow account (headless VNC sign-in).
- `doctor --repair` against the real GitHub zip (tested with a local zip).
- `auto` caption placement on real faces (Flow clips).
