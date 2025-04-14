# video_editor.py
import cv2
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QPen
from PyQt6.QtCore import Qt, QTimer, QRectF
from scripts.interactive_crop_region import InteractiveCropRegion  # New interactive crop region

class VideoEditor:
    def __init__(self, main_app):
        self.main_app = main_app
        self.playback_timer = QTimer() # Use a persistent timer
        self.playback_timer.timeout.connect(self._playback_step)
        # Add state flag for range playback
        self.is_playing_range = False
        self.current_range_end_frame = -1 # Store end frame for range playback

    def load_video_properties(self, video_path):
        """Opens video, gets properties, displays first frame. Returns True on success."""
        try:
            if self.main_app.cap:
                 self.main_app.cap.release()
            self.main_app.cap = cv2.VideoCapture(video_path)
            if not self.main_app.cap.isOpened():
                print(f"Error: Could not open video file: {video_path}")
                self.main_app.cap = None # Ensure cap is None on failure
                return False
                
            self.main_app.frame_count = int(self.main_app.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.main_app.original_width = int(self.main_app.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.main_app.original_height = int(self.main_app.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            # self.main_app.clip_aspect_ratio = self.main_app.original_width / self.main_app.original_height # Aspect ratio handled elsewhere
            
            if self.main_app.frame_count <= 0:
                 print(f"Warning: Video has {self.main_app.frame_count} frames. Cannot process.")
                 self.main_app.cap.release()
                 self.main_app.cap = None
                 return False
                 
            # Set slider range and enable
            self.main_app.slider.setMaximum(self.main_app.frame_count - 1)
            self.main_app.slider.setEnabled(True)
            self.main_app.slider.setValue(0) # Start slider at 0
            
            # Display the first frame
            return self.update_frame_display(0)

        except Exception as e:
            print(f"Error loading video properties: {e}")
            if self.main_app.cap:
                 self.main_app.cap.release()
            self.main_app.cap = None
            return False

    def update_frame_display(self, frame_number):
        """Sets capture to specific frame and displays it."""
        if not self.main_app.cap or not self.main_app.cap.isOpened():
             print("⚠️ Cannot update display: Video capture not ready.")
             return False
             
        if frame_number < 0 or frame_number >= self.main_app.frame_count:
             print(f"⚠️ Cannot update display: Frame {frame_number} out of bounds (0-{self.main_app.frame_count-1}).")
             # Optionally clamp frame_number or just return False
             frame_number = max(0, min(frame_number, self.main_app.frame_count - 1))
             # return False 

        try:
            # Setting position and reading can be slow/inaccurate sometimes, grabbing helps?
            self.main_app.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            # for _ in range(2): # Optional grab frames
            #      self.main_app.cap.grab()
            ret, frame = self.main_app.cap.read()
            if ret:
                self.display_frame(frame)
                # Update slider if needed (e.g., if called not by slider itself)
                if self.main_app.slider.value() != frame_number:
                     self.main_app.slider.setValue(frame_number)                     
                return True
            else:
                print(f"Error: Could not read frame {frame_number}.")
                 # Attempt to reread from beginning if read fails?
                 # self.main_app.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                return False
        except Exception as e:
             print(f"Error updating frame display for frame {frame_number}: {e}")
             return False

    def display_frame(self, frame):
        if frame is None:
             print("⚠️ display_frame called with None frame.")
             return
        try:
            # Convert and scale frame
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)
            
            # Use view port dimensions for scaling
            view_width = self.main_app.graphics_view.viewport().width() - 2 # Subtract border/padding
            view_height = self.main_app.graphics_view.viewport().height() - 2
            
            scaled_pixmap = pixmap.scaled(
                view_width,
                view_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # Update pixmap item and view
            self.main_app.pixmap_item.setPixmap(scaled_pixmap)
            # Fit view AFTER setting pixmap
            self.main_app.graphics_view.fitInView(self.main_app.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            # Set scene rect AFTER fitting view to ensure coordinates match
            self.main_app.scene.setSceneRect(self.main_app.pixmap_item.boundingRect())
        except Exception as e:
            print(f"Error displaying frame: {e}")

    def scrub_video(self, position):
        """Called when slider is moved interactively."""
        if self.main_app.cap:
            # Just update the frame display based on slider position
            self.update_frame_display(position)
            # No need to update trim points here anymore

    def show_thumbnail(self, event):
        # This logic seems okay, but relies on accurate frame seeking
        if not self.main_app.cap or not self.main_app.cap.isOpened():
            return
        try:
            pos = event.position().toPoint()
            slider_width = self.main_app.slider.width()
            if slider_width <= 0: return # Avoid division by zero
            
            frame_pos = int((pos.x() / slider_width) * self.main_app.frame_count)
            frame_pos = max(0, min(frame_pos, self.main_app.frame_count - 1))
            
            # Store current position to restore later
            current_cap_pos = self.main_app.cap.get(cv2.CAP_PROP_POS_FRAMES)
            
            self.main_app.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
            ret, frame = self.main_app.cap.read()
            
            # Restore previous position
            self.main_app.cap.set(cv2.CAP_PROP_POS_FRAMES, current_cap_pos) 
            
            if ret and frame is not None:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                if h == 0 or w == 0: return # Invalid frame dimensions
                bytes_per_line = ch * w
                q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(q_img)
                
                # Calculate thumbnail size (use fixed size or aspect ratio)
                thumbnail_height = 90 # Keep it smaller
                thumbnail_width = 160
                # thumbnail_aspect = self.main_app.original_width / self.main_app.original_height if self.main_app.original_height > 0 else 16/9
                # thumbnail_width = int(thumbnail_height * thumbnail_aspect)
                
                self.main_app.thumbnail_label.setFixedSize(thumbnail_width, thumbnail_height)
                self.main_app.thumbnail_image_label.setGeometry(0, 0, thumbnail_width, thumbnail_height)
                scaled_pixmap = pixmap.scaled(thumbnail_width, thumbnail_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.main_app.thumbnail_image_label.setPixmap(scaled_pixmap)
                
                # Position tooltip relative to slider
                slider_global_pos = self.main_app.slider.mapToGlobal(pos)
                tooltip_x = slider_global_pos.x() - thumbnail_width // 2
                tooltip_y = slider_global_pos.y() - thumbnail_height - 10 # Position above slider
                self.main_app.thumbnail_label.move(tooltip_x, tooltip_y)
                self.main_app.thumbnail_label.show()
            else:
                self.main_app.thumbnail_label.hide()
        except Exception as e:
             print(f"Error showing thumbnail: {e}")
             self.main_app.thumbnail_label.hide()

    def toggle_loop_playback(self):
        """Toggles playback looping within the selected range."""
        if self.main_app.is_playing or self.is_playing_range: # Stop any other playback first
            self.stop_playback()

        self.main_app.loop_playback = not self.main_app.loop_playback
        if self.main_app.loop_playback:
            print("Starting loop playback...")
            self._start_playback(loop=True)
        else:
            print("Stopping loop playback...")
            self.stop_playback()

    def toggle_play_forward(self):
        """Toggles normal playback from current position."""
        if self.main_app.loop_playback or self.is_playing_range: # Stop any other playback first
            self.stop_playback()

        self.main_app.is_playing = not self.main_app.is_playing
        if self.main_app.is_playing:
            print("Starting normal playback...")
            self._start_playback(loop=False)
        else:
            print("Stopping normal playback...")
            self.stop_playback()
            
    def toggle_range_playback(self, start_frame, end_frame):
        """Starts or stops playback limited to the given start/end frames."""
        if self.is_playing_range: # If already playing this range, stop it
             print("Stopping range playback...")
             self.stop_playback()
        elif self.main_app.is_playing or self.main_app.loop_playback: # Stop other modes first
             print("Stopping other playback before starting range playback...")
             self.stop_playback()
             self._start_playback(loop=False, range_playback=True, start_frame=start_frame, end_frame=end_frame)
        else: # Start range playback
             self._start_playback(loop=False, range_playback=True, start_frame=start_frame, end_frame=end_frame)

    def _start_playback(self, loop=False, range_playback=False, start_frame=None, end_frame=None):
        if not self.main_app.cap or not self.main_app.cap.isOpened():
            print("Cannot start playback: Video not ready.")
            self.main_app.is_playing = False
            self.main_app.loop_playback = False
            self.is_playing_range = False
            return

        self.main_app.is_playing = not loop and not range_playback
        self.main_app.loop_playback = loop
        self.is_playing_range = range_playback

        # Determine start/end based on mode
        self.current_playback_start_frame = 0
        self.current_playback_end_frame = self.main_app.frame_count # Default to full video
        playback_mode_msg = "normal"

        if loop:
            playback_mode_msg = "looping"
            range_data = self.main_app.find_range_by_id(self.main_app.current_selected_range_id)
            if range_data:
                self.current_playback_start_frame = range_data['start']
                self.current_playback_end_frame = range_data['end']
                # Set starting position for loop
                current_frame = int(self.main_app.cap.get(cv2.CAP_PROP_POS_FRAMES))
                # If current frame outside loop range, reset to start
                if not (self.current_playback_start_frame <= current_frame < self.current_playback_end_frame):
                    start_seek = self.current_playback_start_frame
                    self.main_app.cap.set(cv2.CAP_PROP_POS_FRAMES, start_seek)
                    self.main_app.slider.setValue(start_seek)
            else:
                print("Cannot loop: No range selected.")
                self.stop_playback()
                return
        elif range_playback:
            playback_mode_msg = "range"
            if start_frame is not None and end_frame is not None and start_frame < end_frame:
                 self.current_playback_start_frame = start_frame
                 self.current_playback_end_frame = end_frame
                 self.current_range_end_frame = end_frame # Store specifically for range check
                 # Set starting position for range playback
                 start_seek = self.current_playback_start_frame
                 self.main_app.cap.set(cv2.CAP_PROP_POS_FRAMES, start_seek)
                 self.main_app.slider.setValue(start_seek)
            else:
                 print(f"Cannot start range playback: Invalid start/end frames ({start_frame}, {end_frame})")
                 self.stop_playback()
                 return
        else: # Normal play forward from current position
            self.current_playback_start_frame = self.main_app.slider.value()
            # End frame remains the total frame count

        print(f"Starting {playback_mode_msg} playback from {self.current_playback_start_frame} to {self.current_playback_end_frame}")
        # Use a timer for smoother playback
        fps = self.main_app.cap.get(cv2.CAP_PROP_FPS)
        interval = int(1000 / fps) if fps > 0 else 33 # Default to ~30fps
        self.playback_timer.start(interval)
        self._playback_step() # Process first frame immediately

    def _playback_step(self):
        """Reads and displays the next frame during playback."""
        # Check if any playback mode is active
        is_active = self.main_app.is_playing or self.main_app.loop_playback or self.is_playing_range
        if not self.main_app.cap or not self.main_app.cap.isOpened() or not is_active:
            self.stop_playback() # Ensure timer stops if state is inconsistent
            return

        current_frame_pos = int(self.main_app.cap.get(cv2.CAP_PROP_POS_FRAMES))

        # --- Check End Conditions --- 
        # 1. Range Playback End
        if self.is_playing_range and current_frame_pos >= self.current_range_end_frame:
             print("Range playback finished.")
             self.stop_playback()
             # Optionally seek back to start of range after stopping?
             # self.update_frame_display(self.current_playback_start_frame)
             return
             
        # 2. Loop Playback Restart
        elif self.main_app.loop_playback and current_frame_pos >= self.current_playback_end_frame:
            print("Looping back to start...")
            start_seek = self.current_playback_start_frame
            self.main_app.cap.set(cv2.CAP_PROP_POS_FRAMES, start_seek)
            current_frame_pos = start_seek # Update position for read check below
            self.main_app.slider.setValue(current_frame_pos)
            
        # 3. Normal Playback End
        elif self.main_app.is_playing and current_frame_pos >= self.current_playback_end_frame:
            print("Normal playback finished.")
            self.stop_playback()
            return
            
        # --- Read and Display Frame --- 
        ret, frame = self.main_app.cap.read()
        if ret and frame is not None:
            # Update slider to reflect actual read position (before display)
            # POS_FRAMES gives the index of the *next* frame to be decoded, so current is pos-1
            actual_pos = max(0, current_frame_pos - 1) 
            self.main_app.slider.setValue(actual_pos)
            self.display_frame(frame)
        else:
            print("End of stream or read error during playback.")
            self.stop_playback()

    def stop_playback(self):
        """Stops any active playback timer and resets flags."""
        if self.playback_timer.isActive():
            self.playback_timer.stop()
            print("Playback timer stopped.")
            
        was_playing = self.main_app.is_playing or self.main_app.loop_playback or self.is_playing_range
            
        self.main_app.is_playing = False
        self.main_app.loop_playback = False
        self.is_playing_range = False
        self.current_range_end_frame = -1
        
        if was_playing:
             print("Playback stopped.")
        # Optionally reset frame to start of selected range after stopping?
        # if self.main_app.cap and self.main_app.current_selected_range_id:
        #     range_data = self.main_app.find_range_by_id(self.main_app.current_selected_range_id)
        #     if range_data:
        #         self.update_frame_display(range_data['start'])

    def next_clip(self):
        # This should advance the main video list selection
        current_row = self.main_app.video_list.currentRow()
        next_row = min(self.main_app.video_list.count() - 1, current_row + 1)
        if next_row != current_row:
             self.main_app.video_list.setCurrentRow(next_row)
             # load_video is automatically called by itemClicked signal, no need to call manually
             # self.main_app.loader.load_video(self.main_app.video_list.item(next_row))
        else:
             print("Already at the last video.")

    def navigate_clip(self, direction):
        # This could potentially navigate the clip range list instead?
        # For now, keep it simple or map to prev/next video
        if direction < 0: # Previous video
             current_row = self.main_app.video_list.currentRow()
             prev_row = max(0, current_row - 1)
             if prev_row != current_row:
                 self.main_app.video_list.setCurrentRow(prev_row)
             else:
                 print("Already at the first video.")
        else: # Next video
             self.next_clip()
