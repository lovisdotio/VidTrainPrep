# video_editor.py
import cv2, time
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
        # NEW: Add fps cache to avoid repeated cap.get calls
        self.current_fps = 0.0

    def load_video_properties(self, video_path):
        """Opens video, gets properties, displays first frame. Returns True on success."""
        try:
            if self.main_app.cap:
                 self.main_app.cap.release()
            self.main_app.cap = cv2.VideoCapture(video_path)
            if not self.main_app.cap.isOpened():
                print(f"Error: Could not open video file: {video_path}")
                self.main_app.cap = None
                self.current_fps = 0.0 # Reset FPS cache
                return False
                
            self.main_app.frame_count = int(self.main_app.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.main_app.original_width = int(self.main_app.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.main_app.original_height = int(self.main_app.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.current_fps = self.main_app.cap.get(cv2.CAP_PROP_FPS) # Cache FPS
            if self.current_fps <= 0:
                print("Warning: Could not determine video FPS. Using fallback 30.")
                self.current_fps = 30.0 # Fallback FPS
            
            if self.main_app.frame_count <= 0:
                 print(f"Warning: Video has {self.main_app.frame_count} frames. Cannot process.")
                 self.main_app.cap.release()
                 self.main_app.cap = None
                 self.current_fps = 0.0
                 return False
                 
            # Set slider range and enable
            self.main_app.slider.setMaximum(self.main_app.frame_count - 1)
            self.main_app.slider.setEnabled(True)
            self.main_app.slider.setValue(0) # Start slider at 0
            
            # Display the first frame (this now updates the label too)
            return self.update_frame_display(0)

        except Exception as e:
            print(f"Error loading video properties: {e}")
            if self.main_app.cap:
                 self.main_app.cap.release()
            self.main_app.cap = None
            self.current_fps = 0.0
            return False

    def update_frame_display(self, frame_number):
        """Sets capture to specific frame, displays it, and updates the frame label."""
        if not self.main_app.cap or not self.main_app.cap.isOpened():
             print("⚠️ Cannot update display: Video capture not ready.")
             # Update label to show error/unknown state?
             # self.main_app.update_current_frame_label(-1, self.main_app.frame_count, self.current_fps)
             return False

        # Clamp frame number
        frame_number = int(round(frame_number)) # Ensure integer
        frame_number = max(0, min(frame_number, self.main_app.frame_count - 1))

        try:
            # Check if we are already at the desired frame (avoids unnecessary seek)
            # Note: CAP_PROP_POS_FRAMES gives the *next* frame index
            current_pos = int(self.main_app.cap.get(cv2.CAP_PROP_POS_FRAMES))
            # If seeking to the same frame or the frame just read, don't seek again
            if current_pos == frame_number + 1 or current_pos == frame_number:
                 # Read might still be needed if we only seeked but didn't read
                 pass # We might need to read anyway
            else:
                self.main_app.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

            ret, frame = self.main_app.cap.read()
            if ret:
                self.display_frame(frame)

                # Update slider if its value doesn't match (avoiding loops)
                # Block signals temporarily to prevent slider.valueChanged triggering this again
                self.main_app.slider.blockSignals(True)
                self.main_app.slider.setValue(frame_number)
                self.main_app.slider.blockSignals(False)

                # Update the current frame label in the main app
                self.main_app.update_current_frame_label(frame_number, self.main_app.frame_count, self.current_fps)
                return True
            else:
                print(f"Error: Could not read frame {frame_number}.")
                # Update label to show error state?
                # self.main_app.update_current_frame_label(frame_number, self.main_app.frame_count, self.current_fps) # Show last attempted frame
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
        """Called when slider is moved interactively OR value changes."""
        if self.main_app.cap:
            # Stop any playback when scrubbing starts
            if self.playback_timer.isActive():
                self.stop_playback()
            # Update the frame display based on slider position
            self.update_frame_display(position)

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
        # Set initial frame correctly
        initial_seek_frame = self.current_playback_start_frame

        # Seek and update display/label for the starting frame
        print(f"Seeking to start frame {initial_seek_frame} for playback...")
        # update_frame_display handles seek, display, slider, and label update
        if not self.update_frame_display(initial_seek_frame):
            print(f"Error seeking to start frame {initial_seek_frame}. Aborting playback.")
            self.stop_playback()
            return

        # Use a timer for smoother playback
        interval = int(1000 / self.current_fps) if self.current_fps > 0 else 33
        self.playback_timer.start(interval)
        # Don't call _playback_step immediately, the timer will trigger it.

    def _playback_step(self):
        """Reads and displays the next frame during playback."""
        is_active = self.main_app.is_playing or self.main_app.loop_playback or self.is_playing_range
        if not self.main_app.cap or not self.main_app.cap.isOpened() or not is_active:
            self.stop_playback()
            return

        # Get position *before* reading
        current_frame_pos = int(self.main_app.cap.get(cv2.CAP_PROP_POS_FRAMES))

        # --- Check End Conditions ---
        if self.is_playing_range and current_frame_pos >= self.current_range_end_frame:
             print("Range playback finished.")
             self.stop_playback()
             # Go back to start of range after stopping?
             self.update_frame_display(self.current_playback_start_frame)
             return

        elif self.main_app.loop_playback and current_frame_pos >= self.current_playback_end_frame:
            print("Looping back to start...")
            start_seek = self.current_playback_start_frame
            self.main_app.cap.set(cv2.CAP_PROP_POS_FRAMES, start_seek)
            current_frame_pos = start_seek # Update position for read check below
            # No need to update slider/label here, the read below will handle it

        elif self.main_app.is_playing and current_frame_pos >= self.current_playback_end_frame:
            print("Normal playback finished.")
            self.stop_playback()
            # Update label to show the last frame?
            # self.main_app.update_current_frame_label(self.main_app.frame_count - 1, self.main_app.frame_count, self.current_fps)
            return

        # --- Read and Display Frame ---
        ret, frame = self.main_app.cap.read()
        if ret and frame is not None:
            # Calculate the frame index that was just *read*
            actual_read_frame = current_frame_pos # Since POS_FRAMES is next index before read
            if actual_read_frame >= self.main_app.frame_count: # Handle potential off-by-one at end
                actual_read_frame = self.main_app.frame_count - 1

            # Display frame first
            self.display_frame(frame)

            # Update slider (block signals)
            self.main_app.slider.blockSignals(True)
            self.main_app.slider.setValue(actual_read_frame)
            self.main_app.slider.blockSignals(False)

            # Update label
            self.main_app.update_current_frame_label(actual_read_frame, self.main_app.frame_count, self.current_fps)

        else:
            print("End of stream or read error during playback.")
            self.stop_playback()
            # Update label to show the last successfully read frame?
            last_known_frame = current_frame_pos -1 if current_frame_pos > 0 else 0
            last_known_frame = max(0, min(last_known_frame, self.main_app.frame_count - 1))
            self.main_app.update_current_frame_label(last_known_frame, self.main_app.frame_count, self.current_fps)

    def stop_playback(self):
        """Stops any active playback timer and resets flags."""
        was_active = self.playback_timer.isActive()
        if was_active:
            self.playback_timer.stop()
            print("Playback timer stopped.")

        # Reset flags regardless of timer state
        self.main_app.is_playing = False
        self.main_app.loop_playback = False
        self.is_playing_range = False
        self.current_range_end_frame = -1

        # No need to update label here usually, last frame display should be correct

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

    # --- NEW Frame Navigation Methods ---

    def step_frame(self, delta):
        """Steps forward or backward by a specific number of frames (delta)."""
        if not self.main_app.cap or not self.main_app.slider.isEnabled():
            return
        if self.playback_timer.isActive(): # Stop playback if active
            self.stop_playback()

        current_frame = self.main_app.slider.value()
        target_frame = current_frame + delta
        # Clamping happens inside update_frame_display
        self.update_frame_display(target_frame)

    def jump_frames(self, delta_seconds):
        """Jumps forward or backward by a number of seconds."""
        if not self.main_app.cap or not self.main_app.slider.isEnabled() or self.current_fps <= 0:
            return
        if self.playback_timer.isActive(): # Stop playback if active
            self.stop_playback()

        frame_delta = int(round(delta_seconds * self.current_fps))
        if frame_delta == 0: # If jump is less than one frame, step at least one
             frame_delta = 1 if delta_seconds > 0 else -1

        current_frame = self.main_app.slider.value()
        target_frame = current_frame + frame_delta
        # Clamping happens inside update_frame_display
        self.update_frame_display(target_frame)

    def goto_frame(self, frame_number):
        """Jumps directly to a specific frame number."""
        if not self.main_app.cap or not self.main_app.slider.isEnabled():
            return
        if self.playback_timer.isActive(): # Stop playback if active
            self.stop_playback()

        # Clamping happens inside update_frame_display
        self.update_frame_display(frame_number)
