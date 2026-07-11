"""Reusable dialog components"""

import colorsys
import os
from typing import TYPE_CHECKING

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .icons import IconLibrary
from .layouts import clear_layout
from .styles import Styles

if TYPE_CHECKING:
    from ..audio import TrackPlayer
    from ..database import AudioFile


class FilePickerDialog(QFileDialog):
    """Custom file picker for audio files"""

    AUDIO_FILTER = (
        "Audio Files (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.wma);;All Files (*)"
    )

    def __init__(self, parent=None, title: str = "Select Audio Files"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFileMode(QFileDialog.FileMode.ExistingFiles)
        self.setNameFilter(self.AUDIO_FILTER)
        self.setViewMode(QFileDialog.ViewMode.List)


class TagEditDialog(QDialog):
    """Dialog for editing a tag name and color"""

    def __init__(
        self,
        parent=None,
        title: str = "Tag",
        name: str = "",
        color: str | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(320, 240)
        self._selected_color = color or Styles.TAG_COLORS[0]
        self._selected_is_custom = False
        self._color_buttons: dict[str, QPushButton] = {}
        self._custom_color = "#FFFFFF"

        self._setup_ui(name)
        self._initialize_selection(color)

    def _setup_ui(self, name: str):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Tag name:"))
        self.name_input = QLineEdit(name)
        self.name_input.selectAll()
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Color:"))

        grid = QGridLayout()
        cols = 4
        for i, color in enumerate(Styles.TAG_COLORS):
            btn = QPushButton()
            btn.setFixedSize(50, 50)
            btn.clicked.connect(lambda checked, c=color: self._select_preset_color(c))
            self._color_buttons[color] = btn
            grid.addWidget(btn, i // cols, i % cols)
        layout.addLayout(grid)

        custom_row = QHBoxLayout()
        self.custom_button = QPushButton("")
        self.custom_button.setFixedSize(50, 50)
        self.custom_button.setToolTip("Custom")
        self.custom_button.clicked.connect(self._select_custom_color)
        custom_row.addWidget(self.custom_button)

        slider_layout = QVBoxLayout()
        self.hue_slider = QSlider(Qt.Orientation.Horizontal)
        self.hue_slider.setRange(0, 359)
        self.hue_slider.valueChanged.connect(self._on_hue_changed)
        slider_layout.addWidget(self.hue_slider)

        self.value_slider = QSlider(Qt.Orientation.Horizontal)
        self.value_slider.setRange(0, 100)
        self.value_slider.valueChanged.connect(self._on_value_changed)
        slider_layout.addWidget(self.value_slider)

        custom_row.addLayout(slider_layout)
        layout.addLayout(custom_row)

        self._set_hue_slider_style()
        self._set_value_slider_style(self.hue_slider.value())

        preview_layout = QHBoxLayout()
        preview_layout.addWidget(QLabel("Preview:"))
        self.preview_label = QLabel()
        preview_layout.addWidget(self.preview_label)
        preview_layout.addStretch()
        layout.addLayout(preview_layout)

        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._validate_and_accept)
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        layout.addLayout(button_layout)

        self.name_input.returnPressed.connect(self._validate_and_accept)
        self.name_input.textChanged.connect(self._update_preview)

    def _initialize_selection(self, color: str | None):
        if color and color not in Styles.TAG_COLORS:
            self._custom_color = color
            self._set_sliders_from_color(self._custom_color)
            self._select_custom_color()
        else:
            self._set_custom_button_style(self._custom_color, selected=False)
            self._select_preset_color(color or Styles.TAG_COLORS[0])
        self._update_preview()

    def _select_preset_color(self, color: str):
        self._selected_is_custom = False
        self._selected_color = color
        for btn_color, btn in self._color_buttons.items():
            border = "white" if btn_color == color else "transparent"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {btn_color};
                    border: 3px solid {border};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border-color: white;
                }}
            """)
        self._set_custom_button_style(self._custom_color, selected=False)
        self._set_sliders_enabled(False)
        self._update_preview()

    def _select_custom_color(self):
        self._selected_is_custom = True
        self._set_sliders_enabled(True)
        self._set_sliders_from_color(self._custom_color)
        self._selected_color = self._custom_color
        for btn_color, btn in self._color_buttons.items():
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {btn_color};
                    border: 3px solid transparent;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border-color: white;
                }}
            """)
        self._set_custom_button_style(self._custom_color, selected=True)
        self._update_preview()

    def _set_sliders_enabled(self, enabled: bool):
        self.hue_slider.setEnabled(enabled)
        self.value_slider.setEnabled(enabled)

    def _set_custom_button_style(self, color: str, selected: bool):
        border = "white" if selected else "transparent"
        text_color = "#000000" if self._is_light_color(color) else "#FFFFFF"
        self.custom_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: {text_color};
                border: 3px solid {border};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: white;
            }}
        """)

    def _set_sliders_from_color(self, color: str):
        rgb = self._hex_to_rgb(color)
        h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
        hue = int(round(h * 359))
        value = int(round(v * 100))
        self.hue_slider.blockSignals(True)
        self.value_slider.blockSignals(True)
        self.hue_slider.setValue(hue)
        self.value_slider.setValue(value)
        self.hue_slider.blockSignals(False)
        self.value_slider.blockSignals(False)
        self._set_hue_slider_style()
        self._set_value_slider_style(hue)

    def _update_custom_color_from_sliders(self):
        hue = self.hue_slider.value() / 359 if self.hue_slider.value() else 0
        value = self.value_slider.value() / 100
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, value)
        self._custom_color = self._rgb_to_hex(r, g, b)
        if self._selected_is_custom:
            self._selected_color = self._custom_color
        self._set_custom_button_style(
            self._custom_color, selected=self._selected_is_custom
        )
        self._update_preview()

    def _on_hue_changed(self):
        hue = self.hue_slider.value()
        self._set_value_slider_style(hue)
        if self._selected_is_custom:
            self._update_custom_color_from_sliders()

    def _on_value_changed(self):
        if self._selected_is_custom:
            self._update_custom_color_from_sliders()

    def _set_hue_slider_style(self):
        self.hue_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                border-radius: 4px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF0000, stop:0.16 #FFFF00, stop:0.33 #00FF00,
                    stop:0.5 #00FFFF, stop:0.66 #0000FF, stop:0.83 #FF00FF,
                    stop:1 #FF0000);
            }
            QSlider::sub-page:horizontal {
                background: transparent;
            }
            QSlider::add-page:horizontal {
                background: transparent;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 1px solid #666666;
                width: 12px;
                height: 12px;
                margin: -3px 0;
                border-radius: 6px;
            }
        """)

    def _set_value_slider_style(self, hue_value: int):
        hue = hue_value / 359 if hue_value else 0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        color_hex = self._rgb_to_hex(r, g, b)
        self.value_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 8px;
                border-radius: 4px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #000000, stop:1 {color_hex});
            }}
            QSlider::sub-page:horizontal {{
                background: transparent;
            }}
            QSlider::add-page:horizontal {{
                background: transparent;
            }}
            QSlider::handle:horizontal {{
                background: #FFFFFF;
                border: 1px solid #666666;
                width: 12px;
                height: 12px;
                margin: -3px 0;
                border-radius: 6px;
            }}
        """)

    def _update_preview(self):
        name = self.name_input.text().strip() or "Preview"
        self.preview_label.setText(name)
        self.preview_label.setStyleSheet(Styles.tag_badge_style(self._selected_color))

    def _validate_and_accept(self):
        if self.name_input.text().strip():
            self.accept()

    def get_tag_name(self) -> str:
        return self.name_input.text().strip()

    def get_selected_color(self) -> str:
        return self._selected_color

    @staticmethod
    def _rgb_to_hex(r: float, g: float, b: float) -> str:
        return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"

    @staticmethod
    def _hex_to_rgb(color: str) -> tuple[int, int, int]:
        color = color.lstrip("#")
        return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)

    @staticmethod
    def _is_light_color(color: str) -> bool:
        r, g, b = TagEditDialog._hex_to_rgb(color)
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return luminance > 186


class ConfirmDialog(QDialog):
    """Simple confirmation dialog"""

    def __init__(self, parent=None, title: str = "Confirm", message: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        # Message
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)

        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        layout.addLayout(button_layout)


class DuplicateFilesDialog(QDialog):
    """Dialog for showing duplicate audio files"""

    def __init__(self, parent=None, duplicates: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Duplicate Files")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)

        label = QLabel("These files are already in the library and were not imported:")
        label.setWordWrap(True)
        layout.addWidget(label)

        list_widget = QListWidget()
        for path in duplicates or []:
            list_widget.addItem(path)
        layout.addWidget(list_widget)

        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        layout.addLayout(button_layout)


class TextInputDialog(QDialog):
    """Dialog for text input with validation"""

    def __init__(
        self,
        parent=None,
        title: str = "Input",
        label: str = "Enter value:",
        default: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        # Label and input
        layout.addWidget(QLabel(label))
        self.input_field = QLineEdit(default)
        self.input_field.selectAll()
        layout.addWidget(self.input_field)

        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self._validate_and_accept)
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(self.ok_btn)
        layout.addLayout(button_layout)

        # Connect enter key
        self.input_field.returnPressed.connect(self._validate_and_accept)

    def _validate_and_accept(self):
        if self.input_field.text().strip():
            self.accept()

    def get_text(self) -> str:
        return self.input_field.text().strip()


class AudioFileSearchDialog(QDialog):
    """Dialog for searching and selecting audio files"""

    def __init__(
        self, db, audio_engine, disabled_track_ids: set[int] | None = None, parent=None
    ):
        super().__init__(parent)
        self.db = db
        self.audio_engine = audio_engine
        self.selected_files: list[AudioFile] = []
        self._disabled_track_ids: set[int] = disabled_track_ids or set()
        self._preview_player: TrackPlayer | None = None
        self._preview_file_id: int | None = None
        self._preview_item: FileSelectItem | None = None

        self.setWindowTitle("Add Audio Files")
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self._load_files()

    def _setup_ui(self):
        from ..library import TagManager

        layout = QVBoxLayout(self)

        # Search bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by title or artist...")
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Tag filter
        self.tag_manager = TagManager(
            self.db,
            allow_manage=False,
            header_text="Filter by tags",
        )
        self.tag_manager.tag_filter_changed.connect(self._on_tag_filter)
        layout.addWidget(self.tag_manager)

        # File list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.files_container = QWidget()
        self.files_layout = QVBoxLayout(self.files_container)
        self.files_layout.setContentsMargins(0, 0, 0, 0)
        self.files_layout.setSpacing(4)
        self.files_layout.addStretch()

        scroll.setWidget(self.files_container)
        layout.addWidget(scroll)

        # Selected count
        self.selected_label = QLabel("0 files selected")
        self.selected_label.setStyleSheet(f"color: {Styles.TEXT_MUTED};")
        layout.addWidget(self.selected_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.add_btn = QPushButton("Add Selected")
        self.add_btn.clicked.connect(self.accept)
        self.add_btn.setEnabled(False)
        button_layout.addWidget(self.add_btn)

        layout.addLayout(button_layout)

    def _load_files(self, query: str = ""):
        """Load files from database"""
        clear_layout(self.files_layout, keep_trailing_items=1)

        # Load files
        tag_ids = self.tag_manager.get_selected_tag_ids()
        excluded_tag_ids = self.tag_manager.get_excluded_tag_ids()
        if query or tag_ids or excluded_tag_ids:
            files = self.db.search_audio_files(
                query, tag_ids or None, excluded_tag_ids or None
            )
        else:
            files = self.db.get_all_audio_files()

        if self._preview_file_id and self._preview_file_id not in {f.id for f in files}:
            self._stop_preview()

        for file in files:
            disabled = file.id in self._disabled_track_ids
            item = FileSelectItem(file, disabled=disabled)
            item.selection_changed.connect(self._on_selection_changed)
            item.preview_requested.connect(self._on_preview_requested)
            # Check if already selected
            if not disabled and file.id in [f.id for f in self.selected_files]:
                item.set_selected(True)
            if self._preview_file_id == file.id:
                self._preview_item = item
                item.set_preview_playing(True)
            self.files_layout.insertWidget(self.files_layout.count() - 1, item)

    def _on_search(self, query: str):
        """Handle search"""
        self._load_files(query)

    def _on_tag_filter(self, tag_ids: list[int]):
        """Handle tag filter change"""
        self._load_files(self.search_input.text())

    def _on_selection_changed(self, file, selected: bool):
        """Handle file selection change"""
        if selected:
            if file not in self.selected_files:
                self.selected_files.append(file)
        else:
            self.selected_files = [f for f in self.selected_files if f.id != file.id]

        count = len(self.selected_files)
        self.selected_label.setText(f"{count} file{'s' if count != 1 else ''} selected")
        self.add_btn.setEnabled(count > 0)

    def get_selected_files(self):
        """Get selected files"""
        return self.selected_files

    def _on_preview_requested(self, file, item: "FileSelectItem"):
        """Toggle preview playback for a file"""
        from ..audio import TrackPlayer

        if self._preview_player:
            self._preview_player.fade_out(300)
            self._preview_player.release()
            self._preview_player = None
            if self._preview_item:
                self._preview_item.set_preview_playing(False)
            if self._preview_file_id == file.id:
                self._preview_file_id = None
                self._preview_item = None
                return

        if os.path.exists(file.file_path):
            self._preview_player = TrackPlayer(file.file_path, self.audio_engine)
            self._preview_player.end_reached.connect(self._on_preview_ended)
            self._preview_player.fade_in(300)
            self._preview_file_id = file.id
            self._preview_item = item
            item.set_preview_playing(True)

    def _on_preview_ended(self):
        """Handle preview playback ended"""
        if self._preview_item:
            self._preview_item.set_preview_playing(False)
        if self._preview_player:
            self._preview_player.release()
        self._preview_player = None
        self._preview_file_id = None
        self._preview_item = None

    def _stop_preview(self):
        """Stop any active preview playback"""
        if self._preview_player:
            self._preview_player.stop()
            self._preview_player.release()
            self._preview_player = None
        if self._preview_item:
            self._preview_item.set_preview_playing(False)
        self._preview_file_id = None
        self._preview_item = None

    def accept(self):
        self._stop_preview()
        super().accept()

    def reject(self):
        self._stop_preview()
        super().reject()


class FileSelectItem(QFrame):
    """Selectable file item in search dialog"""

    selection_changed = pyqtSignal(object, bool)
    preview_requested = pyqtSignal(object, object)

    def __init__(self, file, disabled: bool = False, parent=None):
        super().__init__(parent)
        self.file = file
        self._selected = False
        self._disabled = disabled
        self._preview_playing = False
        self._icons = IconLibrary()

        self.setFrameStyle(QFrame.Shape.StyledPanel)
        if not disabled:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Title and artist
        info_layout = QVBoxLayout()
        title_label = QLabel(file.display_title)
        text_color = Styles.TEXT_MUTED if disabled else ""
        title_label.setStyleSheet(
            f"font-weight: bold; color: {text_color};"
            if disabled
            else "font-weight: bold;"
        )
        info_layout.addWidget(title_label)

        if file.artist:
            artist_label = QLabel(file.artist)
            artist_label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 11px;")
            info_layout.addWidget(artist_label)

        layout.addLayout(info_layout, 1)

        # "Already added" label for disabled items
        if disabled:
            added_label = QLabel("Already added")
            added_label.setStyleSheet(
                f"color: {Styles.TEXT_MUTED}; font-size: 11px; font-style: italic;"
            )
            layout.addWidget(added_label)

        # Duration
        duration_label = QLabel(file.duration_formatted)
        duration_label.setStyleSheet(f"color: {Styles.TEXT_MUTED};")
        layout.addWidget(duration_label)

        # Preview button
        self.preview_btn = QPushButton()
        self.preview_btn.setFixedSize(16, 16)
        self.preview_btn.setIcon(self._icons.icon("play-solid"))
        self.preview_btn.setIconSize(QSize(12, 12))
        self.preview_btn.setStyleSheet(Styles.small_play_button_style())
        self.preview_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview_btn.clicked.connect(self._on_preview_clicked)
        layout.addWidget(self.preview_btn)

    def _update_style(self):
        """Update visual style based on selection and disabled state"""
        if self._disabled:
            self.setStyleSheet(f"""
                FileSelectItem {{
                    background-color: {Styles.BACKGROUND};
                    border: 1px solid {Styles.BORDER};
                    border-radius: 4px;
                    opacity: 0.5;
                }}
            """)
        elif self._selected:
            self.setStyleSheet(f"""
                FileSelectItem {{
                    background-color: {Styles.PRIMARY};
                    border: 1px solid {Styles.PRIMARY};
                    border-radius: 4px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                FileSelectItem {{
                    background-color: {Styles.BACKGROUND_LIGHT};
                    border: 1px solid {Styles.BORDER};
                    border-radius: 4px;
                }}
                FileSelectItem:hover {{
                    background-color: {Styles.BACKGROUND_LIGHTER};
                }}
            """)

    def set_selected(self, selected: bool):
        """Set selection state"""
        self._selected = selected
        self._update_style()

    def set_preview_playing(self, playing: bool):
        """Update preview button appearance"""
        self._preview_playing = playing
        if playing:
            self.preview_btn.setIcon(self._icons.icon("pause-solid"))
            self.preview_btn.setIconSize(QSize(12, 12))
            self.preview_btn.setStyleSheet(Styles.small_stop_button_style())
        else:
            self.preview_btn.setIcon(self._icons.icon("play-solid"))
            self.preview_btn.setIconSize(QSize(12, 12))
            self.preview_btn.setStyleSheet(Styles.small_play_button_style())

    def _on_preview_clicked(self):
        """Handle preview click"""
        self.preview_requested.emit(self.file, self)

    def mousePressEvent(self, event):
        """Handle click - disabled items cannot be selected"""
        if self._disabled:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._selected = not self._selected
            self._update_style()
            self.selection_changed.emit(self.file, self._selected)
