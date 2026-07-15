"""Create/edit dialog for soundboards: name field + standard track picker"""

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..database import AudioFile, Soundboard
from ..shared.dialogs import AudioFileSearchWidget


class SoundboardEditDialog(QDialog):
    """One dialog for both creating and editing a soundboard.

    Create mode (no board): empty name, all library files selectable.
    Edit mode: name prefilled; the board's existing tracks show greyed out
    ("Already added") and newly selected files are appended by the caller.
    Removing a track is a context-menu action on its button, not part of
    this dialog.
    """

    def __init__(
        self,
        db,
        audio_engine,
        soundboard: Soundboard | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Soundboard" if soundboard else "New Soundboard")
        self.setMinimumSize(560, 520)

        layout = QVBoxLayout(self)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit(soundboard.name if soundboard else "")
        self.name_input.setPlaceholderText("Soundboard name...")
        self.name_input.textChanged.connect(self._on_name_changed)
        name_row.addWidget(self.name_input)
        layout.addLayout(name_row)

        disabled_ids = (
            {b.audio_file_id for b in soundboard.buttons if b.audio_file_id is not None}
            if soundboard
            else None
        )
        self.search_widget = AudioFileSearchWidget(
            db, audio_engine, disabled_ids, parent=self
        )
        layout.addWidget(self.search_widget, 1)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.save_btn)
        layout.addLayout(button_layout)

        self._on_name_changed(self.name_input.text())

    def _on_name_changed(self, text: str) -> None:
        self.save_btn.setEnabled(bool(text.strip()))

    def get_name(self) -> str:
        return self.name_input.text().strip()

    def get_selected_files(self) -> list[AudioFile]:
        return self.search_widget.get_selected_files()

    def accept(self):
        self.search_widget.stop_preview()
        super().accept()

    def reject(self):
        self.search_widget.stop_preview()
        super().reject()
