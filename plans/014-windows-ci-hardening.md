# Plan 014: Windows CI hardening

**Status:** TODO (planned 2026-09-23). Found while releasing v0.9.5
(plan 012). Nothing here affects the app; it makes
`.github/workflows/windows-build.yml` fail fast and loudly instead of
passing silently or hanging.

## What went wrong (evidence: run 35805614842, attempts 1–3, commit `b6068fe`)

1. **Chocolatey exit codes can't be trusted.** Attempt 1: the community feed
   returned 504, `choco install vlc` exited 1 (the job failed — correct).
   Attempt 2: the feed returned 503, choco printed "Chocolatey installed 0/0
   packages" and exited **0**, so the "Install 64-bit VLC" step went green
   with no VLC installed.
2. **Multi-line PowerShell steps only fail on the LAST command.** Windows
   runners default to `pwsh`, which does not stop on a failing native
   command. In attempt 2 the preflight's first line failed
   (`AssertionError: libvlc failed to import`), the second line (Qt) passed,
   and the step went green. Same exposure in "Install Python dependencies"
   (pip upgrade + pip install) and "Zip the build".
3. **Tests without VLC hang forever.** With no libVLC, every `MainWindow`
   schedules `_warn_missing_audio` (`QTimer.singleShot(0, ...)`), a modal
   `QMessageBox.exec()`. Offscreen, nobody clicks OK: the first test that
   processes events blocks. Attempt 2 stopped after 158 tests, inside
   `tests/test_main_window.py::test_scene_playing_sets_state_and_indicator`
   (the two VLC-guarded tests in `test_engine.py` had skipped, which is how
   the missing VLC was spotted).
4. **No job timeout, no stack dump.** GitHub's default job timeout is 6
   hours, and a hung pytest prints nothing — attempt 2 had to be cancelled by
   hand after 12 minutes. Normal durations: tests job ~6 min, build job
   ~1 min.

Attempt 3 (choco healthy) passed: 845 passed, no skips.

## Steps

1. **Fail-fast shells.** In `windows-build.yml`, add to both jobs:
   ```yaml
   defaults:
     run:
       shell: bash
   ```
   (Git Bash on `windows-latest`; GitHub runs it as
   `bash --noprofile --norc -eo pipefail`, so any failing line fails the
   step.) Rewrite "Zip the build" for bash:
   ```bash
   version=$(python -c "from app import __version__; print(__version__)")
   zip="dist/ScenicSoundManager-$version-windows.zip"
   python -m zipfile -c "$zip" "dist/ScenicSound Manager"
   echo "path=$zip" >> "$GITHUB_OUTPUT"
   ```
   `python -m zipfile -c` stores each source under its basename, so the zip
   keeps `ScenicSound Manager/` at the top level like `Compress-Archive`
   did — `just release` and the install notes depend on that layout; check
   it with `python -m zipfile -l`. Fallback if bash causes trouble: keep pwsh
   and put `$PSNativeCommandUseErrorActionPreference = $true` first in each
   multi-line step.
2. **VLC install: retry, then verify.** Replace the choco step with a loop
   (3 attempts, growing sleep) that treats "installed" as
   `test -f "/c/Program Files/VideoLAN/VLC/libvlc.dll"`, not choco's exit
   code, and fails with a clear message after the last attempt. Optional
   fallback when choco stays down: the official win64 installer from
   get.videolan.org, run silently with `/S`.
3. **Time limits.** `timeout-minutes: 20` on the tests job and 10 on the
   build job (~3x and ~10x normal).
4. **Stack dump for stuck tests.** Add `faulthandler_timeout = 120` to
   `[tool.pytest.ini_options]` in `pyproject.toml`. pytest's built-in
   faulthandler then dumps every thread's stack when one test runs longer
   than 120 s (it does not kill the test; step 3 does that). The whole local
   suite takes ~15 s, so there are no false alarms. Helps on every platform.
5. **Optional — tests survive a missing VLC.** An autouse fixture in
   `tests/conftest.py` that replaces `MainWindow._warn_missing_audio` with a
   no-op, so a machine without VLC gets skips instead of a hang. The tests
   that pin the dialog's scheduling patch it themselves (search
   `_warn_missing_audio` in `tests/test_main_window.py`) and must keep
   passing.

## Verification

- A normal push to a `fix/` branch: both jobs green, 845+ passed, zip
  layout unchanged (`python -m zipfile -l` or download the artifact).
- Prove the fail-fast behavior once, in a throwaway commit on the branch
  (then drop it): make the preflight's first line fail (e.g. assert on a
  bogus module) — the step must go red. Optionally request a nonexistent
  choco package to exercise the retry loop's final failure.

## STOP conditions

- If Git Bash breaks `choco`, `pyinstaller`, or paths with spaces, use the
  pwsh fallback in step 1 rather than fighting quoting.
- Don't change what `just release` downloads (artifact name, `archive:
  false`, top-level folder) without updating the justfile and plan 012's
  notes in the same change.

## Out of scope

- Linux CI (`ci.yml`): its bash shell already fails fast.
- Dependabot and dependency freshness: plan 015.
