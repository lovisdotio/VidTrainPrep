# custom_graphics_scene.py
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtGui import QPen, QBrush, QColor
from PyQt6.QtCore import QRectF
from scripts.interactive_crop_region import InteractiveCropRegion  # Import the new class

class CustomGraphicsScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.crop_item = None
        self.start_point = None
        self.temp_rect_item = None
        self.aspect_ratio = None  # Aspect ratio constraint (e.g., 16/9)

    def set_aspect_ratio(self, ratio):
        """Set the aspect ratio constraint for the scene."""
        self.aspect_ratio = ratio
        if self.crop_item:
            # Update the crop item's aspect ratio.
            self.crop_item.aspect_ratio = ratio

    def mousePressEvent(self, event):
        # If an existing crop item exists and the click is near it, let it handle the event.
        if self.crop_item:
            tolerance = 10  # pixels tolerance for selection
            region_scene_rect = self.crop_item.sceneBoundingRect()
            inflated_rect = region_scene_rect.adjusted(-tolerance, -tolerance, tolerance, tolerance)
            if inflated_rect.contains(event.scenePos()):
                super().mousePressEvent(event)
                return
            else:
                # Otherwise, remove the existing crop region.
                self.removeItem(self.crop_item)
                self.crop_item = None

        # Start creating a new crop region.
        self.start_point = event.scenePos()
        self.temp_rect_item = self.addRect(QRectF(self.start_point, self.start_point),
                                           QPen(QColor(255, 0, 0), 2),
                                           QBrush(QColor(255, 0, 0, 30)))
        event.accept()

    def mouseMoveEvent(self, event):
        scene_pos = event.scenePos()
        # If a crop region exists and the mouse is inside it, let it handle the event.
        if self.crop_item and self.crop_item.contains(scene_pos):
            super().mouseMoveEvent(event)
            return

        # If we are drawing a new crop region:
        if self.start_point and self.temp_rect_item:
            current_point = scene_pos
            rect = QRectF(self.start_point, current_point).normalized()

            # Apply aspect ratio constraint if one is set.
            if self.aspect_ratio is not None:
                current_width = rect.width()
                current_height = rect.height() if rect.height() != 0 else 1
                if current_width / current_height > self.aspect_ratio:
                    rect.setWidth(current_height * self.aspect_ratio)
                else:
                    rect.setHeight(current_width / self.aspect_ratio)

            # Clamp the rectangle to the scene bounds.
            scene_rect = self.sceneRect()
            if rect.right() > scene_rect.right():
                rect.setRight(scene_rect.right())
            if rect.bottom() > scene_rect.bottom():
                rect.setBottom(scene_rect.bottom())
            if rect.left() < scene_rect.left():
                rect.setLeft(scene_rect.left())
            if rect.top() < scene_rect.top():
                rect.setTop(scene_rect.top())

            self.temp_rect_item.setRect(rect)
            # Optionally notify the parent of ongoing updates.
            if hasattr(self.parent_widget, "crop_rect_updating"):
                self.parent_widget.crop_rect_updating(rect)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.start_point and self.temp_rect_item:
            # Finalize the new crop region.
            rect = self.temp_rect_item.rect().normalized()
            self.removeItem(self.temp_rect_item)
            self.temp_rect_item = None
            self.start_point = None

            if rect.width() >= 20 and rect.height() >= 20:
                # Create the new interactive crop region.
                self.crop_item = InteractiveCropRegion(rect, aspect_ratio=self.aspect_ratio)
                self.addItem(self.crop_item)
                if hasattr(self.parent_widget, "crop_rect_finalized"):
                    self.parent_widget.crop_rect_finalized(self.crop_item.sceneBoundingRect())
            event.accept()
        else:
            super().mouseReleaseEvent(event)
