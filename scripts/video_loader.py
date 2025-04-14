import os, json
from PyQt6.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor  # Added import for QColor
import ffmpeg # Import ffmpeg-python

class VideoLoader:
    def __init__(self, main_app):
        self.main_app = main_app
        self.session_file = "session_data.json"

    def load_folder(self):
        folder = QFileDialog.getExistingDirectory(self.main_app, "Select Folder")
        if folder:
            self.main_app.folder_path = folder
            # Check if we already have saved session data for this folder.
            if folder in self.main_app.folder_sessions:
                self.main_app.video_files = self.main_app.folder_sessions[folder]
                self.refresh_video_list()
            else:
                self.load_folder_contents()

    def load_folder_contents(self):
        files = [f for f in os.listdir(self.main_app.folder_path) 
                if f.lower().endswith(('.mp4', '.avi', '.mov'))]
        
        # Use saved session data for this folder if available.
        previous_videos = {}
        if self.main_app.folder_path in self.main_app.folder_sessions:
            previous_videos = {
                entry["display_name"]: entry 
                for entry in self.main_app.folder_sessions[self.main_app.folder_path]
            }
        
        new_video_files = []
        for f in files:
            display_name = f
            # If this video was loaded previously in this folder, preserve its settings.
            video_entry = previous_videos.get(display_name, {
                "original_path": os.path.join(self.main_app.folder_path, f),
                "display_name": display_name,
                "copy_number": 0,
                "export_enabled": False  # Default state
            })
            new_video_files.append(video_entry)
        
        # Append any duplicate entries (saved previously) that aren't in the file list.
        for display_name, entry in previous_videos.items():
            if display_name not in files:
                new_video_files.append(entry)
        
        self.main_app.video_files = new_video_files
        # Save this folder's state.
        self.main_app.folder_sessions[self.main_app.folder_path] = new_video_files
        
        self.main_app.video_list.clear()
        for entry in self.main_app.video_files:
            self.add_video_item(entry["display_name"])
        
        self.save_session()

    def add_video_item(self, display_name):
        item = QListWidgetItem(display_name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        # Look up the saved export state.
        entry = next((e for e in self.main_app.video_files if e["display_name"] == display_name), None)
        if entry and entry.get("export_enabled", False):
            item.setCheckState(Qt.CheckState.Checked)
        else:
            item.setCheckState(Qt.CheckState.Unchecked)
        self.update_list_item_color(item)
        self.main_app.video_list.addItem(item)

    def update_list_item_color(self, item):
        idx = self.main_app.video_list.row(item)
        if idx >= 0 and idx < len(self.main_app.video_files):
            # Update the export_enabled flag in the video_files entry.
            self.main_app.video_files[idx]["export_enabled"] = (item.checkState() == Qt.CheckState.Checked)
        if item.checkState() == Qt.CheckState.Checked:
            # Use a darker green.
            item.setBackground(QColor(0, 100, 0))
        else:
            item.setBackground(Qt.GlobalColor.transparent)
        
        # Save the session immediately after updating the state.
        self.save_session()


    def load_video(self, item):
        idx = self.main_app.video_list.row(item)
        if idx < 0 or idx >= len(self.main_app.video_files):
            print("⚠️ Invalid video list index.")
            return
            
        video_entry = self.main_app.video_files[idx]
        original_path = video_entry.get("original_path")
        display_name = video_entry.get("display_name")

        if not original_path or not os.path.exists(original_path):
            QMessageBox.critical(self.main_app, "Error", f"Video file not found: {original_path or display_name}")
            # Optionally remove the invalid entry from the list?
            return

        print(f"Loading video: {display_name} (Source: {original_path})")
        self.main_app.current_video_original_path = original_path
        self.main_app.current_selected_range_id = None # Reset selected range

        if self.main_app.cap:
            self.main_app.cap.release()
        self.main_app.cap = None # Ensure cap is None before loading

        # Clear visual crop from previous video/range
        self.main_app.clear_crop_region_controller()
        
        # --- Load Video Properties (using editor) ---
        # This part also loads the first frame into the viewer
        success = self.main_app.editor.load_video_properties(original_path)
        if not success:
             print(f"Error loading video properties for {original_path}")
             self.main_app.current_video_original_path = None
             # Clear UI elements associated with video loading
             self.main_app.slider.setEnabled(False)
             self.main_app.clip_length_label.setText("Clip Length: 0 frames | Video Length: 0 frames")
             self.main_app.clip_range_list.clear()
             self.main_app.start_frame_input.setText("0")
             self.main_app.end_frame_input.setText("0")
             # Maybe clear the graphics view?
             # self.main_app.scene.clear() # This might remove the pixmap item too, be careful
             # self.main_app.pixmap_item = QGraphicsPixmapItem() # Re-add if cleared
             # self.main_app.scene.addItem(self.main_app.pixmap_item)
             return
        else:
             # Update total length label now that frame_count is known
             self.main_app.clip_length_label.setText(f"Clip Length: ... frames | Video Length: {self.main_app.frame_count} frames")

        # --- Populate Clip Range List ---
        self.main_app.clip_range_list.clear() # Clear previous ranges
        ranges_loaded = False
        if original_path in self.main_app.video_data:
            video_ranges = self.main_app.video_data[original_path].get("ranges", [])
            if video_ranges:
                print(f"   Found {len(video_ranges)} existing ranges for {original_path}")
                # Sort ranges by index just in case
                video_ranges.sort(key=lambda r: r.get('index', 0))
                for range_data in video_ranges:
                    list_item = QListWidgetItem()
                    self.main_app._update_list_item_text(list_item, range_data)
                    self.main_app.clip_range_list.addItem(list_item)
                ranges_loaded = True
        
        # If no ranges were loaded or found for this video, add a default one
        if not ranges_loaded:
            print(f"   No existing ranges found for {original_path}. Adding default range.")
            self.main_app.add_new_range() # This will also select it
        else:
            # If ranges were loaded, select the first one
            if self.main_app.clip_range_list.count() > 0:
                self.main_app.clip_range_list.setCurrentRow(0)
                self.main_app.select_range(self.main_app.clip_range_list.item(0))
            else:
                # Should not happen if add_new_range was called, but handle defensively
                 self.main_app.current_selected_range_id = None
                 self.main_app.start_frame_input.setText("0")
                 self.main_app.end_frame_input.setText("0")

        # Update the simple caption input if it was saved (optional, based on old logic)
        # self.main_app.simple_caption = self.main_app.folder_sessions.get(self.main_app.folder_path, {}).get("captions", {}).get(display_name, "")
        # self.main_app.caption_input.setText(self.main_app.simple_caption)

    def duplicate_clip(self):
        current_item = self.main_app.video_list.currentItem()
        if not current_item:
            return
        current_idx = self.main_app.video_list.row(current_item)
        original_entry = self.main_app.video_files[current_idx]
        base_name, ext = os.path.splitext(original_entry["display_name"])
        # Start with the next copy number.
        new_copy = original_entry["copy_number"] + 1
        new_display = f"{base_name}_{new_copy}{ext}"
        # Check for name collisions.
        existing_names = [entry["display_name"] for entry in self.main_app.video_files]
        while new_display in existing_names:
            new_copy += 1
            new_display = f"{base_name}_{new_copy}{ext}"
        new_entry = {
            "original_path": original_entry["original_path"],
            "display_name": new_display,
            "copy_number": new_copy,
            "export_enabled": original_entry.get("export_enabled", False)
        }
        self.main_app.video_files.append(new_entry)
        self.add_video_item(new_display)
        self.main_app.crop_regions[new_display] = self.main_app.crop_regions.get(original_entry["display_name"], None)
        self.main_app.trim_points[new_display] = self.main_app.trim_points.get(original_entry["display_name"], 0)
        self.save_session()

    def clear_crop_region(self):
        if self.main_app.current_video and self.main_app.current_video in self.main_app.crop_regions:
            self.main_app.crop_regions[self.main_app.current_video] = None
            if self.main_app.current_rect:
                self.main_app.scene.removeItem(self.main_app.current_rect)
                self.main_app.current_rect = None

    def refresh_video_list(self):
        self.main_app.video_list.clear()
        for entry in self.main_app.video_files:
            self.add_video_item(entry["display_name"])

    def load_session(self):
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, "r") as file:
                    session_data = json.load(file)
                    self.main_app.folder_path = session_data.get("folder_path", "")
                    # Load video_files and folder_sessions as before
                    self.main_app.video_files = session_data.get("video_files", [])
                    self.main_app.folder_sessions = session_data.get("folder_sessions", {})
                    # Load the new video_data structure containing ranges
                    self.main_app.video_data = session_data.get("video_data", {})
                    # Load other settings
                    self.main_app.longest_edge = session_data.get("longest_edge", 1024)
                    print("Session loaded successfully.")
            except json.JSONDecodeError:
                 print(f"Error: Could not decode session file: {self.session_file}")
                 # Reset to defaults if file is corrupted
                 self.main_app.folder_path = ""
                 self.main_app.video_files = []
                 self.main_app.folder_sessions = {}
                 self.main_app.video_data = {}
            except Exception as e:
                 print(f"Error loading session: {e}")
                 # Reset to defaults on other errors
                 self.main_app.folder_path = ""
                 self.main_app.video_files = []
                 self.main_app.folder_sessions = {}
                 self.main_app.video_data = {}
                 
        # Refresh list if folder exists (might be redundant with load_folder logic)
        # if self.main_app.folder_path and os.path.exists(self.main_app.folder_path):
        #     # Logic to reload/refresh list based on loaded session is complex here
        #     # It's better handled when load_folder is called after startup
        #     pass

    def save_session(self):
        # Update the export_enabled flag from the UI before saving.
        for i in range(self.main_app.video_list.count()):
            item = self.main_app.video_list.item(i)
            # Ensure index is valid before accessing video_files
            if i < len(self.main_app.video_files):
                self.main_app.video_files[i]["export_enabled"] = (item.checkState() == Qt.CheckState.Checked)
            else:
                print(f"Warning: List item index {i} out of bounds for video_files during save.")
                
        # Update the folder_sessions mapping for the current folder.
        if self.main_app.folder_path: # Only save if a folder is loaded
            self.main_app.folder_sessions[self.main_app.folder_path] = self.main_app.video_files
        
        session_data = {
            "folder_path": self.main_app.folder_path,
            "video_files": self.main_app.video_files,
            "folder_sessions": self.main_app.folder_sessions,
            "video_data": self.main_app.video_data, # Save the new range data
            "longest_edge": self.main_app.longest_edge,
            # Remove obsolete keys from saving
            # "crop_regions": self.main_app.crop_regions, 
            # "trim_points": self.main_app.trim_points,
            # "trim_length": self.main_app.trim_length
        }
        try:
            with open(self.session_file, "w") as file:
                json.dump(session_data, file, indent=4) # Add indent for readability
            # print("Session saved.") # Optional: uncomment for confirmation
        except Exception as e:
            print(f"Error saving session: {e}")

    def convert_folder_fps(self, target_fps, output_subdir):
        """Converts all videos in the current folder to target_fps in a subfolder."""
        source_folder = self.main_app.folder_path
        if not source_folder or not os.path.isdir(source_folder):
            print("❌ Cannot convert: Source folder not valid.")
            return False
            
        output_folder = os.path.join(source_folder, output_subdir)
        try:
            os.makedirs(output_folder, exist_ok=True)
        except OSError as e:
            print(f"❌ Error creating output directory {output_folder}: {e}")
            return False

        print(f"Starting conversion to {target_fps} FPS in folder: {output_folder}")
        video_files_to_convert = [f for f in os.listdir(source_folder) 
                                   if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')) and \
                                   os.path.isfile(os.path.join(source_folder, f))]
                                   
        if not video_files_to_convert:
            print("ℹ️ No video files found in the source folder to convert.")
            # Return true because no work needed, but maybe show warning?
            QMessageBox.warning(self.main_app, "No Videos Found", "No video files (.mp4, .mov, .avi, .mkv) found in the selected folder.")
            return False # Indicate nothing was done / maybe not successful in user terms
            
        success_count = 0
        fail_count = 0
        
        for filename in video_files_to_convert:
            input_path = os.path.join(source_folder, filename)
            output_path = os.path.join(output_folder, filename) # Keep original filename
            print(f"  Converting: {filename} -> {target_fps} FPS...")
            
            # Check if output file already exists - skip for now
            if os.path.exists(output_path):
                 print(f"    ℹ️ Skipping: Output file already exists: {output_path}")
                 # We count existing as success for loading the folder later
                 success_count += 1 
                 continue
                 
            try:
                stream = ffmpeg.input(input_path)
                # Use filter for reliable FPS conversion, copy audio codec if possible
                stream = stream.filter('fps', fps=target_fps, round='up') 
                # Specify output options: H.264 codec, reasonable quality (crf 23), copy audio
                stream = stream.output(output_path, r=target_fps, **{'c:v': 'libx264', 'preset': 'medium', 'crf': 23, 'c:a': 'copy'})
                # Run quietly, overwrite existing (though we check above)
                stream.run(cmd=['ffmpeg', '-nostdin'], quiet=True, overwrite_output=True) # Add -nostdin
                print(f"    ✅ Conversion successful: {filename}")
                success_count += 1
            except ffmpeg.Error as e:
                print(f"    ❌ Error converting {filename}: {e.stderr.decode('utf8', errors='ignore')}")
                fail_count += 1
                # Try again without copying audio? Audio codec might be the issue
                try:
                     print(f"    Retrying {filename} without copying audio...")
                     stream = ffmpeg.input(input_path)
                     stream = stream.filter('fps', fps=target_fps, round='up') 
                     # Default audio codec (AAC usually)
                     stream = stream.output(output_path, r=target_fps, **{'c:v': 'libx264', 'preset': 'medium', 'crf': 23})
                     stream.run(cmd=['ffmpeg', '-nostdin'], quiet=True, overwrite_output=True)
                     print(f"    ✅ Retry successful (audio re-encoded): {filename}")
                     success_count += 1
                     fail_count -= 1 # Correct the fail count
                except ffmpeg.Error as e2:
                     print(f"    ❌ Retry failed for {filename}: {e2.stderr.decode('utf8', errors='ignore')}")
                except Exception as e_retry:
                     print(f"    ❌ Unexpected error during retry for {filename}: {e_retry}")

            except Exception as e:
                print(f"    ❌ Unexpected error converting {filename}: {e}")
                fail_count += 1
                
        print(f"Conversion finished. Success: {success_count}, Failed: {fail_count}")
        return fail_count == 0 # Return True only if all conversions succeeded or were skipped
