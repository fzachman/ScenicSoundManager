"""Shared helpers for the scene-control-card characterization tests.

These pin the *observable* behavior of ``TrackControl`` / ``PlaylistEntryControl``
(signals, model mutation, slider state) so the DEBT-01 refactor — which hoists
the shared logic into a ``SceneControlCard`` base + a reusable ``VolumeSlider``
component — is provably behavior-preserving.

The helpers are deliberately structure-agnostic. In particular ``patch_qt``
targets whichever module currently *binds* ``QMenu`` / ``QDrag``, so the same
tests work both before the refactor (methods live in the two control modules)
and after (methods live in ``app/shared/base_control_card.py``).
"""

import sys

from PyQt6.QtCore import QObject, QPointF, Qt, pyqtSignal

# Modules that may define the drag / context-menu plumbing across the refactor.
_CONTROL_MODULES = (
    "app.scenes.track_control",
    "app.scenes.playlist_entry_control",
    "app.shared.base_control_card",
)


def record(signal):
    """Connect a recorder to a pyqtSignal; return a list of emitted arg-tuples."""
    calls: list[tuple] = []
    signal.connect(lambda *args: calls.append(args))
    return calls


class FakeTrackPlayer(QObject):
    """Minimal stand-in for ``app.audio.player.TrackPlayer`` (no VLC).

    Exposes only the surface ``TrackControl`` touches: ``position_changed`` /
    ``end_reached`` signals, a plain ``target_volume`` int, a plain ``repeat``
    bool, ``get_duration()``, and a recording ``set_position()``.
    """

    position_changed = pyqtSignal(int)
    end_reached = pyqtSignal()

    def __init__(self, duration_ms: int = 60000):
        super().__init__()
        self.target_volume = 0
        self.repeat = False
        self._duration = duration_ms
        self.set_position_calls: list[int] = []

    def get_duration(self) -> int:
        return self._duration

    def set_position(self, position_ms: int) -> None:
        self.set_position_calls.append(position_ms)


class FakeMouseEvent:
    """Duck-typed QMouseEvent for driving ``mouseMoveEvent`` headlessly.

    ``mouseMoveEvent`` only calls ``buttons()`` and ``position()``; this reports
    the left button held and a point far enough from the drag-start to clear the
    ``startDragDistance`` threshold.
    """

    def __init__(self, x: float = 100.0, y: float = 100.0):
        self._pos = QPointF(x, y)

    def buttons(self):
        return Qt.MouseButton.LeftButton

    def position(self):
        return self._pos


class FakeContextEvent:
    """Duck-typed QContextMenuEvent (``contextMenuEvent`` only uses globalPos)."""

    def globalPos(self):
        return None


class _FakeActionSignal:
    def __init__(self):
        self._slots: list = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self):
        for fn in list(self._slots):
            fn()


class FakeAction:
    def __init__(self, text: str):
        self._text = text
        self.triggered = _FakeActionSignal()

    def text(self) -> str:
        return self._text


class FakeMenu:
    """Non-blocking QMenu stand-in: ``exec()`` triggers every added action.

    This drives the *real* ``contextMenuEvent`` body (which connects the action's
    ``triggered`` to a ``remove_requested.emit`` lambda) without blocking on a
    real event loop. Constructed instances are recorded in ``FakeMenu.created``
    so a test can assert which actions the menu actually offered (e.g. that the
    only action is "Remove from scene").
    """

    created: list["FakeMenu"] = []

    def __init__(self, *args, **kwargs):
        self._actions: list[FakeAction] = []
        FakeMenu.created.append(self)

    def addAction(self, text: str) -> FakeAction:
        action = FakeAction(text)
        self._actions.append(action)
        return action

    def actions(self) -> list[FakeAction]:
        return list(self._actions)

    def exec(self, *args, **kwargs):
        for action in self._actions:
            action.triggered.emit()
        return None


class FakeDrag:
    """Non-blocking QDrag stand-in that captures the QMimeData it is handed."""

    created: list["FakeDrag"] = []

    def __init__(self, *args, **kwargs):
        self.mime_data = None
        FakeDrag.created.append(self)

    def setMimeData(self, mime):
        self.mime_data = mime

    def setPixmap(self, pixmap):
        pass

    def setHotSpot(self, point):
        pass

    def exec(self, *args, **kwargs):
        return None


def patch_qt(monkeypatch, **names) -> None:
    """Patch Qt names (e.g. ``QMenu=FakeMenu``) in whichever already-imported
    control/base module binds them, so the patch follows the drag/context-menu
    methods if they move to the base class during the refactor.
    """
    for modname in _CONTROL_MODULES:
        module = sys.modules.get(modname)
        if module is None:
            continue
        for name, value in names.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, value, raising=False)


def mime_payload(mime, mime_type: str) -> str:
    """Decode the bytes stored under ``mime_type`` in a QMimeData."""
    return bytes(mime.data(mime_type)).decode()
