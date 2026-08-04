"""Application styling constants and reusable stylesheets."""

from typing import ClassVar


class Styles:
    """Application-wide style constants and stylesheets.

    Palette tokens (PRIMARY, BACKGROUND, ...) are class attributes whose
    values belong to the active theme; call set_theme() to swap them.
    Stylesheet helpers read the tokens at call time, so styles built after
    a swap automatically use the new palette.
    """

    DARK_PALETTE: ClassVar[dict[str, str]] = {
        "PRIMARY": "#5CA4FF",
        "PRIMARY_DARK": "#4388E0",
        "SECONDARY": "#7A8597",
        "SUCCESS": "#41C784",
        "SUCCESS_DARK": "#33A66D",
        "WARNING": "#F2C14E",
        "WARNING_DARK": "#D9AA3C",
        "DANGER": "#F36B6B",
        "DANGER_DARK": "#DA5A5A",
        "BACKGROUND": "#13171D",
        "BACKGROUND_ELEVATED": "#1A2029",
        "BACKGROUND_LIGHT": "#222A35",
        "BACKGROUND_LIGHTER": "#2B3543",
        "BACKGROUND_HOVER": "#354256",
        "TEXT": "#F3F6FB",
        "TEXT_MUTED": "#A1ADBE",
        "TEXT_SUBTLE": "#7A8698",
        "BORDER": "#344154",
        "BORDER_STRONG": "#4A586E",
    }

    # Provisional values — to be refined by the design pass.
    LIGHT_PALETTE: ClassVar[dict[str, str]] = {
        "PRIMARY": "#2F6FDB",
        "PRIMARY_DARK": "#2458B8",
        "SECONDARY": "#68748A",
        "SUCCESS": "#1F9D61",
        "SUCCESS_DARK": "#188550",
        "WARNING": "#E0A626",
        "WARNING_DARK": "#C4901D",
        "DANGER": "#D64545",
        "DANGER_DARK": "#BC3A3A",
        "BACKGROUND": "#F5F7FA",
        "BACKGROUND_ELEVATED": "#FFFFFF",
        "BACKGROUND_LIGHT": "#EDF1F6",
        "BACKGROUND_LIGHTER": "#E2E8F0",
        "BACKGROUND_HOVER": "#D5DEEA",
        "TEXT": "#1A2230",
        "TEXT_MUTED": "#5A6678",
        "TEXT_SUBTLE": "#8592A6",
        "BORDER": "#D3DCE8",
        "BORDER_STRONG": "#AEBACB",
    }

    PALETTES: ClassVar[dict[str, dict[str, str]]] = {
        "dark": DARK_PALETTE,
        "light": LIGHT_PALETTE,
    }

    active_theme: ClassVar[str] = "dark"

    # Active palette tokens — assigned by set_theme() at the bottom of
    # this module and whenever the theme changes.
    PRIMARY: ClassVar[str]
    PRIMARY_DARK: ClassVar[str]
    SECONDARY: ClassVar[str]
    SUCCESS: ClassVar[str]
    SUCCESS_DARK: ClassVar[str]
    WARNING: ClassVar[str]
    WARNING_DARK: ClassVar[str]
    DANGER: ClassVar[str]
    DANGER_DARK: ClassVar[str]
    BACKGROUND: ClassVar[str]
    BACKGROUND_ELEVATED: ClassVar[str]
    BACKGROUND_LIGHT: ClassVar[str]
    BACKGROUND_LIGHTER: ClassVar[str]
    BACKGROUND_HOVER: ClassVar[str]
    TEXT: ClassVar[str]
    TEXT_MUTED: ClassVar[str]
    TEXT_SUBTLE: ClassVar[str]
    BORDER: ClassVar[str]
    BORDER_STRONG: ClassVar[str]

    @classmethod
    def set_theme(cls, name: str) -> None:
        """Activate a palette by name; unknown names fall back to dark."""
        palette = cls.PALETTES.get(name, cls.DARK_PALETTE)
        cls.active_theme = name if name in cls.PALETTES else "dark"
        for key, value in palette.items():
            setattr(cls, key, value)

    @staticmethod
    def tint(color: str, alpha: float) -> str:
        """Translucent rgba() form of a hex color, for overlay tints."""
        color = color.lstrip("#")
        r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"

    @staticmethod
    def contrast_text_color(background: str) -> str:
        """Black-ish or white text, whichever reads better on background."""
        hex_color = background.lstrip("#")
        r, g, b = (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return "#11161C" if luminance > 186 else "#FFFFFF"

    # Tag colors
    TAG_COLORS = [
        "#E57373",  # Red
        "#F06292",  # Pink
        "#BA68C8",  # Purple
        "#9575CD",  # Deep Purple
        "#7986CB",  # Indigo
        "#64B5F6",  # Blue
        "#4FC3F7",  # Light Blue
        "#4DD0E1",  # Cyan
        "#4DB6AC",  # Teal
        "#81C784",  # Green
        "#AED581",  # Light Green
        "#DCE775",  # Lime
        "#FFF176",  # Yellow
        "#FFD54F",  # Amber
        "#FFB74D",  # Orange
        "#FF8A65",  # Deep Orange
    ]

    @classmethod
    def app_stylesheet(cls) -> str:
        """Full application stylesheet for the active theme."""
        return f"""
        QMainWindow, QWidget {{
            background-color: {cls.BACKGROUND};
            color: {cls.TEXT};
            font-size: 13px;
        }}

        QWidget {{
            selection-background-color: {cls.PRIMARY};
            selection-color: {cls.TEXT};
        }}

        QTabWidget {{
            background-color: transparent;
        }}

        QTabWidget::pane {{
            top: 0px;
            border: none;
            background-color: transparent;
        }}

        QTabBar {{
            background-color: transparent;
        }}

        QTabBar::tab {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_MUTED};
            padding: 12px 22px;
            border: 1px solid {cls.BORDER};
            border-bottom: none;
            border-top-left-radius: 14px;
            border-top-right-radius: 14px;
            margin-right: 8px;
            margin-bottom: 0px;
            min-width: 110px;
            font-size: 14px;
            font-weight: 600;
        }}

        QTabBar::tab:selected {{
            background-color: {cls.BACKGROUND_LIGHT};
            color: {cls.TEXT};
            border-color: {cls.BORDER_STRONG};
        }}

        QTabBar::tab:hover:!selected {{
            background-color: {cls.BACKGROUND_LIGHT};
            color: {cls.TEXT};
        }}

        QPushButton {{
            background-color: {cls.BACKGROUND_LIGHT};
            color: {cls.TEXT};
            border: 1px solid {cls.BORDER};
            padding: 9px 16px;
            border-radius: 10px;
            font-weight: 600;
        }}

        QPushButton:hover {{
            background-color: {cls.BACKGROUND_HOVER};
            border-color: {cls.BORDER_STRONG};
        }}

        QPushButton:pressed {{
            background-color: {cls.BACKGROUND_LIGHTER};
        }}

        QPushButton:disabled {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT_SUBTLE};
            border-color: {cls.BORDER};
        }}

        QLineEdit {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT};
            border: 1px solid {cls.BORDER};
            padding: 9px 12px;
            border-radius: 10px;
        }}

        QLineEdit:focus {{
            border-color: {cls.PRIMARY};
            background-color: {cls.BACKGROUND_LIGHT};
        }}

        QTableWidget {{
            background-color: {cls.BACKGROUND_ELEVATED};
            alternate-background-color: {cls.BACKGROUND};
            color: {cls.TEXT};
            border: 1px solid {cls.BORDER};
            gridline-color: {cls.BORDER};
        }}

        QTableWidget::item {{
            padding: 8px;
            border: none;
        }}

        QTableWidget QLineEdit {{
            padding: 0px 8px;
            border-radius: 0px;
            border: 1px solid {cls.PRIMARY};
            background-color: {cls.BACKGROUND_LIGHT};
        }}

        QTableWidget::item:selected {{
            background-color: {cls.BACKGROUND_HOVER};
            color: {cls.TEXT};
        }}

        QAbstractScrollArea::corner {{
            background-color: {cls.BACKGROUND_ELEVATED};
            border: none;
        }}

        QTableCornerButton::section {{
            background-color: {cls.BACKGROUND_LIGHT};
            border: none;
            border-right: 1px solid {cls.BORDER};
            border-bottom: 1px solid {cls.BORDER};
        }}

        QHeaderView::section {{
            background-color: {cls.BACKGROUND_LIGHT};
            color: {cls.TEXT_MUTED};
            padding: 10px 8px;
            border: none;
            border-right: 1px solid {cls.BORDER};
            border-bottom: 1px solid {cls.BORDER};
            font-size: 12px;
            font-weight: 600;
        }}

        QListWidget {{
            background-color: {cls.BACKGROUND_ELEVATED};
            color: {cls.TEXT};
            border: 1px solid {cls.BORDER};
            padding-top: 8px;
            padding-bottom: 8px;
            outline: none;
        }}

        QListWidget::item {{
            margin: 0 8px 6px 8px;
            padding: 12px 14px;
            border-radius: 10px;
            border: 1px solid transparent;
        }}

        QListWidget::item:selected {{
            background-color: {cls.BACKGROUND_LIGHTER};
            border-color: {cls.PRIMARY};
            color: {cls.TEXT};
        }}

        QListWidget::item:hover:!selected {{
            background-color: {cls.BACKGROUND_LIGHT};
            border-color: {cls.BORDER};
        }}

        QSlider::groove:horizontal {{
            height: 6px;
            background-color: {cls.BACKGROUND_ELEVATED};
            border-radius: 3px;
        }}

        QSlider::handle:horizontal {{
            background-color: {cls.PRIMARY};
            width: 16px;
            margin: -6px 0;
            border-radius: 8px;
            border: 2px solid {cls.BACKGROUND};
        }}

        QSlider::sub-page:horizontal {{
            background-color: {cls.PRIMARY};
            border-radius: 3px;
        }}

        QCheckBox {{
            color: {cls.TEXT};
            spacing: 8px;
        }}

        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid {cls.BORDER};
            background-color: {cls.BACKGROUND_ELEVATED};
        }}

        QCheckBox::indicator:checked {{
            background-color: {cls.PRIMARY};
            border-color: {cls.PRIMARY};
        }}

        QScrollArea {{
            border: none;
            background-color: transparent;
        }}

        QScrollBar:vertical {{
            background-color: {cls.BACKGROUND};
            width: 12px;
            border: none;
            margin: 4px;
        }}

        QScrollBar::handle:vertical {{
            background-color: {cls.BACKGROUND_LIGHTER};
            border-radius: 6px;
            min-height: 30px;
        }}

        QScrollBar::handle:vertical:hover {{
            background-color: {cls.BACKGROUND_HOVER};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        QScrollBar:horizontal {{
            background-color: {cls.BACKGROUND};
            height: 12px;
            border: none;
            margin: 4px;
        }}

        QScrollBar::handle:horizontal {{
            background-color: {cls.BACKGROUND_LIGHTER};
            border-radius: 6px;
            min-width: 30px;
        }}

        QScrollBar::handle:horizontal:hover {{
            background-color: {cls.BACKGROUND_HOVER};
        }}

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}

        QSplitter::handle {{
            background-color: {cls.BORDER};
            width: 1px;
        }}

        QMainWindow::separator {{
            background-color: {cls.BORDER};
            height: 3px;
        }}

        QMainWindow::separator:hover {{
            background-color: {cls.PRIMARY};
        }}

        QDialog, QInputDialog {{
            background-color: {cls.BACKGROUND};
            color: {cls.TEXT};
        }}

        QLabel {{
            color: {cls.TEXT};
            background: transparent;
        }}

        QMenu {{
            background-color: {cls.BACKGROUND_LIGHT};
            color: {cls.TEXT};
            border: 1px solid {cls.BORDER};
            border-radius: 10px;
            padding: 6px;
        }}

        QMenu::item {{
            padding: 8px 12px;
            border-radius: 6px;
        }}

        QMenu::item:selected {{
            background-color: {cls.BACKGROUND_HOVER};
        }}

        QToolTip {{
            background-color: {cls.BACKGROUND_LIGHT};
            color: {cls.TEXT};
            border: 1px solid {cls.BORDER};
            padding: 6px 8px;
        }}
    """

    @staticmethod
    def title_style(size: int = 18, extra: str = "") -> str:
        """Style for section and editor titles."""
        return f"font-size: {size}px; font-weight: 700; {extra}"

    @staticmethod
    def subtle_text_style(size: int = 12, extra: str = "") -> str:
        """Style for secondary text."""
        return f"color: {Styles.TEXT_MUTED}; font-size: {size}px; {extra}"

    @staticmethod
    def widget_panel_style(selector: str | None = None) -> str:
        """Surface treatment for standalone panels."""
        body = f"""
            background-color: {Styles.BACKGROUND_ELEVATED};
            border: 1px solid {Styles.BORDER};
            border-radius: 14px;
        """
        if selector:
            return f"{selector} {{{body}}}"
        return body

    @staticmethod
    def combobox_style() -> str:
        """Dark-theme QComboBox (field, arrow, and popup list)."""
        return f"""
            QComboBox {{
                background-color: {Styles.BACKGROUND_ELEVATED};
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }}
            QComboBox QLineEdit::placeholder {{
                color: {Styles.TEXT_SUBTLE};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {Styles.TEXT_MUTED};
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Styles.BACKGROUND_ELEVATED};
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                selection-background-color: {Styles.PRIMARY};
            }}
        """

    @staticmethod
    def soundboard_button_style(playing: bool) -> str:
        """Style for a soundboard trigger button; highlighted while playing."""
        if playing:
            return f"""
                QPushButton {{
                    background-color: {Styles.BACKGROUND_HOVER};
                    color: {Styles.TEXT};
                    border: 1px solid {Styles.PRIMARY};
                    border-radius: 8px;
                    padding: 0 10px;
                    text-align: left;
                    font-weight: 600;
                }}
            """
        return f"""
            QPushButton {{
                background-color: {Styles.BACKGROUND_LIGHT};
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                border-radius: 8px;
                padding: 0 10px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {Styles.BACKGROUND_LIGHTER};
                border-color: {Styles.BORDER_STRONG};
            }}
            QPushButton:pressed {{
                background-color: {Styles.BACKGROUND_HOVER};
            }}
        """

    @staticmethod
    def dock_title_bar_style(selector: str) -> str:
        """Flat full-width surface for a dock's custom title bar."""
        return f"""
            {selector} {{
                background-color: {Styles.BACKGROUND_ELEVATED};
                border-top: 1px solid {Styles.BORDER};
            }}
        """

    @staticmethod
    def card_frame_style(
        selector: str,
        accent_color: str | None = None,
        border_color: str | None = None,
        background_color: str | None = None,
    ) -> str:
        """Surface treatment for card-like frames."""
        border = border_color or accent_color or Styles.BORDER
        background = background_color or Styles.BACKGROUND_LIGHT
        accent_rule = f"border-left: 4px solid {accent_color};" if accent_color else ""
        padding_left = "padding-left: 10px;" if accent_color else ""
        return f"""
            {selector} {{
                background-color: {background};
                border: 1px solid {border};
                border-radius: 14px;
                padding: 10px;
                {accent_rule}
                {padding_left}
            }}
        """

    @staticmethod
    def tag_badge_style(
        color: str, border_color: str | None = None, border_style: str = "solid"
    ) -> str:
        """Generate stylesheet for a tag badge."""
        border = border_color or "transparent"
        width = "2px" if border_color else "1px"
        return f"""
            background-color: {color};
            color: {Styles.contrast_text_color(color)};
            padding: 3px 10px;
            border-radius: 11px;
            min-height: 18px;
            font-size: 11px;
            font-weight: 700;
            border: {width} {border_style} {border};
        """

    @staticmethod
    def tag_badge_excluded_style() -> str:
        """Style for a tag badge excluded from the filter (NOT this tag)."""
        return f"""
            background-color: {Styles.BACKGROUND_LIGHTER};
            color: {Styles.TEXT_SUBTLE};
            text-decoration: line-through;
            padding: 3px 10px;
            border-radius: 11px;
            min-height: 18px;
            font-size: 11px;
            font-weight: 700;
            border: 2px solid {Styles.BORDER_STRONG};
        """

    @staticmethod
    def tag_remove_button_style(color: str) -> str:
        """Style for a tag badge remove button."""
        return f"""
            QPushButton {{
                background-color: {color};
                color: {Styles.contrast_text_color(color)};
                border: 1px solid {Styles.tint(Styles.contrast_text_color(color), 0.25)};
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 0;
                margin-left: -4px;
            }}
            QPushButton:hover {{
                background-color: {Styles.DANGER};
                border-color: {Styles.DANGER};
            }}
        """

    @staticmethod
    def playback_button_style(is_active: bool) -> str:
        """Style for primary play and pause actions."""
        background = Styles.WARNING if is_active else Styles.SUCCESS
        hover = Styles.WARNING_DARK if is_active else Styles.SUCCESS_DARK
        text_color = Styles.contrast_text_color(background)
        return f"""
            QPushButton {{
                background-color: {background};
                color: {text_color};
                border: none;
                border-radius: 12px;
                padding: 11px 18px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:disabled {{
                background-color: {Styles.BACKGROUND_LIGHT};
                color: {Styles.TEXT_SUBTLE};
                border: 1px solid {Styles.BORDER};
            }}
        """

    @staticmethod
    def play_button_style(size: int = 32) -> str:
        """Style for small active transport buttons."""
        radius = size // 2
        return f"""
            QPushButton {{
                background-color: {Styles.SUCCESS};
                color: {Styles.contrast_text_color(Styles.SUCCESS)};
                min-width: {size}px;
                max-width: {size}px;
                min-height: {size}px;
                max-height: {size}px;
                border: none;
                border-radius: {radius}px;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {Styles.SUCCESS_DARK};
            }}
        """

    @staticmethod
    def play_button_inactive_style(size: int = 32) -> str:
        """Style for small inactive transport buttons."""
        radius = size // 2
        return f"""
            QPushButton {{
                background-color: {Styles.BACKGROUND_LIGHTER};
                color: {Styles.TEXT_MUTED};
                min-width: {size}px;
                max-width: {size}px;
                min-height: {size}px;
                max-height: {size}px;
                border-radius: {radius}px;
                border: 1px solid {Styles.BORDER};
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {Styles.BACKGROUND_HOVER};
            }}
        """

    @staticmethod
    def toggle_on_style(radius: int = 8, extra: str = "") -> str:
        """Style for active toggle buttons."""
        return f"""
            QPushButton {{
                background-color: {Styles.PRIMARY};
                color: {Styles.contrast_text_color(Styles.PRIMARY)};
                border: none;
                border-radius: {radius}px;
                padding: 6px 12px;
                font-weight: 700;
                {extra}
            }}
            QPushButton:hover {{
                background-color: {Styles.PRIMARY_DARK};
            }}
        """

    @staticmethod
    def toggle_off_style(radius: int = 8, extra: str = "") -> str:
        """Style for inactive toggle buttons."""
        return f"""
            QPushButton {{
                background-color: {Styles.BACKGROUND_LIGHTER};
                color: {Styles.TEXT_MUTED};
                border: 1px solid {Styles.BORDER};
                border-radius: {radius}px;
                padding: 6px 12px;
                font-weight: 700;
                {extra}
            }}
            QPushButton:hover {{
                background-color: {Styles.BACKGROUND_HOVER};
                border-color: {Styles.BORDER_STRONG};
            }}
        """

    @staticmethod
    def icon_toggle_button_style(active: bool, size: int = 28) -> str:
        """Style for compact icon-only toggle buttons."""
        radius = size // 2
        background = Styles.PRIMARY if active else Styles.BACKGROUND_LIGHTER
        border = Styles.PRIMARY if active else Styles.BORDER
        hover = Styles.PRIMARY_DARK if active else Styles.BACKGROUND_HOVER
        color = (
            Styles.contrast_text_color(Styles.PRIMARY) if active else Styles.TEXT_MUTED
        )
        return f"""
            QPushButton {{
                background-color: {background};
                color: {color};
                min-width: {size}px;
                max-width: {size}px;
                min-height: {size}px;
                max-height: {size}px;
                border: 1px solid {border};
                border-radius: {radius}px;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {hover};
                border-color: {hover};
            }}
        """

    @staticmethod
    def secondary_button_style(compact: bool = False) -> str:
        """Style for non-primary action buttons."""
        padding = "7px 10px" if compact else "9px 16px"
        radius = 10 if compact else 12
        return f"""
            QPushButton {{
                background-color: {Styles.BACKGROUND_LIGHTER};
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                border-radius: {radius}px;
                padding: {padding};
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {Styles.BACKGROUND_HOVER};
                border-color: {Styles.BORDER_STRONG};
            }}
        """

    @staticmethod
    def compact_icon_button_style() -> str:
        """Style for compact icon-only utility buttons."""
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {Styles.TEXT_MUTED};
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {Styles.BACKGROUND_LIGHT};
                border-color: {Styles.BORDER};
            }}
            QPushButton:checked {{
                background-color: {Styles.BACKGROUND_HOVER};
                border-color: {Styles.PRIMARY};
                color: {Styles.TEXT};
            }}
        """

    @staticmethod
    def remove_button_style() -> str:
        """Style for subtle remove buttons."""
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {Styles.TEXT_SUBTLE};
                border: none;
                font-size: 18px;
                font-weight: 700;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {Styles.DANGER};
                background-color: {Styles.tint(Styles.DANGER, 0.12)};
            }}
        """

    @staticmethod
    def ghost_button_style() -> str:
        """Style for link-like text buttons."""
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {Styles.TEXT};
                border: none;
                padding: 0;
                text-align: left;
                font-weight: 700;
            }}
            QPushButton:hover {{
                color: {Styles.PRIMARY};
                background-color: transparent;
            }}
        """

    @staticmethod
    def empty_state_style(active: bool = False) -> str:
        """Style for empty and drop target states."""
        border = Styles.PRIMARY if active else Styles.BORDER
        text = Styles.PRIMARY if active else Styles.TEXT_MUTED
        background = (
            Styles.tint(Styles.PRIMARY, 0.12) if active else Styles.BACKGROUND_ELEVATED
        )
        return f"""
            color: {text};
            font-size: 13px;
            padding: 32px;
            border: 2px dashed {border};
            border-radius: 16px;
            background-color: {background};
        """

    @staticmethod
    def title_input_style(size: int = 18) -> str:
        """Style for inline title editing fields."""
        return f"""
            QLineEdit {{
                background-color: {Styles.BACKGROUND_LIGHT};
                border: 1px solid {Styles.BORDER_STRONG};
                border-radius: 12px;
                padding: 8px 12px;
                font-size: {size}px;
                font-weight: 700;
            }}
            QLineEdit:focus {{
                border-color: {Styles.PRIMARY};
            }}
        """

    @staticmethod
    def small_play_button_style() -> str:
        """Style for tiny library preview buttons."""
        return f"""
            QPushButton {{
                background-color: {Styles.SUCCESS};
                color: {Styles.contrast_text_color(Styles.SUCCESS)};
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                border-radius: 10px;
                border: none;
                padding: 0 0 0 1px;
            }}
            QPushButton:hover {{
                background-color: {Styles.SUCCESS_DARK};
            }}
        """

    @staticmethod
    def small_stop_button_style() -> str:
        """Style for tiny library stop buttons."""
        return f"""
            QPushButton {{
                background-color: {Styles.DANGER};
                color: {Styles.contrast_text_color(Styles.DANGER)};
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                border-radius: 10px;
                border: none;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {Styles.DANGER_DARK};
            }}
        """


# Populate the active palette tokens at import time.
Styles.set_theme("dark")
