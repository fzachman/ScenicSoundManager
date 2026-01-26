#!/usr/bin/env python3
"""SoundManager - D&D Audio Soundscape Manager

Main entry point for the application.
"""

import sys
import os


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

    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication

    from app.main_window import MainWindow

    # High DPI support (must be set before QApplication is created)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("SoundManager")
    app.setOrganizationName("SoundManager")

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
