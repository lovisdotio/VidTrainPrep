import sys, os, cv2, ffmpeg, json, numpy as np
import uuid # Import UUID for unique range IDs
from scripts.custom_graphics_view import CustomGraphicsView
from PyQt6.QtWidgets import (
    QApplication, QWidget, QFileDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QListWidget, QSlider, QGraphicsPixmapItem, QLineEdit, QSpinBox,
    QSizePolicy, QCheckBox, QListWidgetItem, QComboBox, QMessageBox, QDialog, QFormLayout, QDialogButtonBox,
    QSpacerItem # Added QSpacerItem
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QIcon, QMouseEvent, QIntValidator
from PyQt6.QtCore import Qt, QTimer, QRectF

# Custom scene (modified to use the new crop region)
from scripts.custom_graphics_scene import CustomGraphicsScene

# Import helper modules
from scripts.video_loader import VideoLoader
from scripts.video_editor import VideoEditor
from scripts.video_exporter import VideoExporter

class VideoCropper(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VidTrainPrep")
        self.setGeometry(100, 100, 900, 700) # Increased size slightly
        self.setWindowIcon(QIcon("icons/favicon.ico"))
        
        # Core state
        self.folder_path = ""
        self.video_files = []  # List of video dicts (display info)
        # NEW Data structure: Key is original_path, value is dict with ranges
        self.video_data = {}
        # Structure for a range: {"start": int, "end": int, "crop": tuple | None, "id": str}
        self.current_video_original_path = None # Track the source file path
        self.current_selected_range_id = None # Track the selected range in the list

        # Crop related (mostly unchanged, but context changes)
        self.current_rect = None
        self.longest_edge = 1024
        self.cap = None
        self.frame_count = 0
        self.original_width = 0
        self.original_height = 0
        self.clip_aspect_ratio = 1.0

        # Playback state (mostly unchanged)
        self.is_playing = False
        self.loop_playback = False # Will apply to selected range

        # Export properties (mostly unchanged for now)
        self.export_uncropped = False
        self.export_image = False

        # Session file (will need update later)
        self.folder_sessions = {}
        self.session_file = "session_data.json"

        # Caption properties (unchanged)
        self.simple_caption = ""

        # UI widgets (some changes)
        self.video_list = QListWidget() # Main list of videos/duplicates

        # Aspect ratio options (unchanged)
        self.aspect_ratios = {
            "Free-form": None, "1:1 (Square)": 1.0, "4:3 (Standard)": 4/3,
            "16:9 (Widescreen)": 16/9, "9:16 (Vertical Video)": 9/16,
            "2:1 (Cinematic)": 2.0, "3:2 (Classic Photo)": 3/2,
            "21:9 (Ultrawide)": 21/9
        }

        # Create helper modules and pass self.
        self.loader = VideoLoader(self)
        self.editor = VideoEditor(self)
        self.exporter = VideoExporter(self)

        # Load previous session.
        self.loader.load_session() # Will need modification later
        
        self.initUI()
        # Initialize frame label text after UI is built
        self.update_current_frame_label(0, 0, 0) # Show initial state
    
    def initUI(self):
        main_layout = QHBoxLayout(self)
        
        # LEFT PANEL
        left_panel = QVBoxLayout()
        icon_label = QLabel(self)
        icon_pixmap = QPixmap("icons/folder_icon.png")
        icon_label.setPixmap(icon_pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_panel.addWidget(icon_label)
        
        self.folder_button = QPushButton("Select Folder")
        self.folder_button.clicked.connect(self.loader.load_folder)
        left_panel.addWidget(self.folder_button)
        
        # Add FPS Conversion Button
        self.convert_fps_button = QPushButton("Convert FPS...")
        self.convert_fps_button.setToolTip("Convert all videos in the current folder to a target FPS.")
        self.convert_fps_button.clicked.connect(self.open_convert_fps_dialog) # New method
        left_panel.addWidget(self.convert_fps_button)
        
        # Main video list
        left_panel.addWidget(QLabel("Video Files:"))
        self.video_list.itemClicked.connect(self.loader.load_video) # load_video needs update
        # self.video_list.itemChanged.connect(self.loader.update_list_item_color) # Keep this
        left_panel.addWidget(self.video_list, 1) # More vertical space

        # self.duplicate_button = QPushButton("Duplicate Video Entry") # REMOVED - Obsolete with ranges
        # self.duplicate_button.clicked.connect(self.loader.duplicate_clip)
        # left_panel.addWidget(self.duplicate_button)
        
        # --- Clip Range Management Panel ---
        range_group_box = QWidget() # Use a QWidget for layout within the panel
        range_layout = QVBoxLayout(range_group_box)
        range_layout.setContentsMargins(0, 5, 0, 0) # Adjust margins

        range_layout.addWidget(QLabel("Clip Ranges for Selected Video:"))
        self.clip_range_list = QListWidget()
        self.clip_range_list.setFixedHeight(150) # Adjust height as needed
        self.clip_range_list.itemClicked.connect(self.select_range) # New method needed
        range_layout.addWidget(self.clip_range_list)

        # Range Start/End Inputs -> Start/Duration Inputs
        range_input_layout = QHBoxLayout()
        range_input_layout.addWidget(QLabel("Start Frame:")) # Changed label
        self.start_frame_input = QLineEdit("0")
        self.start_frame_input.setReadOnly(True) # Make Start Frame read-only
        # self.start_frame_input.setValidator(QIntValidator(0, 9999999))
        # self.start_frame_input.editingFinished.connect(self.update_range_from_inputs) # No longer directly edited
        range_input_layout.addWidget(self.start_frame_input)

        range_input_layout.addWidget(QLabel("Duration (f):")) # Changed label
        self.duration_input = QLineEdit("60") # Default duration
        self.duration_input.setValidator(QIntValidator(1, 99999)) # Duration must be at least 1
        self.duration_input.editingFinished.connect(self.update_range_duration_from_input) # Renamed method
        range_input_layout.addWidget(self.duration_input)
        range_layout.addLayout(range_input_layout)

        # Add/Remove Buttons
        range_button_layout = QHBoxLayout()
        self.add_range_button = QPushButton("Add Range Here") # Renamed button
        self.add_range_button.setToolTip("Add a new range starting at the current frame, using the specified duration (no crop).")
        self.add_range_button.clicked.connect(self.add_range_at_current_frame) # Changed connection
        range_button_layout.addWidget(self.add_range_button)

        self.remove_range_button = QPushButton("Remove Range")
        self.remove_range_button.clicked.connect(self.remove_selected_range) # New method needed
        range_button_layout.addWidget(self.remove_range_button)
        self.play_range_button = QPushButton("Preview Range (Z)") # New Button
        self.play_range_button.clicked.connect(self.toggle_play_selected_range) # New method
        range_button_layout.addWidget(self.play_range_button)
        range_layout.addLayout(range_button_layout)

        left_panel.addWidget(range_group_box) # Add the range management group

        # --- Other Controls (Moved slightly) ---
        self.clear_crop_button = QPushButton("Clear Crop for Selected Range") # Text updated
        self.clear_crop_button.clicked.connect(self.clear_current_range_crop) # New method needed
        left_panel.addWidget(self.clear_crop_button)

        self.export_cropped_checkbox = QCheckBox("Export Cropped Clips") # Keep concept
        self.export_cropped_checkbox.setChecked(True) # Default to true maybe?
        left_panel.addWidget(self.export_cropped_checkbox)

        self.export_uncropped_checkbox = QCheckBox("Export Uncropped Clips") # Keep concept
        self.export_uncropped_checkbox.setChecked(False)
        left_panel.addWidget(self.export_uncropped_checkbox)

        self.export_image_checkbox = QCheckBox("Export Image at Start Frame") # Text updated
        self.export_image_checkbox.setChecked(False)
        left_panel.addWidget(self.export_image_checkbox)

        # Add spacer to push export settings down
        left_panel.addStretch(1)

        # Add Description Label
        description_label = QLabel(
            "<b>Workflow:</b><br>"
            "1. Select Folder / Convert FPS.<br>"
            "2. Select video from list.<br>"
            "3. Navigate to desired start frame using slider.<br>"
            "4. Set clip Duration.<br>"
            "5. Draw crop rectangle to define & add a new range.<br>"
            "   (Or click 'Add Range Here' for no crop).<br>"
            "6. Select ranges, adjust Duration if needed.<br>"
            "7. Configure Export/Gemini options (API Key, Trigger, Name).<br>"
            "8. Check videos in list & Export."
        )
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        description_label.setStyleSheet("font-size: 11px; color: #B0B0B0; background-color: transparent; padding: 5px; border-top: 1px solid #555555;") # Add style
        left_panel.addWidget(description_label)

        # Add Attribution Label
        attribution_label = QLabel(
            "Based on <a href=\"https://github.com/Tr1dae/HunyClip\" style=\"color: #88C0D0;\"><span style=\"color: #88C0D0;\">HunyClip by Tr1dae</span></a>"
        )
        attribution_label.setOpenExternalLinks(True)
        attribution_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        attribution_label.setStyleSheet("font-size: 11px; color: #A0A0A0; background-color: transparent; margin-top: 5px;") # Increased font size
        left_panel.addWidget(attribution_label)

        main_layout.addLayout(left_panel, 1) # Left panel takes less space relative to right

        self.video_list.setStyleSheet("QListWidget::item:selected { background-color: #3A4F7A; }")
        self.clip_range_list.setStyleSheet("QListWidget::item:selected { background-color: #5A6F9A; }") # Different selection color
        
        # RIGHT PANEL
        right_panel = QVBoxLayout()
        keybindings_label = QLabel("Left/Right: Prev/Next Frame | Shift+Left/Right: Prev/Next Second | Drag: Crop | Z: Preview Range | X: Next Video | C: Play/Pause | Q/W: Nudge End | A/S: Nudge Start") # Updated shortcuts
        keybindings_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keybindings_label.setStyleSheet("font-size: 11px; color: #ECEFF4;") # Smaller font
        right_panel.addWidget(keybindings_label)
        
        aspect_ratio_layout = QHBoxLayout()
        aspect_ratio_layout.addWidget(QLabel("Aspect Ratio:"))
        self.aspect_ratio_combo = QComboBox()
        for ratio_name in self.aspect_ratios.keys():
            self.aspect_ratio_combo.addItem(ratio_name)
        self.aspect_ratio_combo.currentTextChanged.connect(self.set_aspect_ratio)
        aspect_ratio_layout.addWidget(self.aspect_ratio_combo)
        right_panel.addLayout(aspect_ratio_layout)
        
        self.graphics_view = CustomGraphicsView()
        self.graphics_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.graphics_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.graphics_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scene = CustomGraphicsScene(self)
        self.graphics_view.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        self.graphics_view.setMouseTracking(True)
        right_panel.addWidget(self.graphics_view, 1)
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setEnabled(False)
        self.slider.sliderMoved.connect(self.editor.scrub_video)
        self.slider.valueChanged.connect(self.editor.scrub_video)
        right_panel.addWidget(self.slider)
        
        self.clip_length_label = QLabel("Clip Length: 0 frames | Video Length: 0 frames") # Show clip and total length
        right_panel.addWidget(self.clip_length_label)
        
        self.thumbnail_label = QWidget(self)
        self.thumbnail_label.setWindowFlags(Qt.WindowType.ToolTip)
        self.thumbnail_label.setStyleSheet("background-color: black; border: 1px solid white;")
        self.thumbnail_label.hide()
        right_panel.addWidget(self.thumbnail_label)
        self.thumbnail_image_label = QLabel(self.thumbnail_label)
        self.thumbnail_image_label.setGeometry(0, 0, 160, 90)
        
        self.slider.installEventFilter(self)
        
        # --- NEW: Frame Control Layout ---
        frame_control_layout = QHBoxLayout()

        # Prev Frame Button
        self.step_backward_button = QPushButton("< Frame")
        self.step_backward_button.setToolTip("Go to Previous Frame (Shortcut: Left Arrow)")
        self.step_backward_button.clicked.connect(self._step_frame_backward)
        self.step_backward_button.setFixedWidth(80) # Optional fixed width
        frame_control_layout.addWidget(self.step_backward_button)

        # Current Frame Label (NEW) - Give it expanding space
        self.current_frame_label = QLabel("Frame: - / -")
        self.current_frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_frame_label.setStyleSheet("font-size: 12px; color: #C0C0C0;") # Style
        frame_control_layout.addWidget(self.current_frame_label, 1) # Expanding

        # Next Frame Button
        self.step_forward_button = QPushButton("Frame >")
        self.step_forward_button.setToolTip("Go to Next Frame (Shortcut: Right Arrow)")
        self.step_forward_button.clicked.connect(self._step_frame_forward)
        self.step_forward_button.setFixedWidth(80) # Optional fixed width
        frame_control_layout.addWidget(self.step_forward_button)

        # Go to Frame Input
        frame_control_layout.addWidget(QLabel(" Go to Frame:"))
        self.goto_frame_input = QLineEdit()
        self.goto_frame_input.setFixedWidth(70) # Optional fixed width
        self.goto_frame_input.setValidator(QIntValidator(0, 9999999)) # Allow large frame numbers
        self.goto_frame_input.setToolTip("Enter frame number and press Enter")
        self.goto_frame_input.returnPressed.connect(self._goto_frame) # Connect return key
        frame_control_layout.addWidget(self.goto_frame_input)

        right_panel.addLayout(frame_control_layout) # Add this layout below the slider

        # --- Reorganized Export Settings & Gemini Inputs (Vertical) ---
        export_options_group = QWidget()
        export_options_layout = QFormLayout(export_options_group)
        export_options_layout.setContentsMargins(0, 10, 0, 5) # Add some top margin

        # Resolution
        self.resolution_input = QLineEdit() # Keep this one
        self.resolution_input.setPlaceholderText("Longest Edge (e.g., 1024, Optional)")
        self.resolution_input.textChanged.connect(self.set_longest_edge)
        export_options_layout.addRow("Output Res (Max Edge):", self.resolution_input)

        # Filename Prefix
        self.prefix_input = QLineEdit()
        self.prefix_input.setPlaceholderText("Replace original name (Optional)")
        self.prefix_input.textChanged.connect(lambda text: setattr(self, "export_prefix", text))
        export_options_layout.addRow("Filename Prefix:", self.prefix_input)

        # Trigger Word
        self.trigger_word_input = QLineEdit()
        self.trigger_word_input.setPlaceholderText("Prepend to captions (Optional)")
        export_options_layout.addRow("Trigger Word:", self.trigger_word_input)

        # Character Name
        self.character_name_input = QLineEdit()
        self.character_name_input.setPlaceholderText("Subject name for Gemini (Optional)")
        export_options_layout.addRow("Character Name:", self.character_name_input)
        
        # Gemini API Key
        self.gemini_api_key_input = QLineEdit()
        self.gemini_api_key_input.setPlaceholderText("Enter Gemini API Key Here")
        self.gemini_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        export_options_layout.addRow("Gemini API Key:", self.gemini_api_key_input)
        
        # Gemini Checkbox
        self.gemini_caption_checkbox = QCheckBox("Generate Gemini Caption/Description") # Text updated
        self.gemini_caption_checkbox.setChecked(False)
        # self.gemini_caption_checkbox.stateChanged.connect(self.toggle_image_export_based_on_gemini) # Connection removed previously
        export_options_layout.addRow("", self.gemini_caption_checkbox) # Add checkbox without a label on the left

        right_panel.addWidget(export_options_group)

        # Captions (Keep as is)
        # self.caption_input = QLineEdit() # REMOVED
        # self.caption_input.setPlaceholderText("Simple caption (Optional)") # REMOVED
        # self.caption_input.textChanged.connect(lambda text: setattr(self, "simple_caption", text)) # REMOVED
        # right_panel.addWidget(self.caption_input) # REMOVED
        # self.gemini_api_key_input = QLineEdit() # MOVED
        # self.gemini_api_key_input.setPlaceholderText("Enter Gemini API Key Here") # MOVED
        # self.gemini_api_key_input.setEchoMode(QLineEdit.EchoMode.Password) # MOVED
        # right_panel.addWidget(self.gemini_api_key_input) # MOVED
        # self.gemini_caption_checkbox = QCheckBox("Generate Gemini Caption/Description") # MOVED
        # self.gemini_caption_checkbox.setChecked(False) # MOVED
        # # self.gemini_caption_checkbox.stateChanged.connect(self.toggle_image_export_based_on_gemini) # Connection removed previously
        # right_panel.addWidget(self.gemini_caption_checkbox) # MOVED

        self.submit_button = QPushButton("Export Selected Video(s)") # Text updated
        self.submit_button.clicked.connect(self.exporter.export_videos) # export_videos needs update
        right_panel.addWidget(self.submit_button)
        
        main_layout.addLayout(right_panel, 3)
    
    def set_aspect_ratio(self, ratio_name):
        ratio_value = self.aspect_ratios.get(ratio_name)
        self.scene.set_aspect_ratio(ratio_value)
    
    def set_longest_edge(self):
        try:
            self.longest_edge = int(self.resolution_input.text())
        except ValueError:
            self.longest_edge = 1080

    def clear_crop_region_controller(self):
        """
        Remove all interactive crop region items from the scene.
        This ensures that when loading a new clip or creating a new crop region,
        only one crop region is visible.
        """
        from scripts.interactive_crop_region import InteractiveCropRegion
        # Collect all items that are instances of InteractiveCropRegion.
        items_to_remove = [item for item in self.scene.items() if isinstance(item, InteractiveCropRegion)]
        for item in items_to_remove:
            self.scene.removeItem(item)
        self.current_rect = None

    def crop_rect_updating(self, rect):
        """
        Callback invoked during crop region adjustment.
        You can use this to update a preview or status label.
        """
        print(f"Crop region updating: {rect}")

    def crop_rect_finalized(self, rect):
        """Callback invoked when the crop region is finalized.
           If a range is selected, updates its crop.
           If no range is selected, creates a new range at the current frame.
        """
        if not self.current_video_original_path:
            print("⚠️ Cannot process crop: No video loaded.")
            return

        pixmap = self.pixmap_item.pixmap()
        if pixmap is None or pixmap.width() == 0:
            print("⚠️ Cannot process crop: No pixmap.")
            return

        # --- Calculate Crop Data (relative to original video) ---
        scale_w = self.original_width / pixmap.width()
        scale_h = self.original_height / pixmap.height()
        x = int(rect.x() * scale_w)
        y = int(rect.y() * scale_h)
        w = int(rect.width() * scale_w)
        h = int(rect.height() * scale_h)
        
        # Validate coordinates
        if x<0 or y<0 or w<=0 or h<=0 or x+w > self.original_width or y+h > self.original_height:
             print(f"⚠️ Invalid crop coordinates calculated: ({x},{y},{w},{h}). Clamping/adjusting might be needed.")
             x = max(0, x)
             y = max(0, y)
             w = min(w, self.original_width - x)
             h = min(h, self.original_height - y)
             if w <= 0 or h <= 0:
                 print("   Crop invalid even after clamping. Discarding crop action.")
                 self.clear_crop_region_controller() # Clear invalid visual crop
                 return
                 
        crop_tuple = (x, y, w, h)
        
        # --- Apply Crop to Selected Range OR Create New Range ---
        if self.current_selected_range_id:
            # --- Update Existing Selected Range --- 
            range_data = self.find_range_by_id(self.current_selected_range_id)
            if range_data:
                 range_data["crop"] = crop_tuple
                 print(f"Updated crop for range {self.current_selected_range_id}: {crop_tuple}")
                 # Reload visual crop to ensure consistency (handles aspect ratio enforcement)
                 self._load_range_crop(range_data)
            else:
                 print(f"⚠️ Could not find selected range {self.current_selected_range_id} to update crop.")
                 # Clear visual crop if data is inconsistent
                 self.clear_crop_region_controller()
        else:
            # --- Create New Range --- 
            print("No range selected. Creating new range from crop...")
            start_frame = self.slider.value() # Use the current slider position as start
            try:
                duration = int(self.duration_input.text())
                if duration <= 0:
                    print("⚠️ Duration must be positive. Using default of 60.")
                    duration = 60
                    self.duration_input.setText("60")
            except ValueError:
                print("⚠️ Invalid duration input. Using default of 60.")
                duration = 60
                self.duration_input.setText("60")
                
            end_frame = min(start_frame + duration, self.frame_count) # Calculate end, clamp to video length
            if end_frame <= start_frame: # Ensure duration is at least 1 frame after clamping
                print("⚠️ Calculated end frame is <= start frame. Adjusting end frame.")
                end_frame = start_frame + 1
                if end_frame > self.frame_count:
                    print("   Cannot add range starting at the very last frame.")
                    self.clear_crop_region_controller()
                    return

            print(f"Adding new range from crop: Start={start_frame}, End={end_frame}, Crop={crop_tuple}")
            self.add_new_range(start=start_frame, end=end_frame, crop=crop_tuple)
            # The visual crop rectangle is handled by the selection of the new range in add_new_range

    def check_current_video_item(self):
        # Might need rework depending on how "checked" state is used with ranges
        pass
        # for i in range(self.video_list.count()):
        #     item = self.video_list.item(i)
        #     # How to map item back to original_path consistently? Store path in item data?
        #     # item_path = item.data(Qt.ItemDataRole.UserRole) # Assuming we store path here
        #     # if item_path == self.current_video_original_path:
        #     #      if item.checkState() != Qt.CheckState.Checked:
        #     #         item.setCheckState(Qt.CheckState.Checked)
        #     #      break

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        # Focus check: Only handle frame keys if graphics view or slider has focus?
        # Or allow always? Let's allow always for now.
        # focused_widget = QApplication.focusWidget()
        # allow_frame_nav = focused_widget is self.graphics_view or focused_widget is self.slider

        if key == Qt.Key.Key_Right: # Frame Forward / Jump Forward
            if self.slider.isEnabled(): # Only if video loaded
                if modifiers == Qt.KeyboardModifier.ShiftModifier:
                    self.editor.jump_frames(1.0) # Jump 1 second forward
                else:
                    self.editor.step_frame(1) # Step 1 frame forward
                event.accept()
            else:
                super().keyPressEvent(event)
        elif key == Qt.Key.Key_Left: # Frame Backward / Jump Backward
             if self.slider.isEnabled(): # Only if video loaded
                if modifiers == Qt.KeyboardModifier.ShiftModifier:
                    self.editor.jump_frames(-1.0) # Jump 1 second backward
                else:
                    self.editor.step_frame(-1) # Step 1 frame backward
                event.accept()
             else:
                super().keyPressEvent(event)

        elif key == Qt.Key.Key_Z: # Preview selected range
            # No change needed, handled by button connection now, but keep shortcut
            self.editor.toggle_loop_playback()
            event.accept()
        elif key == Qt.Key.Key_X: # Next Video
            self.editor.next_clip()
            event.accept()
        elif key == Qt.Key.Key_C: # Play/Pause Normal
             if self.slider.isEnabled():
                self.editor.toggle_play_forward()
                event.accept()
             else:
                 super().keyPressEvent(event)
        elif key == Qt.Key.Key_Q: # Nudge End Frame Left
            if self.current_selected_range_id:
                self.nudge_end_frame(-1)
                event.accept()
            else:
                super().keyPressEvent(event)
        elif key == Qt.Key.Key_W: # Nudge End Frame Right
            if self.current_selected_range_id:
                self.nudge_end_frame(1)
                event.accept()
            else:
                super().keyPressEvent(event)
        elif key == Qt.Key.Key_A: # Nudge Start Frame Left
            # This needs adjustment to update duration correctly when start moves
            if self.current_selected_range_id:
                self.nudge_start_frame(-1)
                event.accept()
            else:
                super().keyPressEvent(event)
        elif key == Qt.Key.Key_S: # Nudge Start Frame Right
             # This needs adjustment to update duration correctly when start moves
             if self.current_selected_range_id:
                self.nudge_start_frame(1)
                event.accept()
             else:
                super().keyPressEvent(event)
        elif key == Qt.Key.Key_Delete or key == Qt.Key.Key_Backspace:
            # Delete selected range if range list has focus
            if self.clip_range_list.hasFocus() and self.current_selected_range_id:
                self.remove_selected_range()
                event.accept()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def nudge_start_frame(self, delta):
        if not self.current_selected_range_id: return
        range_data = self.find_range_by_id(self.current_selected_range_id)
        if not range_data: return

        try:
            current_start = range_data.get("start", 0)
            current_end = range_data.get("end", 0)
            current_duration = current_end - current_start

            new_start = max(0, current_start + delta)

            # Calculate new end based on original duration, then clamp
            new_end = new_start + current_duration
            new_end = min(new_end, self.frame_count) # Clamp end to video length

            # Ensure start is still less than (clamped) end
            if new_start >= new_end:
                 print("Nudge start failed: Start frame reached or exceeded end frame.")
                 # Optionally revert or just do nothing
                 return

            # Update data structure
            range_data["start"] = new_start
            range_data["end"] = new_end # End also changes to maintain duration

            # Update UI Input Fields
            self.start_frame_input.setText(str(new_start))
            new_duration = new_end - new_start
            self.duration_input.setText(str(new_duration)) # Update duration display

            # Update list item text
            current_item = self.clip_range_list.currentItem()
            if current_item:
                self._update_list_item_text(current_item, range_data)

            # Update frame display and slider to the new start
            self.editor.update_frame_display(new_start)

            print(f"Nudged start for {self.current_selected_range_id}: New Range [{new_start}-{new_end}]")

        except ValueError: pass # Ignore if inputs are somehow invalid

    def nudge_end_frame(self, delta):
        # This function is simpler as it just changes duration
        if not self.current_selected_range_id: return
        try:
            # Get current duration from input
            current_duration = int(self.duration_input.text())
            new_duration = max(1, current_duration + delta) # Ensure duration is at least 1

            # Update the duration input
            self.duration_input.setText(str(new_duration))

            # Trigger the update logic (which clamps end frame etc.)
            self.update_range_duration_from_input()
            print(f"Nudged end for {self.current_selected_range_id}: New Duration {new_duration}")

        except ValueError: pass

    def eventFilter(self, source, event):
        if source is self.slider:
            if event.type() == QMouseEvent.Type.MouseButtonPress:
                pass
            elif event.type() == QMouseEvent.Type.HoverMove:
                self.editor.show_thumbnail(event) # show_thumbnail might need update?
            elif event.type() == QMouseEvent.Type.Leave:
                self.thumbnail_label.hide()
        return False

    def closeEvent(self, event):
        self.loader.save_session() # save_session needs update
        event.accept()

    def select_range(self, item):
        if not item: # Can happen if list is cleared
            self.current_selected_range_id = None
            self.start_frame_input.setText("-") # Indicate no selection
            self.duration_input.setText("-")
            self.clear_crop_region_controller()
            if hasattr(self, 'goto_frame_input'): self.goto_frame_input.clear() # Clear goto input
            return
            
        range_id = item.data(Qt.ItemDataRole.UserRole)
        if not range_id:
             print("⚠️ Selected item has no range ID.")
             return
             
        self.current_selected_range_id = range_id
        range_data = self.find_range_by_id(range_id)

        if range_data:
            print(f"Range selected: {range_id} -> {range_data}")
            start_frame = range_data.get("start", 0)
            end_frame = range_data.get("end", 0)
            self.start_frame_input.setText(str(start_frame))
            duration = end_frame - start_frame
            self.duration_input.setText(str(duration))
            self._load_range_crop(range_data) # Load visual crop
            if self.frame_count > 0:
                 # Update frame display first
                 self.editor.update_frame_display(start_frame)
                 # Update slider value (may trigger scrub_video again, but should be ok)
                 self.slider.setValue(start_frame)
            # Update label (using the new method directly)
            fps = self.cap.get(cv2.CAP_PROP_FPS) if self.cap else 0
            # self.update_current_frame_label(start_frame, self.frame_count, fps) # update_frame_display handles this

            # Clear goto input when selecting a range
            if hasattr(self, 'goto_frame_input'): self.goto_frame_input.clear()

        else:
            print(f"⚠️ Could not find data for range ID: {range_id}")
            self.current_selected_range_id = None
            # Reset UI elements if data not found
            self.start_frame_input.setText("0")
            self.duration_input.setText("60") # Default duration
            self.clear_crop_region_controller()
            if hasattr(self, 'goto_frame_input'): self.goto_frame_input.clear() # Clear goto input

    def update_range_duration_from_input(self): # Renamed method
        if not self.current_selected_range_id:
             # Don't update if no range is selected (e.g., during initial load)
             return
             
        range_data = self.find_range_by_id(self.current_selected_range_id)
        if not range_data:
            print(f"⚠️ Cannot update: Range data not found for {self.current_selected_range_id}")
            return

        try:
            # Read start frame (read-only) and new duration
            start_frame = int(self.start_frame_input.text())
            new_duration = int(self.duration_input.text())
            
            # Validation
            if new_duration <= 0:
                 print("⚠️ Duration must be positive. Reverting.")
                 old_duration = range_data.get("end", start_frame) - range_data.get("start", start_frame)
                 self.duration_input.setText(str(old_duration))
                 return
            
            new_end = min(start_frame + new_duration, self.frame_count) # Calculate new end, clamp
            if new_end <= start_frame: # If clamping results in invalid range
                print("⚠️ Duration too short or start frame too near end. Reverting.")
                old_duration = range_data.get("end", start_frame) - range_data.get("start", start_frame)
                self.duration_input.setText(str(old_duration))
                return
                   
            # Update input fields after validation (duration might change due to clamping)
            self.duration_input.setText(str(new_end - start_frame))

            # Update data structure (only end frame changes)
            range_data["end"] = new_end
            print(f"Range {self.current_selected_range_id} duration updated: Start={start_frame}, End={new_end}")

            # Update list item text
            current_item = self.clip_range_list.currentItem()
            if current_item:
                self._update_list_item_text(current_item, range_data)
                
            # Update length label
            range_len = new_end - start_frame
            self.clip_length_label.setText(f"Clip Length: {range_len} frames | Video Length: {self.frame_count} frames")
            
            # Optionally update slider handle visuals here if implemented

        except ValueError:
            print("⚠️ Invalid input for start/end frame.")
            # Revert inputs to stored values? Or just ignore?
            self.start_frame_input.setText(str(range_data.get("start", 0)))
            old_duration = range_data.get("end", start_frame) - range_data.get("start", start_frame)
            self.duration_input.setText(str(old_duration))

    def add_new_range(self, start=None, end=None, crop=None):
        """Adds a new range, potentially with pre-defined start, end, crop."""
        if not self.current_video_original_path:
            QMessageBox.warning(self, "No Video", "Please select a video first.")
            return
            
        if self.current_video_original_path not in self.video_data:
             # Initialize if this is the first range for this video
             self.video_data[self.current_video_original_path] = {"ranges": []}

        video_ranges = self.video_data[self.current_video_original_path]["ranges"]
        
        # Determine default start/end/crop if not provided
        if start is None:
             # Default: use current slider position
             start_frame = self.slider.value()
             try:
                 duration = int(self.duration_input.text())
                 if duration <= 0: duration = 60
             except ValueError: duration = 60
             end_frame = min(start_frame + duration, self.frame_count)
             if end_frame <= start_frame:
                  end_frame = min(start_frame + 1, self.frame_count)
                  if start_frame >= end_frame:
                      start_frame = max(0, end_frame - 1)
             crop_tuple = None # No crop by default if using button
        else:
             # Use provided values (from crop_rect_finalized)
             start_frame = start
             end_frame = end
             crop_tuple = crop

        # Create new range data
        new_range_id = str(uuid.uuid4())
        new_range_data = {
            "id": new_range_id,
            "start": start_frame,
            "end": end_frame,
            "crop": crop_tuple, # Use calculated/provided crop
            "index": len(video_ranges) + 1 # Simple 1-based index for display
        }
        video_ranges.append(new_range_data)
        print(f"Added new range: {new_range_data}")

        # Add item to the list widget
        item = QListWidgetItem()
        self._update_list_item_text(item, new_range_data) 
        self.clip_range_list.addItem(item)
        
        # Select the newly added item
        self.clip_range_list.setCurrentItem(item)
        self.select_range(item) # Trigger selection logic to load data into UI
        
    def add_range_at_current_frame(self):
         """Called by the 'Add Range Here' button."""
         self.add_new_range() # Call add_new_range without specific args
         
    def remove_selected_range(self):
        selected_items = self.clip_range_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a range to remove.")
            return
            
        current_item = selected_items[0]
        range_id_to_remove = current_item.data(Qt.ItemDataRole.UserRole)
        
        if not range_id_to_remove or not self.current_video_original_path:
            print("⚠️ Cannot remove range: Invalid state.")
            return

        # Remove from data structure
        if self.current_video_original_path in self.video_data:
            ranges = self.video_data[self.current_video_original_path].get("ranges", [])
            original_length = len(ranges)
            self.video_data[self.current_video_original_path]["ranges"] = [
                r for r in ranges if r["id"] != range_id_to_remove
            ]
            # Re-index remaining ranges for display consistency
            for i, r in enumerate(self.video_data[self.current_video_original_path]["ranges"]):
                 r["index"] = i + 1
                 
            if len(self.video_data[self.current_video_original_path]["ranges"]) < original_length:
                 print(f"Removed range {range_id_to_remove}")
            else:
                 print(f"⚠️ Range {range_id_to_remove} not found in data.")
                 # Don't remove from list if not found in data
                 return

        # Remove from list widget
        row = self.clip_range_list.row(current_item)
        self.clip_range_list.takeItem(row)
        
        # Update list item text for remaining items (due to re-indexing)
        for i in range(self.clip_range_list.count()):
            item = self.clip_range_list.item(i)
            item_range_id = item.data(Qt.ItemDataRole.UserRole)
            item_range_data = self.find_range_by_id(item_range_id)
            if item_range_data:
                self._update_list_item_text(item, item_range_data)

        # Clear selection or select next/previous
        if self.clip_range_list.count() > 0:
            next_row = min(row, self.clip_range_list.count() - 1)
            self.clip_range_list.setCurrentRow(next_row)
            self.select_range(self.clip_range_list.item(next_row)) # Explicitly call select
        else:
            self.current_selected_range_id = None
            self.start_frame_input.setText("-")
            self.duration_input.setText("-")
            self.clear_crop_region_controller()
            self.clip_length_label.setText("Clip Length: 0 frames | Video Length: ...")

    def clear_current_range_crop(self):
        if not self.current_selected_range_id:
             QMessageBox.warning(self, "No Selection", "Please select a range first.")
             return
             
        # Visually clear the rectangle
        self.clear_crop_region_controller() 
        
        # Update data
        range_data = self.find_range_by_id(self.current_selected_range_id)
        if range_data:
           if range_data.get("crop") is not None:
               range_data["crop"] = None
               print(f"Cleared crop data for range {self.current_selected_range_id}")
           else:
                print(f"No crop data to clear for range {self.current_selected_range_id}")
        else:
            print(f"⚠️ Could not find range {self.current_selected_range_id} to clear crop data.")

    def toggle_play_selected_range(self):
        """Starts or stops playback of the currently selected range."""
        if not self.current_selected_range_id:
            QMessageBox.warning(self, "No Range Selected", "Please select a range to play.")
            return
            
        range_data = self.find_range_by_id(self.current_selected_range_id)
        if not range_data:
            print("⚠️ Cannot play range: Data not found.")
            return
            
        print(f"Toggling playback for range: {range_data['start']} - {range_data['end']}")
        self.editor.toggle_range_playback(range_data['start'], range_data['end'])

    # --- Range Data Helper --- 
    def find_range_by_id(self, range_id):
        if self.current_video_original_path in self.video_data:
            for r in self.video_data[self.current_video_original_path].get("ranges", []):
                if r["id"] == range_id:
                    return r
        return None

    def _update_list_item_text(self, item, range_data):
        """Helper to format the text of a range list item."""
        item.setText(f"Range {range_data.get('index', '?')} [{range_data['start']}-{range_data['end']}]")
        # Store the range ID in the item's data
        item.setData(Qt.ItemDataRole.UserRole, range_data["id"])
        
    def _load_range_crop(self, range_data):
        """ Clears existing crop and loads the one for the given range."""
        self.clear_crop_region_controller()
        crop_tuple = range_data.get("crop")
        if crop_tuple:
            from scripts.interactive_crop_region import InteractiveCropRegion
            x, y, w, h = crop_tuple
            
            # Convert original coordinates back to scene coordinates
            pixmap = self.pixmap_item.pixmap()
            if pixmap and pixmap.width() > 0 and pixmap.height() > 0:
                scale_w = pixmap.width() / self.original_width
                scale_h = pixmap.height() / self.original_height
                scene_x = x * scale_w
                scene_y = y * scale_h
                scene_w = w * scale_w
                scene_h = h * scale_h
                
                # Create a QRectF object first
                scene_rect = QRectF(scene_x, scene_y, scene_w, scene_h)

                # Create and add the visual crop rectangle using the QRectF and pass aspect ratio
                crop_item = InteractiveCropRegion(scene_rect, aspect_ratio=self.scene.aspect_ratio) # Pass aspect ratio here
                self.scene.addItem(crop_item)
                self.current_rect = crop_item # Keep track of the visual item
            else:
                print("⚠️ Cannot display crop: pixmap invalid.")

    def open_convert_fps_dialog(self):
        """Opens the dialog to configure and start FPS conversion."""
        if not self.folder_path or not os.path.isdir(self.folder_path):
            QMessageBox.warning(self, "No Folder", "Please select a folder first.")
            return

        # We'll create the dialog class separately
        dialog = ConvertFpsDialog(self)
        if dialog.exec(): # exec() shows the dialog modally
            target_fps, output_subdir = dialog.get_values()
            if target_fps and output_subdir:
                print(f"Starting FPS conversion: Target FPS={target_fps}, Subdir={output_subdir}")
                # Call the conversion function (likely in VideoLoader)
                # This should ideally run in a thread later, but start simple
                success = self.loader.convert_folder_fps(target_fps, output_subdir)
                if success:
                    QMessageBox.information(self, "Conversion Complete", f"Videos converted to {target_fps} FPS in subfolder '{output_subdir}'. Reloading folder.")
                    # Automatically load the new folder
                    new_folder_path = os.path.join(self.folder_path, output_subdir)
                    self.folder_path = new_folder_path # Update main path
                    self.loader.load_folder_contents() # Reload contents
                else:
                    QMessageBox.critical(self, "Conversion Failed", "FPS conversion failed. Check console for details.")
            else:
                 print("Conversion cancelled or invalid values.")

    # --- Helper to format timecodes ---
    def _format_timecode(self, frame_number, fps):
        if fps <= 0:
            return "--:--:--.---"
        total_seconds = frame_number / fps
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int((total_seconds - int(total_seconds)) * 1000)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
        else:
            return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

    # --- Method to update the current frame label ---
    def update_current_frame_label(self, current_frame, total_frames, fps):
        if not hasattr(self, 'current_frame_label'): # Check if UI is initialized
             return
        current_tc = self._format_timecode(current_frame, fps)
        total_tc = self._format_timecode(total_frames, fps)
        if total_frames > 0:
            self.current_frame_label.setText(f"Frame: {current_frame} / {total_frames - 1}   ({current_tc} / {total_tc})")
        else:
            self.current_frame_label.setText("Frame: - / -   (--:--:--.-- / --:--:--.--)")

    # --- Slot Methods for New Frame Controls ---
    def _step_frame_backward(self):
        self.editor.step_frame(-1)

    def _step_frame_forward(self):
        self.editor.step_frame(1)

    def _goto_frame(self):
        try:
            target_frame = int(self.goto_frame_input.text())
            self.editor.goto_frame(target_frame)
        except ValueError:
            print("Invalid frame number entered.")
            # Optionally clear the input or show a brief message
            self.goto_frame_input.clear()

# --- FPS Conversion Dialog --- 
class ConvertFpsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Convert Video FPS")
        
        self.layout = QFormLayout(self)
        
        # Target FPS Input
        self.fps_input = QSpinBox()
        self.fps_input.setRange(1, 120) # Reasonable range
        self.fps_input.setValue(30) # Default to 30 FPS
        self.layout.addRow("Target FPS:", self.fps_input)
        
        # Output Subfolder Input
        self.subdir_input = QLineEdit()
        self.subdir_input.setPlaceholderText("e.g., converted_30fps")
        self.layout.addRow("Output Subfolder Name:", self.subdir_input)
        
        # Update default subdir name when FPS changes
        self.fps_input.valueChanged.connect(self._update_default_subdir)
        self._update_default_subdir() # Set initial value
        
        # OK and Cancel Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept) # accept() closes with QDialog.Accepted
        self.button_box.rejected.connect(self.reject) # reject() closes with QDialog.Rejected
        self.layout.addWidget(self.button_box)
        
    def _update_default_subdir(self):
        fps = self.fps_input.value()
        self.subdir_input.setText(f"converted_{fps}fps")
        
    def get_values(self):
        """Returns the selected FPS and subfolder name if accepted."""
        # Basic validation could be added here before returning
        fps = self.fps_input.value()
        subdir = self.subdir_input.text().strip()
        if not subdir: # Ensure subdir name is not empty
             # Optionally show a warning
             return None, None
        # Add more validation for subdir name (e.g., no invalid characters)?
        return fps, subdir

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Use explicit path check
    css_path = os.path.join("styles", "dark_mode.css")
    if os.path.exists(css_path):
        try:
            with open(css_path, "r") as file:
                app.setStyleSheet(file.read())
        except Exception as e:
            print(f"Error loading stylesheet: {e}")
    else:
        print(f"Stylesheet not found at {css_path}")

    try:
        window = VideoCropper()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        import traceback
        print(f"An error occurred: {e}")
        traceback.print_exc() # Print full traceback
        input("Press Enter to exit...")
        sys.exit(1)
