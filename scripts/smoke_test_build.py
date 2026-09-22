"""Smoke-test a frozen build: launch it, wait for startup, check the database.

Used by CI (.github/workflows/windows-build.yml) on a clean runner, where the
app's data and log folders (app/paths.py) start empty. It refuses to run
when a library already exists there, so it can never launch against (and
modify) a real install.

    python scripts/smoke_test_build.py "dist/ScenicSound Manager/ScenicSound Manager.exe"

Passes when the app logs ``app_started`` (main.py, after the window shows),
is still running a few seconds later, and has created its database with the
default tags seeded — which proves the bundled schema.sql and
default_tags.sql were found.
"""

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import paths  # noqa: E402

STARTUP_TIMEOUT_S = 90  # a first launch on a CI runner is slow (AV scanning)
SETTLE_S = 5  # keep the event loop running past startup timers


def main() -> int:
    exe = Path(sys.argv[1])
    db = paths.DATA_DIR / paths.DB_FILENAME
    log = paths.LOG_DIR / "soundmanager.log"
    if db.exists():
        print(f"Refusing to run: a library already exists at {db}")
        return 2

    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    proc = subprocess.Popen([str(exe)], env=env)
    started = False
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline and proc.poll() is None:
        if log.exists() and "app_started" in log.read_text(errors="replace"):
            started = True
            break
        time.sleep(0.5)
    if started:
        time.sleep(SETTLE_S)
    alive = proc.poll() is None
    if alive:
        proc.kill()
    proc.wait()

    failures = []
    if not started:
        failures.append(f"no app_started log line within {STARTUP_TIMEOUT_S}s")
    if not alive:
        failures.append(f"app exited early (code {proc.returncode})")
    if not db.exists():
        failures.append(f"no database at {db}")
    else:
        con = sqlite3.connect(db)
        try:
            tags = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        except sqlite3.Error as exc:
            failures.append(f"database has no schema: {exc}")
        else:
            if tags == 0:
                failures.append("default tags were not seeded")
        finally:
            con.close()

    print(f"--- {log}")
    print(log.read_text(errors="replace") if log.exists() else "(no log file)")
    if failures:
        print("SMOKE TEST FAILED:\n  " + "\n  ".join(failures))
        return 1
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
