# ScenicSound Manager task runner. Run `just` alone to list recipes.

# The installed `just` is an x86_64 binary, so recipe shells it spawns would
# run under Rosetta and pick the x86_64 slice of the universal venv python —
# which then can't load the venv's arm64-only C extensions (mypy, PyQt6).
# Forcing the shell to arm64 keeps everything native.
set shell := ["/usr/bin/arch", "-arm64", "/bin/sh", "-cu"]

# List available recipes
default:
    @just --list

# Run the app from source
run:
    ./run.sh

# Run the test suite
test:
    venv/bin/pytest tests/

# Run every CI gate (format, lint, types, tests)
check:
    venv/bin/ruff format --check .
    venv/bin/ruff check .
    venv/bin/mypy app/
    venv/bin/pytest tests/

# Build the macOS app bundle into dist/ (requires VLC.app installed)
build:
    rm -rf build dist
    venv/bin/python setup.py py2app
    @app="$(echo dist/*.app)"; ver="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app/Contents/Info.plist")"; printf '\n✓ Built %s (version %s)\n' "$app" "$ver"
