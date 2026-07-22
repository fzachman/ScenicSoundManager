"""
py2app build script for SoundManager

Usage:
    python setup.py py2app

The build does NOT embed VLC (plan 010 decision): the built app requires
VLC.app installed at runtime (python-vlc auto-discovers /Applications/
VLC.app; the app shows an install-VLC dialog when it's missing). If a
future release embeds libVLC, see plan 010 — it's LGPL-legal via dynamic
linking, but the plugin set must be curated and PYTHON_VLC_LIB_PATH /
VLC_PLUGIN_PATH wired (hooks already exist in main.py and AudioEngine).

For development builds:
    python setup.py py2app -A  (alias mode, faster but requires source files)

For production builds:
    python setup.py py2app     (standalone, includes all dependencies)
"""

from setuptools import setup

from app import APP_DISPLAY_NAME, __version__

# Application metadata. APP_NAME is the internal/setuptools name; the
# user-facing name (macOS menu bar, Finder) comes from the plist below.
APP = ["main.py"]
APP_NAME = "SoundManager"
VERSION = __version__

# Data files to include
DATA_FILES = []

# py2app options
OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,  # Add path to .icns file if available
    "plist": {
        # CFBundleName names the macOS app menu; keep it the display name.
        "CFBundleName": APP_DISPLAY_NAME,
        "CFBundleDisplayName": APP_DISPLAY_NAME,
        "CFBundleGetInfoString": "D&D Audio Soundscape Manager",
        "CFBundleIdentifier": "com.scenicsound.soundmanager",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,  # Support dark mode
    },
    # "app" MUST be in packages (not includes): py2app copies packages as
    # real directories, keeping __file__-relative data loading working
    # (DatabaseConnection reads schema.sql, IconLibrary reads
    # app/assets/icons/*.svg). Modules in `includes` go into a zip where
    # those paths don't exist.
    "packages": [
        "app",
        "PyQt6",
        "vlc",
        "mutagen",
        "structlog",
    ],
    "excludes": [
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
    ],
}


if __name__ == "__main__":
    setup(
        name=APP_NAME,
        version=VERSION,
        app=APP,
        data_files=DATA_FILES,
        options={"py2app": OPTIONS},
        # No install_requires/setup_requires: newer setuptools rejects them
        # here, and this file is purely the py2app build script — runtime
        # dependencies are pinned in requirements.txt.
    )
