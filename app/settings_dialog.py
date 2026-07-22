"""Application settings dialog (app menu > Settings...).

Currently a single section: the remote-control WebSocket server. The dialog
reads and writes the QSettings the server is configured from; MainWindow
restarts the server after an accepted change (see ``remote_config_changed``).
"""

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .remote import DEFAULT_PORT, SETTINGS_ENABLED, SETTINGS_GROUP, SETTINGS_PORT
from .shared.styles import Styles


class SettingsDialog(QDialog):
    """Edit app settings; persists to QSettings on OK."""

    PORT_MIN = 1024
    PORT_MAX = 65535

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)

        self._initial_enabled, self._initial_port = self._read_remote_settings()

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("Remote Control")
        title.setStyleSheet(Styles.title_style(size=14))
        layout.addWidget(title)

        description = QLabel(
            "Lets local apps (e.g. a Stream Deck) drive playback over a "
            "WebSocket on this machine. Changes apply immediately; changing "
            "the port disconnects current clients."
        )
        description.setWordWrap(True)
        description.setStyleSheet(Styles.subtle_text_style(size=12))
        layout.addWidget(description)

        self.enabled_checkbox = QCheckBox("Enable remote control")
        self.enabled_checkbox.setChecked(self._initial_enabled)
        self.enabled_checkbox.toggled.connect(self._on_enabled_toggled)
        layout.addWidget(self.enabled_checkbox)

        port_row = QHBoxLayout()
        port_row.setSpacing(8)
        port_label = QLabel("Port")
        port_row.addWidget(port_label)
        self.port_spinbox = QSpinBox()
        self.port_spinbox.setRange(self.PORT_MIN, self.PORT_MAX)
        self.port_spinbox.setValue(self._initial_port)
        self.port_spinbox.setEnabled(self._initial_enabled)
        port_row.addWidget(self.port_spinbox)
        port_row.addStretch()
        layout.addLayout(port_row)

        layout.addStretch()

        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        layout.addLayout(button_layout)

    def _on_enabled_toggled(self, checked: bool):
        self.port_spinbox.setEnabled(checked)

    @staticmethod
    def _read_remote_settings() -> tuple[bool, int]:
        settings = QSettings()
        settings.beginGroup(SETTINGS_GROUP)
        enabled = settings.value(SETTINGS_ENABLED, defaultValue=True, type=bool)
        port = settings.value(SETTINGS_PORT, defaultValue=DEFAULT_PORT, type=int)
        settings.endGroup()
        # A stored ephemeral/invalid port would make the spinbox clamp and
        # then silently "change" it; normalize to the default instead.
        if not (SettingsDialog.PORT_MIN <= port <= SettingsDialog.PORT_MAX):
            port = DEFAULT_PORT
        return enabled, port

    def accept(self):
        settings = QSettings()
        settings.beginGroup(SETTINGS_GROUP)
        settings.setValue(SETTINGS_ENABLED, self.enabled_checkbox.isChecked())
        settings.setValue(SETTINGS_PORT, self.port_spinbox.value())
        settings.endGroup()
        super().accept()

    def remote_config_changed(self) -> bool:
        """True if the accepted values differ from what the dialog opened with
        (so MainWindow only restarts the server — dropping clients — when the
        configuration actually changed)."""
        return (
            self.enabled_checkbox.isChecked() != self._initial_enabled
            or self.port_spinbox.value() != self._initial_port
        )
