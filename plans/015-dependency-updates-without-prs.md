# Plan 015: Dependency updates without pull requests

**Status:** TODO (planned 2026-09-23). Needs an owner decision (see
Options) before any work.

## Problem

Pull requests are disabled on this repo on purpose (sole contributor;
`gh api repos/fzachman/ScenicSoundManager` → `has_pull_requests: false`).
`.github/dependabot.yml` (added 2026-06-25) configures weekly version updates
for pip and GitHub Actions, and repo settings have Dependabot **security
updates** enabled — both work by opening PRs, so neither can deliver
anything now. Updates stopped silently:

- The last Dependabot branches are from 2026-07-24. Two stale ones remain on
  the remote: `dependabot/pip/python-deps-1988f90e20` and
  `dependabot/github_actions/github-actions-e91bde37dc`.
- Snapshot 2026-09-23, pinned (`requirements.txt`) vs latest:

  | Package | Pinned | Latest |
  |---|---|---|
  | PyQt6 | 6.10.2 | 6.11.0 |
  | mutagen | 1.47.0 | 1.48.1 |
  | structlog | 25.5.0 | 26.1.0 (major) |
  | py2app | 0.28.9 | 0.28.10 |
  | pytest | 9.0.3 | 9.1.1 |
  | ruff | 0.15.20 | 0.16.8 |
  | mypy | 2.1.0 | 2.3.1 |
  | python-vlc, pyinstaller | current | — |

  Actions: `actions/checkout@v5` (latest v7), `actions/setup-python@v6`
  (latest v7), `actions/upload-artifact@v7` (current).

Dependabot **alerts** (security advisories in the Security tab) do not need
PRs and keep working; only the update PRs are dead.

## Options (owner picks)

- **A. Local check, manual bumps.** A `scripts/check_outdated.py` (PyPI JSON
  for every `==` pin in `requirements.txt`, honoring the platform markers;
  GitHub releases API for each `uses:` action's latest major) behind a
  `just outdated` recipe. Bump on a `fix/` branch; CI on push validates.
  Simplest, but only happens when remembered.
- **B. Weekly reminder issue (recommended).** The same script in a scheduled
  workflow (`schedule:` weekly + `workflow_dispatch`, `permissions: issues:
  write`) that creates or updates ONE open issue ("Outdated dependencies")
  listing what is behind, and closes it when nothing is. Issues are enabled
  and email the owner, which restores Dependabot's nudge without PRs. Keep
  `just outdated` from A for local use.
- **C. Re-enable PRs for bots only.** The repo already has
  `pull_request_creation_policy: collaborators_only`; check whether
  Dependabot counts. Least preferred: the owner wants PRs off.

## Steps (for B; A is steps 1–2 only)

1. Write `scripts/check_outdated.py`: parse `requirements.txt` pins; query
   `https://pypi.org/pypi/<name>/json` for the latest version; parse
   `uses: owner/action@vN` from `.github/workflows/*.yml` and query
   `repos/<owner>/<action>/releases/latest`. Print a table; exit 0 either
   way (it reports, it doesn't gate). Flag major bumps separately.
2. Add `just outdated`.
3. Add `.github/workflows/outdated.yml`: weekly schedule + dispatch, runs the
   script, then `gh issue` create/edit/close by a fixed title (use the
   workflow's `GITHUB_TOKEN`; no extra secrets).
4. Remove the version-update entries from `.github/dependabot.yml` (or the
   whole file), since they can't deliver. Owner, in repo settings: turn off
   "Dependabot security updates" (dead without PRs) and keep "Dependabot
   alerts" on.
5. Owner: delete the two stale `dependabot/*` branches on the remote.
6. First run: act on the current backlog (table above) on a `fix/` branch —
   structlog 26 is a major; read its changelog (the app uses
   `ProcessorFormatter`, `ConsoleRenderer`, contextvars). Actions v5/v6 → v7
   usually just raise the Node runtime.

## STOP conditions

- Don't auto-commit or auto-push bumps from a workflow: every bump goes
  through a branch push and green CI (Linux + Windows) first.
- If the owner picks C, stop — that's a settings change, not code.
