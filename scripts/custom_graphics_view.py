from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtCore import Qt

class CustomGraphicsView(QGraphicsView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event: QMouseEvent):
        grabbed = self.scene().mouseGrabberItem()
        if grabbed:
            # Map the view's mouse position to scene coordinates.
            scene_pos = self.mapToScene(event.pos())
            # Then map the scene position to the grabbed item's local coordinates.
            local_pos = grabbed.mapFromScene(scene_pos)
            # Create a new fake QMouseEvent with the local coordinates.
            fake_event = QMouseEvent(
                event.type(),
                local_pos,
                event.globalPosition(),
                event.button(),
                event.buttons(),
                event.modifiers()
            )
            grabbed.mouseMoveEvent(fake_event)
            event.accept()
        else:
            super().mouseMoveEvent(event)
