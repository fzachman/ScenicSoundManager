"""Application styling constants and stylesheets"""

from typing import Optional


class Styles:
    """Application-wide style constants and stylesheets"""

    # Color palette
    PRIMARY = "#4A90D9"
    PRIMARY_DARK = "#3A7BC8"
    SECONDARY = "#6C757D"
    SUCCESS = "#28A745"
    WARNING = "#FFC107"
    DANGER = "#DC3545"

    BACKGROUND = "#2D2D2D"
    BACKGROUND_LIGHT = "#3D3D3D"
    BACKGROUND_LIGHTER = "#4D4D4D"
    TEXT = "#FFFFFF"
    TEXT_MUTED = "#AAAAAA"
    BORDER = "#555555"

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

    # Main application stylesheet
    APP_STYLESHEET = f"""
        QMainWindow, QWidget {{
            background-color: {BACKGROUND};
            color: {TEXT};
        }}

        QTabWidget::pane {{
            border: 1px solid {BORDER};
            background-color: {BACKGROUND};
        }}

        QTabBar::tab {{
            background-color: {BACKGROUND_LIGHT};
            color: {TEXT};
            padding: 10px 20px;
            border: 1px solid {BORDER};
            border-bottom: none;
            margin-right: 2px;
        }}

        QTabBar::tab:selected {{
            background-color: {PRIMARY};
            color: {TEXT};
        }}

        QTabBar::tab:hover {{
            background-color: {BACKGROUND_LIGHTER};
        }}

        QPushButton {{
            background-color: {PRIMARY};
            color: {TEXT};
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }}

        QPushButton:hover {{
            background-color: {PRIMARY_DARK};
        }}

        QPushButton:pressed {{
            background-color: #2A6BB8;
        }}

        QPushButton:disabled {{
            background-color: {SECONDARY};
            color: {TEXT_MUTED};
        }}

        QLineEdit {{
            background-color: {BACKGROUND_LIGHT};
            color: {TEXT};
            border: 1px solid {BORDER};
            padding: 8px;
            border-radius: 4px;
        }}

        QLineEdit:focus {{
            border-color: {PRIMARY};
        }}

        QTableWidget {{
            background-color: {BACKGROUND};
            color: {TEXT};
            border: 1px solid {BORDER};
            gridline-color: {BORDER};
        }}

        QTableWidget::item {{
            padding: 8px;
        }}

        QTableWidget::item:selected {{
            background-color: {PRIMARY};
        }}

        QHeaderView::section {{
            background-color: {BACKGROUND_LIGHT};
            color: {TEXT};
            padding: 8px;
            border: none;
            border-right: 1px solid {BORDER};
            border-bottom: 1px solid {BORDER};
        }}

        QListWidget {{
            background-color: {BACKGROUND};
            color: {TEXT};
            border: 1px solid {BORDER};
        }}

        QListWidget::item {{
            padding: 8px;
        }}

        QListWidget::item:selected {{
            background-color: {PRIMARY};
        }}

        QListWidget::item:hover {{
            background-color: {BACKGROUND_LIGHTER};
        }}

        QSlider::groove:horizontal {{
            height: 8px;
            background-color: {BACKGROUND_LIGHT};
            border-radius: 4px;
        }}

        QSlider::handle:horizontal {{
            background-color: {PRIMARY};
            width: 16px;
            margin: -4px 0;
            border-radius: 8px;
        }}

        QSlider::sub-page:horizontal {{
            background-color: {PRIMARY};
            border-radius: 4px;
        }}

        QCheckBox {{
            color: {TEXT};
            spacing: 8px;
        }}

        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 3px;
            border: 1px solid {BORDER};
            background-color: {BACKGROUND_LIGHT};
        }}

        QCheckBox::indicator:checked {{
            background-color: {PRIMARY};
            border-color: {PRIMARY};
        }}

        QScrollBar:vertical {{
            background-color: {BACKGROUND};
            width: 12px;
            border: none;
        }}

        QScrollBar::handle:vertical {{
            background-color: {BACKGROUND_LIGHTER};
            border-radius: 6px;
            min-height: 30px;
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        QScrollBar:horizontal {{
            background-color: {BACKGROUND};
            height: 12px;
            border: none;
        }}

        QScrollBar::handle:horizontal {{
            background-color: {BACKGROUND_LIGHTER};
            border-radius: 6px;
            min-width: 30px;
        }}

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}

        QSplitter::handle {{
            background-color: {BORDER};
        }}

        QDialog {{
            background-color: {BACKGROUND};
            color: {TEXT};
        }}

        QInputDialog {{
            background-color: {BACKGROUND};
            color: {TEXT};
        }}

        QLabel {{
            color: {TEXT};
        }}

        QMenu {{
            background-color: {BACKGROUND_LIGHT};
            color: {TEXT};
            border: 1px solid {BORDER};
        }}

        QMenu::item:selected {{
            background-color: {PRIMARY};
        }}
    """

    @staticmethod
    def tag_badge_style(color: str, border_color: Optional[str] = None) -> str:
        """Generate stylesheet for a tag badge"""
        border = (
            f"border: 2px solid {border_color};"
            if border_color
            else "border: 1px solid transparent;"
        )
        return f"""
            background-color: {color};
            color: white;
            padding: 1px 8px;
            border-radius: 9px;
            min-height: 16px;
            font-size: 11px;
            font-weight: bold;
            {border}
        """

    @staticmethod
    def play_button_style() -> str:
        """Style for play buttons"""
        return f"""
            QPushButton {{
                background-color: {Styles.SUCCESS};
                color: white;
                min-width: 30px;
                max-width: 30px;
                min-height: 30px;
                max-height: 30px;
                border-radius: 15px;
            }}
            QPushButton:hover {{
                background-color: #218838;
            }}
        """

    @staticmethod
    def stop_button_style() -> str:
        """Style for stop buttons"""
        return f"""
            QPushButton {{
                background-color: {Styles.DANGER};
                color: white;
                min-width: 30px;
                max-width: 30px;
                min-height: 30px;
                max-height: 30px;
                border-radius: 15px;
            }}
            QPushButton:hover {{
                background-color: #C82333;
            }}
        """

    @staticmethod
    def small_play_button_style() -> str:
        """Style for small play buttons"""
        return f"""
            QPushButton {{
                background-color: {Styles.SUCCESS};
                color: white;
                min-width: 16px;
                max-width: 16px;
                min-height: 16px;
                max-height: 16px;
                border-radius: 8px;
                padding: 0 0 0 1px;
            }}
            QPushButton:hover {{
                background-color: #218838;
            }}
        """

    @staticmethod
    def small_stop_button_style() -> str:
        """Style for small stop buttons"""
        return f"""
            QPushButton {{
                background-color: {Styles.DANGER};
                color: white;
                min-width: 16px;
                max-width: 16px;
                min-height: 16px;
                max-height: 16px;
                border-radius: 8px;
                padding: 0 0 0 1px;
            }}
            QPushButton:hover {{
                background-color: #C82333;
            }}
        """
