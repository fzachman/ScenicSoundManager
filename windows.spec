# PyInstaller spec for the Windows build (plan 012): one-folder, windowed.
#
#   pyinstaller --noconfirm --clean windows.spec
#
# Built in CI (.github/workflows/windows-build.yml), which also zips it.
# PyInstaller can't cross-compile, so the macOS app keeps its own builder
# (setup.py / py2app). Running this spec on macOS still produces a runnable
# (non-.app) folder, which is a quick way to check data-file collection.
#
# VLC is NOT bundled (plan 010): Windows users install 64-bit VLC, and
# python-vlc finds it through the registry.
#
# resources/app_icon.ico is generated from resources/app_icon.png (16-256px,
# via Pillow's ICO writer); regenerate it if the PNG changes.

import sys

sys.path.insert(0, SPECPATH)  # noqa: F821 - injected by PyInstaller
from app import APP_DISPLAY_NAME  # noqa: E402

# Loaded relative to their module's __file__: DatabaseConnection reads the
# SQL, IconLibrary the SVGs. Frozen modules get a __file__ under
# sys._MEIPASS, so mirror the source layout there.
datas = [
    ("app/database/schema.sql", "app/database"),
    ("app/database/default_tags.sql", "app/database"),
    ("app/assets/icons", "app/assets/icons"),
]

a = Analysis(  # noqa: F821
    ["main.py"],
    datas=datas,
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy", "py2app"],
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_DISPLAY_NAME,
    console=False,
    # UPX-packed executables draw more antivirus false positives.
    upx=False,
    icon="resources/app_icon.ico",
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    upx=False,
    name=APP_DISPLAY_NAME,
)
