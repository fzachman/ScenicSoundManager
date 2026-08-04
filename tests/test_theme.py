"""Tests for the theme system: palette swap, style helpers, ThemeManager,
and tinted icon rendering."""

import pytest
from PyQt6.QtCore import QSettings

from app.shared.icons import IconLibrary
from app.shared.styles import Styles
from app.shared.theme import (
    DEFAULT_THEME,
    SETTINGS_THEME_KEY,
    ThemeManager,
    theme_manager,
)


@pytest.fixture(autouse=True)
def reset_theme(qapp):
    """Restore the dark theme and clear the persisted choice after each test."""
    yield
    QSettings().remove(SETTINGS_THEME_KEY)
    Styles.set_theme(DEFAULT_THEME)


class TestStylesPalette:
    def test_set_theme_swaps_tokens(self):
        dark_background = Styles.BACKGROUND
        Styles.set_theme("light")
        assert Styles.BACKGROUND == Styles.LIGHT_PALETTE["BACKGROUND"]
        assert Styles.active_theme == "light"
        Styles.set_theme("dark")
        assert Styles.BACKGROUND == dark_background

    def test_unknown_theme_falls_back_to_dark(self):
        Styles.set_theme("solarized")
        assert Styles.active_theme == "dark"
        assert Styles.PRIMARY == Styles.DARK_PALETTE["PRIMARY"]

    def test_palettes_define_identical_token_sets(self):
        assert set(Styles.DARK_PALETTE) == set(Styles.LIGHT_PALETTE)

    def test_app_stylesheet_follows_active_palette(self):
        assert Styles.DARK_PALETTE["BACKGROUND"] in Styles.app_stylesheet()
        Styles.set_theme("light")
        sheet = Styles.app_stylesheet()
        assert Styles.LIGHT_PALETTE["BACKGROUND"] in sheet
        assert Styles.DARK_PALETTE["BACKGROUND"] not in sheet

    def test_style_helpers_follow_active_palette(self):
        Styles.set_theme("light")
        assert Styles.LIGHT_PALETTE["BACKGROUND_ELEVATED"] in Styles.combobox_style()


class TestStyleHelpers:
    def test_tint_converts_hex_to_rgba(self):
        assert Styles.tint("#F36B6B", 0.12) == "rgba(243, 107, 107, 0.12)"

    def test_contrast_text_color_light_background(self):
        assert Styles.contrast_text_color("#FFF176") == "#11161C"

    def test_contrast_text_color_dark_background(self):
        assert Styles.contrast_text_color("#41C784") == "#FFFFFF"


class TestThemeManager:
    def test_set_theme_emits_after_swap(self, qapp):
        received = []
        theme_manager.theme_changed.connect(received.append)
        try:
            theme_manager.set_theme("light")
            assert received == ["light"]
            assert Styles.active_theme == "light"
        finally:
            theme_manager.theme_changed.disconnect(received.append)

    def test_set_theme_noop_for_active_theme(self, qapp):
        received = []
        theme_manager.theme_changed.connect(received.append)
        try:
            theme_manager.set_theme(Styles.active_theme)
            assert received == []
        finally:
            theme_manager.theme_changed.disconnect(received.append)

    def test_saved_theme_defaults_and_validates(self, qapp):
        assert ThemeManager.saved_theme() == DEFAULT_THEME
        QSettings().setValue(SETTINGS_THEME_KEY, "garbage")
        assert ThemeManager.saved_theme() == DEFAULT_THEME

    def test_save_and_apply_persists_and_applies(self, qapp):
        theme_manager.save_and_apply("light")
        assert QSettings().value(SETTINGS_THEME_KEY, type=str) == "light"
        assert Styles.active_theme == "light"

    def test_apply_saved_theme_is_silent(self, qapp):
        QSettings().setValue(SETTINGS_THEME_KEY, "light")
        received = []
        theme_manager.theme_changed.connect(received.append)
        try:
            theme_manager.apply_saved_theme()
            assert Styles.active_theme == "light"
            assert received == []
        finally:
            theme_manager.theme_changed.disconnect(received.append)


class TestIconTinting:
    def test_icon_renders_non_null(self, qapp):
        icon = IconLibrary().icon("play-solid")
        assert not icon.isNull()

    def test_missing_icon_returns_null_icon(self, qapp):
        assert IconLibrary().icon("does-not-exist").isNull()

    def test_same_name_and_color_is_cached(self, qapp):
        library = IconLibrary()
        assert library.icon("plus", "#FF0000") is library.icon("plus", "#FF0000")

    def test_different_colors_render_distinct_icons(self, qapp):
        library = IconLibrary()
        assert library.icon("plus", "#FF0000") is not library.icon("plus", "#00FF00")

    def test_default_color_follows_theme(self, qapp):
        library = IconLibrary()
        dark_icon = library.icon("plus")
        Styles.set_theme("light")
        assert library.icon("plus") is not dark_icon
