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
release: _preflight
    #!/bin/sh
    set -eu
    # Gather answers up front (defaults: just hit return), then run the slow
    # gates + build unattended, then publish.
    default_title="ScenicSound Manager {{version}}{{title_suffix}}"
    printf 'Release title [%s]: ' "$default_title"
    read -r title || true
    title="${title:-$default_title}"
    printf 'Mark as pre-release? [{{ if prerelease_flag == "--prerelease" { "Y/n" } else { "y/N" } }}]: '
    read -r pre_answer || true
    pre_answer="${pre_answer:-{{ if prerelease_flag == "--prerelease" { "y" } else { "n" } }}}"
    pre_flag=""
    case "$pre_answer" in [Yy]*) pre_flag="--prerelease" ;; esac
    notes_file="$(mktemp -t release-notes)"
    cp docs/release-notes-base.md "$notes_file"
    printf 'Edit release notes in %s first? [y/N]: ' "${EDITOR:-nano}"
    read -r edit_answer || true
    case "$edit_answer" in [Yy]*) ${EDITOR:-nano} "$notes_file" ;; esac
    just check build
    # Re-runs after a partial failure resume: the tag may already exist from
    # the failed attempt (preflight guarantees it points at HEAD).
    if ! git rev-parse -q --verify "refs/tags/v{{version}}" >/dev/null; then git tag -a "v{{version}}" -m "ScenicSound Manager {{version}}"; fi
    git push origin "v{{version}}"
    (cd dist && ditto -c -k --keepParent "ScenicSound Manager.app" "ScenicSoundManager-{{version}}.zip")
    gh release create "v{{version}}" "dist/ScenicSoundManager-{{version}}.zip" --repo {{repo}} $pre_flag --title "$title" --notes-file "$notes_file"
    printf '\n✓ Released v%s — https://github.com/%s/releases/tag/v%s\n' '{{version}}' '{{repo}}' '{{version}}'

# Refuse to release from the wrong branch, a dirty tree, a stale/duplicate
# version, or the wrong gh account — all BEFORE anything irreversible happens
_preflight:
    @test "$(git rev-parse --abbrev-ref HEAD)" = "main" || { echo "✗ releases come from main (currently on $(git rev-parse --abbrev-ref HEAD))"; exit 1; }
    @test -z "$(git status --porcelain)" || { echo "✗ working tree not clean — commit or stash first"; exit 1; }
    @git fetch -q origin main
    @test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" || { echo "✗ main is not in sync with origin/main — push or pull first"; exit 1; }
    @test "$(gh api repos/{{repo}} --jq .permissions.push 2>/dev/null)" = "true" || { echo "✗ gh can't write to {{repo}} — wrong active account? Run: gh auth switch -u fzachman"; exit 1; }
    @! gh release view "v{{version}}" --repo {{repo}} >/dev/null 2>&1 || { echo "✗ release v{{version}} already exists — bump __version__ in app/__init__.py first"; exit 1; }
    @if git rev-parse -q --verify "refs/tags/v{{version}}" >/dev/null; then test "$(git rev-parse "refs/tags/v{{version}}^{commit}")" = "$(git rev-parse HEAD)" || { echo "✗ tag v{{version}} exists but points at a different commit — bump __version__ or delete the stale tag"; exit 1; }; echo "· tag v{{version}} already at HEAD (resuming a failed release)"; fi
    @echo "✓ preflight ok — will release {{version}} from $(git rev-parse --short HEAD)"
