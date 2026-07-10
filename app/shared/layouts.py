"""Helpers for safely clearing dynamic Qt layouts."""

from PyQt6.QtWidgets import QLayout


def clear_layout(layout: QLayout, keep_trailing_items: int = 0) -> None:
    """Remove child widgets from a layout and detach them from the parent tree."""
    while layout.count() > keep_trailing_items:
        item = layout.takeAt(0)
        if item is None:
            continue
        widget = item.widget()
        child_layout = item.layout()

        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)
