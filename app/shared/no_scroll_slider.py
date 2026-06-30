"""A QSlider that stays out of the way of keyboard and wheel navigation."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSlider, QWidget


class NoScrollSlider(QSlider):
    """A value slider that doesn't grab keyboard focus or mouse-wheel scrolling.

    The volume and position sliders live inside a scrollable list of cards, where
    a plain ``QSlider`` misbehaves in two ways:

    * it takes keyboard focus when clicked, so the playback arrow-key shortcuts
      get redirected into nudging whichever slider was last touched; and
    * it consumes wheel events whenever the pointer is over it, so scrolling the
      list snags on the slider sitting under the cursor.

    This subclass drops keyboard focus (``NoFocus``) and forwards the wheel to
    its parent (the scroll area) so the list keeps scrolling. Set the value by
    dragging the handle or clicking the groove.
    """

    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        parent: QWidget | None = None,
    ):
        super().__init__(orientation, parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def wheelEvent(self, event):
        # Ignore so the wheel propagates to the parent scroll area instead of
        # changing this slider's value.
        event.ignore()
