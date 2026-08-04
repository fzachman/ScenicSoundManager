"""Tests for the app Settings dialog (appearance + remote-control sections)."""

import pytest
from PyQt6.QtCore import QSettings

from app.remote import DEFAULT_PORT, SETTINGS_ENABLED, SETTINGS_GROUP, SETTINGS_PORT
from app.settings_dialog import SettingsDialog
from app.shared.styles import Styles
from app.shared.theme import DEFAULT_THEME, SETTINGS_THEME_KEY


@pytest.fixture(autouse=True)
def remote_settings(qapp):
    """Clean remote settings for each test, then restore the session default
    (remote disabled — see conftest) so later MainWindow-constructing tests
    don't bind a real port."""
    settings = QSettings()
    settings.remove(SETTINGS_GROUP)
    yield settings
    settings.remove(SETTINGS_GROUP)
    settings.beginGroup(SETTINGS_GROUP)
    settings.setValue(SETTINGS_ENABLED, False)
    settings.endGroup()


def _set(settings, enabled=None, port=None):
    settings.beginGroup(SETTINGS_GROUP)
    if enabled is not None:
        settings.setValue(SETTINGS_ENABLED, enabled)
    if port is not None:
        settings.setValue(SETTINGS_PORT, port)
    settings.endGroup()


def test_defaults_with_no_stored_settings(remote_settings):
    dialog = SettingsDialog()
    assert dialog.enabled_checkbox.isChecked() is True
    assert dialog.port_spinbox.value() == DEFAULT_PORT


def test_reflects_stored_settings(remote_settings):
    _set(remote_settings, enabled=False, port=9001)
    dialog = SettingsDialog()
    assert dialog.enabled_checkbox.isChecked() is False
    assert dialog.port_spinbox.value() == 9001
    assert dialog.port_spinbox.isEnabled() is False


def test_invalid_stored_port_normalized_to_default(remote_settings):
    # An ephemeral port (0) can be stored by tests/tools; the spinbox must not
    # clamp it to PORT_MIN and then silently persist that as a change.
    _set(remote_settings, enabled=True, port=0)
    dialog = SettingsDialog()
    assert dialog.port_spinbox.value() == DEFAULT_PORT


def test_checkbox_gates_port_spinbox(remote_settings):
    dialog = SettingsDialog()
    assert dialog.port_spinbox.isEnabled() is True
    dialog.enabled_checkbox.setChecked(False)
    assert dialog.port_spinbox.isEnabled() is False


def test_accept_persists_values(remote_settings):
    dialog = SettingsDialog()
    dialog.enabled_checkbox.setChecked(False)
    dialog.port_spinbox.setValue(9100)
    dialog.accept()

    remote_settings.beginGroup(SETTINGS_GROUP)
    enabled = remote_settings.value(SETTINGS_ENABLED, type=bool)
    port = remote_settings.value(SETTINGS_PORT, type=int)
    remote_settings.endGroup()
    assert enabled is False
    assert port == 9100


def test_reject_persists_nothing(remote_settings):
    dialog = SettingsDialog()
    dialog.enabled_checkbox.setChecked(False)
    dialog.reject()

    remote_settings.beginGroup(SETTINGS_GROUP)
    assert not remote_settings.contains(SETTINGS_ENABLED)
    remote_settings.endGroup()


def test_remote_config_changed_false_when_untouched(remote_settings):
    dialog = SettingsDialog()
    dialog.accept()
    assert dialog.remote_config_changed() is False


def test_remote_config_changed_true_on_toggle(remote_settings):
    dialog = SettingsDialog()
    dialog.enabled_checkbox.setChecked(False)
    dialog.accept()
    assert dialog.remote_config_changed() is True


def test_remote_config_changed_true_on_port_change(remote_settings):
    dialog = SettingsDialog()
    dialog.port_spinbox.setValue(DEFAULT_PORT + 1)
    dialog.accept()
    assert dialog.remote_config_changed() is True


@pytest.fixture
def theme_settings(qapp):
    """Clean theme setting and restore the dark theme around each test."""
    settings = QSettings()
    settings.remove(SETTINGS_THEME_KEY)
    yield settings
    settings.remove(SETTINGS_THEME_KEY)
    Styles.set_theme(DEFAULT_THEME)


def test_theme_combo_defaults_to_dark(remote_settings, theme_settings):
    dialog = SettingsDialog()
    assert dialog.theme_combo.currentData() == "dark"


def test_theme_combo_reflects_saved_theme(remote_settings, theme_settings):
    theme_settings.setValue(SETTINGS_THEME_KEY, "light")
    dialog = SettingsDialog()
    assert dialog.theme_combo.currentData() == "light"


def test_accept_persists_and_applies_theme(remote_settings, theme_settings):
    dialog = SettingsDialog()
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("light"))
    dialog.accept()
    assert theme_settings.value(SETTINGS_THEME_KEY, type=str) == "light"
    assert Styles.active_theme == "light"


def test_theme_previews_live_on_selection(remote_settings, theme_settings):
    dialog = SettingsDialog()
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("light"))
    # Applied immediately for preview, but not yet persisted.
    assert Styles.active_theme == "light"
    assert not theme_settings.contains(SETTINGS_THEME_KEY)


def test_reject_reverts_theme_preview(remote_settings, theme_settings):
    dialog = SettingsDialog()
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("light"))
    assert Styles.active_theme == "light"
    dialog.reject()
    assert not theme_settings.contains(SETTINGS_THEME_KEY)
    assert Styles.active_theme == "dark"
