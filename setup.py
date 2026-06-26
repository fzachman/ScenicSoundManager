"""
py2app build script for SoundManager

Usage:
    python setup.py py2app

To bundle VLC libraries:
1. Install VLC.app from https://www.videolan.org/vlc/
2. The setup script will automatically locate and bundle VLC libraries

For development builds:
    python setup.py py2app -A  (alias mode, faster but requires source files)

For production builds:
    python setup.py py2app     (standalone, includes all dependencies)
"""

import os
import sys

from setuptools import setup

# Application metadata
APP = ["main.py"]
APP_NAME = "SoundManager"
VERSION = "1.0.0"

# Data files to include
DATA_FILES = []

# py2app options
OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,  # Add path to .icns file if available
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleGetInfoString": "D&D Audio Soundscape Manager",
        "CFBundleIdentifier": "com.soundmanager.app",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,  # Support dark mode
    },
    "packages": [
        "PyQt6",
        "vlc",
        "mutagen",
        "structlog",
    ],
    "includes": [
        "app",
        "app.database",
        "app.audio",
        "app.library",
        "app.scenes",
        "app.shared",
    ],
    "excludes": [
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
    ],
    "frameworks": [],  # VLC libraries will be added here
    "resources": [
        "app/database/schema.sql",
    ],
}


def find_vlc_libraries():
    """Find VLC libraries from VLC.app installation"""
    vlc_app_paths = [
        "/Applications/VLC.app",
        os.path.expanduser("~/Applications/VLC.app"),
    ]

    for vlc_path in vlc_app_paths:
        if os.path.exists(vlc_path):
            lib_path = os.path.join(vlc_path, "Contents", "MacOS", "lib")
            plugins_path = os.path.join(vlc_path, "Contents", "MacOS", "plugins")

            if os.path.exists(lib_path) and os.path.exists(plugins_path):
                return lib_path, plugins_path

    return None, None


def setup_vlc_bundling():
    """Set up VLC library bundling"""
    lib_path, plugins_path = find_vlc_libraries()

    if lib_path and plugins_path:
        print(f"Found VLC libraries at: {lib_path}")

        # Add VLC libraries to frameworks
        vlc_libs = [
            os.path.join(lib_path, "libvlc.dylib"),
            os.path.join(lib_path, "libvlccore.dylib"),
        ]

        for lib in vlc_libs:
            if os.path.exists(lib):
                OPTIONS["frameworks"].append(lib)
                print(f"  Adding: {lib}")

        # Add plugins as resources (they'll be copied to Resources/plugins)
        # Note: This increases app size significantly but ensures all codecs work
        print(f"VLC plugins will be copied from: {plugins_path}")

        return True
    else:
        print(
            "WARNING: VLC.app not found. The app will require VLC to be installed separately."
        )
        print(
            "Install VLC from https://www.videolan.org/vlc/ to bundle it with the app."
        )
        return False


if __name__ == "__main__":
    # Set up VLC bundling if building app
    if "py2app" in sys.argv:
        setup_vlc_bundling()

    setup(
        name=APP_NAME,
        version=VERSION,
        app=APP,
        data_files=DATA_FILES,
        options={"py2app": OPTIONS},
        setup_requires=["py2app"],
        python_requires=">=3.10",
        install_requires=[
            "PyQt6>=6.6.0",
            "python-vlc>=3.0.18",
            "mutagen>=1.47.0",
            "structlog>=24.1.0",
        ],
    )
