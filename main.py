#!/usr/bin/env python3
"""SoundManager - D&D Audio Soundscape Manager

Main entry point for the application.
"""

import os
import sys


def setup_environment():
    """Set up environment variables for bundled VLC if needed"""
    if getattr(sys, "frozen", False):
        # Running in a py2app bundle
        bundle_dir = os.path.dirname(sys.executable)
        resources_dir = os.path.join(bundle_dir, "..", "Resources")

        # VLC library paths
        vlc_lib = os.path.join(resources_dir, "lib", "libvlc.dylib")
        vlc_plugins = os.path.join(resources_dir, "plugins")

        if os.path.exists(vlc_lib):
            os.environ["PYTHON_VLC_LIB_PATH"] = vlc_lib
        if os.path.exists(vlc_plugins):
            os.environ["VLC_PLUGIN_PATH"] = vlc_plugins


def main():
    """Main entry point"""
    setup_environment()

    from app.shared.logging import configure_logging

    configure_logging()

    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication

    from app.main_window import MainWindow

    # High DPI support (must be set before QApplication is created)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    from app import APP_DISPLAY_NAME

    # Create application. applicationName/organizationName are the QSettings
    # identity (macOS domain com.scenicsound.SoundManager) — renaming either
    # orphans existing user settings, so any future change needs a startup
    # migration (see commit 6458079 for the 2026-07 org-rename one, removed
    # after it ran; note macOS merges NSGlobalDomain into QSettings.allKeys()).
    # The user-facing name goes in applicationDisplayName and the bundle plist.
    app = QApplication(sys.argv)
    app.setApplicationName("SoundManager")
    app.setOrganizationName("ScenicSound")
    app.setApplicationDisplayName(APP_DISPLAY_NAME)

    # Refuse to run twice: two instances share one database, which is
    # unsafe around schema upgrades (see app/single_instance.py). The
    # lock must stay referenced for the app's lifetime.
    from PyQt6.QtWidgets import QMessageBox

    from app.single_instance import acquire_instance_lock

    instance_lock = acquire_instance_lock()
    if instance_lock is None:
        QMessageBox.warning(
            None,
            "Already Running",
            f"{APP_DISPLAY_NAME} is already running.\n\n"
            "Close the other copy before opening a new one — two copies "
            "sharing one library can corrupt it during upgrades.",
        )
        sys.exit(0)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
