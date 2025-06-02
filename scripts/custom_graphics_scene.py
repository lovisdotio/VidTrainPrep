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
        old_ratio = self.aspect_ratio
        self.aspect_ratio = ratio
        
        if self.crop_item:
            # Update the crop item's aspect ratio.
            self.crop_item.aspect_ratio = ratio
            
            # If the aspect ratio actually changed, tell the crop_item to update its geometry
            if old_ratio != ratio:
                if hasattr(self.crop_item, 'update_geometry_on_ratio_change'):
                    self.crop_item.update_geometry_on_ratio_change()
                else: # Fallback if method not yet implemented
                    self.crop_item.update() # Request a generic update

    def mousePressEvent(self, event):
        # Si un crop existe déjà
        if self.crop_item:
            # Vérifier si le clic est proche du crop existant
            tolerance = 10  # tolérance en pixels pour la sélection
            region_scene_rect = self.crop_item.sceneBoundingRect()
            inflated_rect = region_scene_rect.adjusted(-tolerance, -tolerance, tolerance, tolerance)
            
            if inflated_rect.contains(event.scenePos()):
                # Transférer l'événement à l'élément de crop
                self.crop_item.mousePressEvent(event)
                event.accept()
                return
            else:
                # Si le clic est loin, supprimer le crop existant
                self.removeItem(self.crop_item)
                self.crop_item = None
                # Continuer pour créer un nouveau crop

        # Commencer à créer un nouveau crop
        self.start_point = event.scenePos()
        self.temp_rect_item = self.addRect(QRectF(self.start_point, self.start_point),
                                         QPen(QColor(255, 0, 0), 2),
                                         QBrush(QColor(255, 0, 0, 30)))
        event.accept()

    def mouseMoveEvent(self, event):
        scene_pos = event.scenePos()
        
        # Si un crop existe et que la souris est à l'intérieur
        if self.crop_item and self.crop_item.contains(scene_pos):
            # Transférer l'événement à l'élément de crop
            self.crop_item.mouseMoveEvent(event)
            event.accept()
            return

        # Si nous dessinons un nouveau crop
        if self.start_point and self.temp_rect_item:
            current_point = scene_pos
            rect = QRectF(self.start_point, current_point).normalized()

            # Appliquer la contrainte de ratio d'aspect si définie
            if self.aspect_ratio is not None:
                current_width = rect.width()
                current_height = rect.height() if rect.height() != 0 else 1
                if current_width / current_height > self.aspect_ratio:
                    rect.setWidth(current_height * self.aspect_ratio)
                else:
                    rect.setHeight(current_width / self.aspect_ratio)

            # Limiter le rectangle aux limites de la scène
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
            
            # Notifier le parent des mises à jour en cours
            if hasattr(self.parent_widget, "crop_rect_updating"):
                self.parent_widget.crop_rect_updating(rect)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.start_point and self.temp_rect_item:
            # Finaliser le nouveau crop
            rect = self.temp_rect_item.rect().normalized()
            self.removeItem(self.temp_rect_item)
            self.temp_rect_item = None
            self.start_point = None

            if rect.width() >= 20 and rect.height() >= 20:
                # Créer le nouveau crop interactif
                self.crop_item = InteractiveCropRegion(rect, aspect_ratio=self.aspect_ratio)
                self.addItem(self.crop_item)
                if hasattr(self.parent_widget, "crop_rect_finalized"):
                    self.parent_widget.crop_rect_finalized(self.crop_item.sceneBoundingRect())
            event.accept()
        else:
            super().mouseReleaseEvent(event)
