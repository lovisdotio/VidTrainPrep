# interactive_crop_region.py
from PyQt6.QtWidgets import QGraphicsRectItem, QStyleOptionGraphicsItem, QWidget
from PyQt6.QtGui import QPen, QBrush, QColor, QMouseEvent, QWheelEvent, QPainter
from PyQt6.QtCore import QRectF, Qt, QPointF

class InteractiveCropRegion(QGraphicsRectItem):
    HANDLE_SIZE = 8
    MIN_SIZE = 20

    def __init__(self, rect: QRectF, aspect_ratio: float = None, parent=None):
        """
        rect: initial rectangle in local coordinates.
        aspect_ratio: if set, enforces width/height ratio (e.g. 16/9); if None, freeform.
        """
        super().__init__(rect, parent)
        self.aspect_ratio = aspect_ratio
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        # Enable focus so wheel events are received.
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setPen(QPen(QColor("red"), 2))
        self.setBrush(QBrush(QColor(165, 0, 0, 30)))
        
        # Internal state for resizing
        self.active_handle = None  # "top_left", "top_right", "bottom_left", or "bottom_right"
        self.resizing = False
        self.start_rect = QRectF()
        self.start_mouse_pos = QPointF()
        # Store the offset between the scenePos and the item's position during dragging.
        self._drag_offset = QPointF()
        
        self.handle_positions = {}
        self.updateHandlePositions()


    def boundingRect(self) -> QRectF:
        """Return the area that needs to be repainted (including handles)."""
        rect = self.rect()
        extra = self.HANDLE_SIZE / 2
        return rect.adjusted(-extra, -extra, extra, extra)

    def updateHandlePositions(self):
        """Compute small square handles at the four corners of the crop rect."""
        r = self.rect()
        s = self.HANDLE_SIZE
        half = s / 2
        self.handle_positions = {
            "top_left": QRectF(r.left() - half, r.top() - half, s, s),
            "top_right": QRectF(r.right() - half, r.top() - half, s, s),
            "bottom_left": QRectF(r.left() - half, r.bottom() - half, s, s),
            "bottom_right": QRectF(r.right() - half, r.bottom() - half, s, s)
        }
        # Request a repaint for the whole bounding rect
        self.update()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        painter.setPen(self.pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())
        painter.setBrush(QBrush(QColor("red")))
        for handle_rect in self.handle_positions.values():
            painter.drawRect(handle_rect)
            painter.drawRect(handle_rect)
            painter.drawRect(handle_rect)

    def hoverMoveEvent(self, event: QMouseEvent):
        pos = QPointF(event.pos())
        handle = self.getHandleAt(pos)
        if handle:
            if handle in ("top_left", "bottom_right"):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif handle in ("top_right", "bottom_left"):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        event.accept()

    def getHandleAt(self, pos: QPointF):
        for name, rect in self.handle_positions.items():
            if rect.contains(pos):
                return name
        return None

    def mousePressEvent(self, event: QMouseEvent):
        pos_local = QPointF(event.pos())
        handle = self.getHandleAt(pos_local)
        if handle:
            self.active_handle = handle
            self.resizing = True
            self.start_rect = QRectF(self.rect())
            self.start_mouse_pos = pos_local
        else:
            self.resizing = False
            self._drag_offset = self.mapToScene(QPointF(event.pos())) - self.scenePos()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.resizing and self.active_handle:
            current_pos = QPointF(event.pos())
            delta = current_pos - self.start_mouse_pos
            new_rect = QRectF(self.start_rect)
            if self.active_handle == "top_left":
                fixed = self.start_rect.bottomRight()
                new_top_left = self.start_rect.topLeft() + delta
                if self.aspect_ratio:
                    candidate_width = fixed.x() - new_top_left.x()
                    candidate_height = fixed.y() - new_top_left.y()
                    if candidate_width / candidate_height > self.aspect_ratio:
                        candidate_width = candidate_height * self.aspect_ratio
                    else:
                        candidate_height = candidate_width / self.aspect_ratio
                    new_top_left = QPointF(fixed.x() - candidate_width, fixed.y() - candidate_height)
                new_rect.setTopLeft(new_top_left)
            elif self.active_handle == "top_right":
                fixed = self.start_rect.bottomLeft()
                new_top_right = self.start_rect.topRight() + delta
                if self.aspect_ratio:
                    candidate_width = new_top_right.x() - fixed.x()
                    candidate_height = fixed.y() - new_top_right.y()
                    if candidate_width / candidate_height > self.aspect_ratio:
                        candidate_width = candidate_height * self.aspect_ratio
                    else:
                        candidate_height = candidate_width / self.aspect_ratio
                    new_top_right = QPointF(fixed.x() + candidate_width, fixed.y() - candidate_height)
                new_rect.setTopRight(new_top_right)
            elif self.active_handle == "bottom_left":
                fixed = self.start_rect.topRight()
                new_bottom_left = self.start_rect.bottomLeft() + delta
                if self.aspect_ratio:
                    candidate_width = fixed.x() - new_bottom_left.x()
                    candidate_height = new_bottom_left.y() - fixed.y()
                    if candidate_width / candidate_height > self.aspect_ratio:
                        candidate_width = candidate_height * self.aspect_ratio
                    else:
                        candidate_height = candidate_width / self.aspect_ratio
                    new_bottom_left = QPointF(fixed.x() - candidate_width, fixed.y() + candidate_height)
                new_rect.setBottomLeft(new_bottom_left)
            elif self.active_handle == "bottom_right":
                fixed = self.start_rect.topLeft()
                new_bottom_right = self.start_rect.bottomRight() + delta
                if self.aspect_ratio:
                    candidate_width = new_bottom_right.x() - fixed.x()
                    candidate_height = new_bottom_right.y() - fixed.y()
                    if candidate_width / candidate_height > self.aspect_ratio:
                        candidate_width = candidate_height * self.aspect_ratio
                    else:
                        candidate_height = candidate_width / self.aspect_ratio
                    new_bottom_right = QPointF(fixed.x() + candidate_width, fixed.y() + candidate_height)
                new_rect.setBottomRight(new_bottom_right)
            if new_rect.width() < self.MIN_SIZE or new_rect.height() < self.MIN_SIZE:
                new_rect = self.rect()
            scene_rect = self.scene().sceneRect()
            new_scene_rect = self.mapRectToScene(new_rect)
            dx, dy = 0, 0
            if new_scene_rect.left() < scene_rect.left():
                dx = scene_rect.left() - new_scene_rect.left()
            if new_scene_rect.top() < scene_rect.top():
                dy = scene_rect.top() - new_scene_rect.top()
            if new_scene_rect.right() > scene_rect.right():
                dx = scene_rect.right() - new_scene_rect.right()
            if new_scene_rect.bottom() > scene_rect.bottom():
                dy = scene_rect.bottom() - new_scene_rect.bottom()
            if dx or dy:
                new_scene_rect.translate(dx, dy)
                new_rect = self.mapRectFromScene(new_scene_rect)
            self.setRect(new_rect.normalized())
            self.updateHandlePositions()
            event.accept()
            if hasattr(self.scene().parent_widget, "crop_rect_updating"):
                self.scene().parent_widget.crop_rect_updating(self.sceneBoundingRect())
        else:
            new_scene_pos = self.mapToScene(QPointF(event.pos()))
            new_pos = new_scene_pos - self._drag_offset
            self.setPos(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.clamp_to_scene_bounds()
        event.accept()
        if hasattr(self.scene().parent_widget, "crop_rect_finalized"):
            self.scene().parent_widget.crop_rect_finalized(self.sceneBoundingRect())

    def clamp_to_scene_bounds(self):
        """Adjusts the crop region's position to be fully inside the scene bounds."""
        scene_rect = self.scene().sceneRect()
        crop_rect = self.sceneBoundingRect()
        dx, dy = 0, 0
        if crop_rect.left() < scene_rect.left():
            dx = scene_rect.left() - crop_rect.left()
        if crop_rect.top() < scene_rect.top():
            dy = scene_rect.top() - crop_rect.top()
        if crop_rect.right() > scene_rect.right():
            dx = scene_rect.right() - crop_rect.right()
        if crop_rect.bottom() > scene_rect.bottom():
            dy = scene_rect.bottom() - crop_rect.bottom()
        if dx or dy:
            self.moveBy(dx, dy)

    def wheelEvent(self, event: QWheelEvent):
        if hasattr(event, "angleDelta"):
            delta_val = event.angleDelta().y()
        elif hasattr(event, "pixelDelta"):
            delta_val = event.pixelDelta().y()
        else:
            delta_val = 0
        scale_factor = 1 + (delta_val / 120) * 0.1
        current_rect = self.rect()
        center = current_rect.center()
        new_width = current_rect.width() * scale_factor
        new_height = current_rect.height() * scale_factor
        if new_width < self.MIN_SIZE or new_height < self.MIN_SIZE:
            event.ignore()
            return
        if self.aspect_ratio:
            new_height = new_width / self.aspect_ratio
        new_rect = QRectF(
            center.x() - new_width / 2,
            center.y() - new_height / 2,
            new_width,
            new_height
        )
        scene_rect = self.scene().sceneRect()
        new_scene_rect = self.mapRectToScene(new_rect)
        dx, dy = 0, 0
        if new_scene_rect.left() < scene_rect.left():
            dx = scene_rect.left() - new_scene_rect.left()
        if new_scene_rect.top() < scene_rect.top():
            dy = scene_rect.top() - new_scene_rect.top()
        if new_scene_rect.right() > scene_rect.right():
            dx = scene_rect.right() - new_scene_rect.right()
        if new_scene_rect.bottom() > scene_rect.bottom():
            dy = scene_rect.bottom() - new_scene_rect.bottom()
        if dx or dy:
            new_scene_rect.translate(dx, dy)
            new_rect = self.mapRectFromScene(new_scene_rect)
        self.setRect(new_rect)
        self.updateHandlePositions()
        event.accept()
        if hasattr(self.scene().parent_widget, "crop_rect_finalized"):
            self.scene().parent_widget.crop_rect_finalized(self.sceneBoundingRect())
        """
        Adjusts the crop region's position if it moves outside the scene bounds.
        This is called on mouse release after dragging the entire crop region.
        """
        scene_rect = self.scene().sceneRect()
        crop_rect = self.sceneBoundingRect()

        dx, dy = 0, 0
        if crop_rect.left() < scene_rect.left():
            dx = scene_rect.left() - crop_rect.left()
        if crop_rect.top() < scene_rect.top():
            dy = scene_rect.top() - crop_rect.top()
        if crop_rect.right() > scene_rect.right():
            dx = scene_rect.right() - crop_rect.right()
        if crop_rect.bottom() > scene_rect.bottom():
            dy = scene_rect.bottom() - crop_rect.bottom()

        if dx != 0 or dy != 0:
            self.moveBy(dx, dy)