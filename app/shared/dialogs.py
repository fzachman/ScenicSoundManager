"""Reusable dialog components"""

import colorsys

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QFileDialog, QLineEdit, QSlider, QListWidget
)
from PyQt6.QtCore import Qt

from .styles import Styles


class FilePickerDialog(QFileDialog):
    """Custom file picker for audio files"""

    AUDIO_FILTER = "Audio Files (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.wma);;All Files (*)"

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
        self._set_custom_button_style(self._custom_color, selected=self._selected_is_custom)
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
        luminance = (0.299 * r + 0.587 * g + 0.114 * b)
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

        label = QLabel(
            "These files are already in the library and were not imported:"
        )
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
        default: str = ""
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
