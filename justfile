# ScenicSound Manager task runner. Run `just` alone to list recipes.

# The installed `just` is an x86_64 binary, so recipe shells it spawns would
# run under Rosetta and pick the x86_64 slice of the universal venv python —
# which then can't load the venv's arm64-only C extensions (mypy, PyQt6).
# Forcing the shell to arm64 keeps everything native.
set shell := ["/usr/bin/arch", "-arm64", "/bin/sh", "-cu"]

version := `sed -n 's/^__version__ = "\(.*\)"$/\1/p' app/__init__.py`
repo := "fzachman/ScenicSoundManager"

# 0.x releases are betas: mark them pre-release on GitHub.
prerelease_flag := if version =~ '^0\.' { "--prerelease" } else { "" }
title_suffix := if version =~ '^0\.' { " (beta)" } else { "" }

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

# Gate, build, tag, zip, and publish the current app version to GitHub Releases
release: _preflight check build
    git tag -a "v{{version}}" -m "ScenicSound Manager {{version}}"
    git push origin "v{{version}}"
    cd dist && ditto -c -k --keepParent "ScenicSound Manager.app" "ScenicSoundManager-{{version}}.zip"
    gh release create "v{{version}}" "dist/ScenicSoundManager-{{version}}.zip" --repo {{repo}} {{prerelease_flag}} --title "ScenicSound Manager {{version}}{{title_suffix}}" --notes-file docs/release-notes-base.md
    @printf '\n✓ Released v%s — add highlights at https://github.com/%s/releases/tag/v%s\n' '{{version}}' '{{repo}}' '{{version}}'

# Refuse to release from the wrong branch, a dirty tree, or a stale/duplicate version
_preflight:
    @test "$(git rev-parse --abbrev-ref HEAD)" = "main" || { echo "✗ releases come from main (currently on $(git rev-parse --abbrev-ref HEAD))"; exit 1; }
    @test -z "$(git status --porcelain)" || { echo "✗ working tree not clean — commit or stash first"; exit 1; }
    @git fetch -q origin main
    @test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" || { echo "✗ main is not in sync with origin/main — push or pull first"; exit 1; }
    @if git rev-parse -q --verify "refs/tags/v{{version}}" >/dev/null; then echo "✗ tag v{{version}} already exists — bump __version__ in app/__init__.py first"; exit 1; fi
    @echo "✓ preflight ok — will release {{version}} from $(git rev-parse --short HEAD)"
