"""Tests for the app Settings dialog (remote-control section)."""

import pytest
from PyQt6.QtCore import QSettings

from app.remote import DEFAULT_PORT, SETTINGS_ENABLED, SETTINGS_GROUP, SETTINGS_PORT
from app.settings_dialog import SettingsDialog


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
