"""Tests for the soundboard dock shell (Plan 008 Phase 1).

Covers the dock's permanent-panel contract: collapse to a title-bar line
(pinned height, no separator drag), expand restoring the saved height,
pop-out to a floating window whose close re-docks instead of closing, and
QSettings persistence of the collapsed state and expanded height.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QDockWidget, QMainWindow, QWidget

import app.main_window as main_window_module
from app.database import DatabaseConnection
from app.soundboard import SoundboardDock


@pytest.fixture(autouse=True)
def clean_soundboard_settings(qapp):
    settings = QSettings()
    settings.remove(SoundboardDock.SETTINGS_GROUP)
    yield
    settings.remove(SoundboardDock.SETTINGS_GROUP)


@pytest.fixture
def host(qapp):
    """A bare QMainWindow hosting the dock, shown offscreen with real layout."""
    window = QMainWindow()
    window.setMinimumSize(900, 600)
    window.setCentralWidget(QWidget())
    dock = SoundboardDock()
    window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
    window.show()
    qapp.processEvents()
    yield window, dock
    window.close()
    qapp.processEvents()


class TestDockShell:
    def test_object_name_set_for_savestate(self, host):
        # QMainWindow.saveState() silently skips docks without an objectName.
        _, dock = host
        assert dock.objectName() == "soundboardDock"

    def test_bottom_area_only_and_not_closable(self, host):
        window, dock = host
        assert window.dockWidgetArea(dock) == Qt.DockWidgetArea.BottomDockWidgetArea
        assert dock.allowedAreas() == Qt.DockWidgetArea.BottomDockWidgetArea
        assert dock.features() == QDockWidget.DockWidgetFeature.DockWidgetFloatable

    def test_starts_expanded_with_content_visible(self, host):
        _, dock = host
        assert not dock.collapsed
        assert dock.widget().isVisible()

    def test_titlebar_buttons_never_take_focus(self, host):
        # A focused button would swallow the Space play/pause transport key.
        _, dock = host
        bar = dock.titleBarWidget()
        assert bar.collapse_btn.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert bar.popout_btn.focusPolicy() == Qt.FocusPolicy.NoFocus


class TestCollapse:
    def test_collapse_hides_content_and_pins_height(self, qapp, host):
        _, dock = host
        dock.titleBarWidget().collapse_btn.click()
        qapp.processEvents()
        assert dock.collapsed
        assert not dock.widget().isVisible()
        # min == max pins the height and disables the separator drag.
        assert dock.minimumHeight() == dock.maximumHeight()
        assert dock.height() <= dock.titleBarWidget().sizeHint().height()

    def test_expand_shows_content_and_unpins(self, qapp, host):
        _, dock = host
        dock.set_collapsed(True)
        dock.titleBarWidget().collapse_btn.click()
        qapp.processEvents()
        assert not dock.collapsed
        assert dock.widget().isVisible()
        assert dock.maximumHeight() > dock.minimumHeight()

    def test_collapse_captures_expanded_height(self, qapp, host):
        window, dock = host
        window.resizeDocks([dock], [300], Qt.Orientation.Vertical)
        qapp.processEvents()
        captured = dock.height()
        dock.set_collapsed(True)
        settings = QSettings()
        settings.beginGroup(SoundboardDock.SETTINGS_GROUP)
        saved = settings.value(SoundboardDock.SETTINGS_EXPANDED_HEIGHT, type=int)
        settings.endGroup()
        assert saved == captured

    def test_expand_restores_captured_height(self, qapp, host):
        window, dock = host
        window.resizeDocks([dock], [300], Qt.Orientation.Vertical)
        qapp.processEvents()
        captured = dock.height()
        dock.set_collapsed(True)
        qapp.processEvents()
        dock.set_collapsed(False)
        qapp.processEvents()
        assert abs(dock.height() - captured) <= 5

    def test_collapsed_state_persists_across_instances(self, qapp, host):
        _, dock = host
        dock.set_collapsed(True)
        fresh = SoundboardDock()
        assert fresh.collapsed
        assert fresh.minimumHeight() == fresh.maximumHeight()


class TestPopOut:
    def test_popout_floats_and_updates_title_bar(self, qapp, host):
        _, dock = host
        bar = dock.titleBarWidget()
        bar.popout_btn.click()
        qapp.processEvents()
        assert dock.isFloating()
        # Collapse is a docked-only affordance.
        assert not bar.collapse_btn.isVisible()

    def test_popout_button_redocks_when_floating(self, qapp, host):
        _, dock = host
        bar = dock.titleBarWidget()
        bar.popout_btn.click()
        qapp.processEvents()
        bar.popout_btn.click()
        qapp.processEvents()
        assert not dock.isFloating()
        assert bar.collapse_btn.isVisible()

    def test_popout_while_collapsed_expands_first(self, qapp, host):
        _, dock = host
        dock.set_collapsed(True)
        dock.titleBarWidget().popout_btn.click()
        qapp.processEvents()
        assert dock.isFloating()
        assert not dock.collapsed
        assert dock.widget().isVisible()

    def test_closing_floating_window_redocks(self, qapp, host):
        _, dock = host
        dock.titleBarWidget().popout_btn.click()
        qapp.processEvents()
        dock.close()
        qapp.processEvents()
        assert not dock.isFloating()
        assert dock.isVisible()


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(
        main_window_module, "DatabaseConnection", lambda: DatabaseConnection(db_path)
    )
    window = main_window_module.MainWindow()
    yield window
    window.db.close()


class TestMainWindowIntegration:
    def test_dock_added_to_bottom_area(self, main_window):
        dock = main_window.soundboard_dock
        assert (
            main_window.dockWidgetArea(dock) == Qt.DockWidgetArea.BottomDockWidgetArea
        )

    def test_window_state_saved(self, qapp, main_window):
        settings = QSettings()
        settings.beginGroup(main_window.SETTINGS_UI_GROUP)
        settings.remove(main_window.SETTINGS_WINDOW_STATE)
        settings.endGroup()

        main_window._save_window_state()

        settings.beginGroup(main_window.SETTINGS_UI_GROUP)
        state = settings.value(main_window.SETTINGS_WINDOW_STATE)
        settings.remove(main_window.SETTINGS_WINDOW_STATE)
        settings.endGroup()
        assert state is not None
