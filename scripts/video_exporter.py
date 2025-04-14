import os, ffmpeg, cv2
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt
import google.generativeai as genai
from google.api_core import exceptions # For specific error handling
from PIL import Image
import time # for potential retries

class VideoExporter:
    def __init__(self, main_app):
        self.main_app = main_app
        self.file_counter = 0  # Counter for incremental padding suffix
        self.gemini_model = None # Initialize Gemini model placeholder

    def _configure_gemini(self):
        """Configures the Gemini API client if not already configured."""
        if self.gemini_model:
            return True # Already configured

        api_key = self.main_app.gemini_api_key_input.text()
        if not api_key:
            print("❌ Gemini API Key is missing. Cannot generate captions.")
            # Optionally show a message box to the user
            # msg = QMessageBox()
            # msg.setIcon(QMessageBox.Icon.Warning)
            # msg.setText("Gemini API Key Missing")
            # msg.setInformativeText("Please enter your Gemini API key in the input field to generate captions.")
            # msg.setWindowTitle("API Key Error")
            # msg.exec()
            return False

        try:
            genai.configure(api_key=api_key)
            self.gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
            print("✅ Gemini API configured successfully using gemini-1.5-flash-latest.")
            return True
        except Exception as e:
            print(f"❌ Failed to configure Gemini API: {e}")
            self.gemini_model = None # Ensure model is None if config fails
            # Optionally show a more detailed error to the user
            # msg = QMessageBox()
            # msg.setIcon(QMessageBox.Icon.Critical)
            # msg.setText("Gemini API Configuration Error")
            # msg.setInformativeText(f"Failed to configure Gemini API: {e}")
            # msg.setWindowTitle("API Error")
            # msg.exec()
            return False

    def generate_gemini_caption(self, image_path, max_retries=3):
        """Generates a caption for the given image using the Gemini API."""
        if not self.gemini_model and not self._configure_gemini():
             # Attempt to configure if not already done, return if fails
            return None # Configuration failed or API key missing

        try:
            print(f"⏳ Generating Gemini caption for {os.path.basename(image_path)}...")
            img = Image.open(image_path)
            
            # Simple retry mechanism
            for attempt in range(max_retries):
                try:
                    # Use generate_content with stream=False for simpler handling
                    # Updated prompt for more detailed image captions
                    # Check for character name
                    char_name_widget = getattr(self.main_app, 'character_name_input', None)
                    char_name = char_name_widget.text().strip() if char_name_widget else ""
                    
                    name_clause = f" The main subject is named {char_name}. Describe {char_name}, including their" if char_name else " Describe the main subject(s), including"
                    
                    prompt = (
                        f"Analyze this image and provide a detailed description suitable for a video caption, "
                        f"covering the following aspects in approximately 80-100 words:\n"
                        f"1.  **Subject:**{name_clause} appearance, expression, clothing, and posture.\n"
                        f"2.  **Scene:** Describe the environment, background, and setting.\n"
                        f"3.  **Visual Style:** Describe the overall visual style (e.g., realistic, illustration, photographic style, specific art style if applicable).\n"
                        f"4.  **Atmosphere:** Describe the mood or feeling conveyed (e.g., mysterious, joyful, tense, solemn, vibrant).\n"
                        f"Output only the description."
                    )
                    response = self.gemini_model.generate_content(
                        [prompt, img], # Pass the updated prompt and the image
                        generation_config=genai.types.GenerationConfig(
                            # Optional: Add safety settings or other parameters if needed
                            # candidate_count=1,
                            # max_output_tokens=100, # Limit caption length
                            # temperature=0.4 
                        ),
                        stream=False # Get the full response at once
                    )
                    # Resolve the response to get the text part
                    response.resolve() 
                    
                    if response.parts:
                         # Remove potential markdown and leading/trailing whitespace
                        caption = response.text.strip().replace('*', '') 
                        print(f"✅ Generated caption: '{caption}'")
                        return caption
                    else:
                        print(f"❓ Gemini response did not contain text for {os.path.basename(image_path)}.")
                        return None # No text part in response
                        
                except Exception as e:
                    print(f"⚠️ Attempt {attempt + 1} failed: {e}")
                    if attempt + 1 == max_retries:
                        print(f"❌ Max retries reached for {os.path.basename(image_path)}. Giving up.")
                        return None
                    time.sleep(2 ** attempt) # Exponential backoff

            return None # Should not be reached if loop logic is correct

        except FileNotFoundError:
            print(f"❌ Image file not found: {image_path}")
            return None
        except Exception as e:
            # Catch other potential errors during image loading or API call
            print(f"❌ Error generating Gemini caption for {image_path}: {e}")
            # Consider more specific error handling based on potential Gemini API errors
            # if "API key not valid" in str(e): # Example specific error check
            #     self._show_api_key_error_message() # A helper to show QMessageBox
            #     self.gemini_model = None # Reset model state if key is invalid
            return None

    def generate_gemini_video_description(self, video_path, max_retries=3):
        """Generates a description for the given video file using the Gemini API."""
        if not self.gemini_model and not self._configure_gemini():
            return None # Configuration failed or API key missing

        print(f"⏳ Uploading video {os.path.basename(video_path)} for Gemini analysis...")
        video_file = None
        try:
            # Upload the video file
            video_file = genai.upload_file(path=video_path)
            print(f"   File uploaded: {video_file.name}, URI: {video_file.uri}")

            # Wait for the file to be processed and active
            while video_file.state.name == "PROCESSING":
                print("   Waiting for video processing...")
                time.sleep(5) # Check every 5 seconds
                video_file = genai.get_file(video_file.name)

            if video_file.state.name == "FAILED":
                print(f"❌ Video processing failed for {video_path}: {video_file.state}")
                return None
            elif video_file.state.name != "ACTIVE":
                print(f"❌ Video is not active after processing: {video_file.state.name}")
                return None
                
            print(f"✅ Video processed. Generating description for {os.path.basename(video_path)}...")
                
            # --- Generate Content using the uploaded video --- 
            # Updated prompt for more detailed video descriptions
            # Check for character name
            char_name_widget = getattr(self.main_app, 'character_name_input', None)
            char_name = char_name_widget.text().strip() if char_name_widget else ""
            
            name_clause = f" The main subject is named {char_name}. Describe {char_name}, including their" if char_name else " Describe the main subject(s), including"
            action_subject = char_name if char_name else "the subject(s)"
            
            prompt = (
                f"Analyze this video clip and provide a detailed description covering the following aspects "
                f"in approximately 80-100 words:\n"
                f"1.  **Subject:**{name_clause} appearance, expression, clothing, and posture.\n"
                f"2.  **Scene:** Describe the environment, background, and setting.\n"
                f"3.  **Action/Motion:** Describe the key actions or movements performed by {action_subject} and any significant camera movement (e.g., push in, pull out, pan, follow, orbit). Use simple, direct verbs.\n"
                f"4.  **Visual Style:** Describe the overall visual style (e.g., realistic, animated, cinematic, film grain, specific art style if applicable).\n"
                f"5.  **Atmosphere:** Describe the mood or feeling conveyed (e.g., mysterious, joyful, tense, solemn, vibrant).\n"
                f"Output only the description."
            )
            
            # Simple retry mechanism for generation
            for attempt in range(max_retries):
                try:
                    response = self.gemini_model.generate_content(
                        [prompt, video_file], # Pass the prompt and the file object
                        generation_config=genai.types.GenerationConfig(
                            # temperature=0.4 
                        ),
                        request_options={'timeout': 600} # Increased timeout for video
                    )
                    response.resolve()
                    
                    if response.parts:
                        description = response.text.strip().replace('*', '')
                        print(f"✅ Generated video description: '{description}'")
                        return description
                    else:
                        print(f"❓ Gemini response did not contain text for video {os.path.basename(video_path)}.")
                        return None # No text part
                        
                except exceptions.DeadlineExceeded:
                     print(f"⚠️ Attempt {attempt + 1} failed: Timeout during generation.")
                     if attempt + 1 == max_retries: return None
                     time.sleep(5)
                except Exception as e:
                    print(f"⚠️ Attempt {attempt + 1} failed during generation: {e}")
                    if attempt + 1 == max_retries: return None
                    time.sleep(2 ** attempt) # Exponential backoff
            
            return None # Should not be reached

        except Exception as e:
            print(f"❌ Error during video upload or description generation for {video_path}: {e}")
            return None
        finally:
            # --- IMPORTANT: Clean up the uploaded file --- 
            if video_file:
                try:
                    print(f"   Deleting uploaded file {video_file.name}...")
                    genai.delete_file(video_file.name)
                    print(f"   File {video_file.name} deleted.")
                except Exception as e:
                    print(f"⚠️ Failed to delete uploaded file {video_file.name}: {e}")

    @staticmethod
    def get_frame_count(video_path):
        try:
            probe = ffmpeg.probe(video_path)
            video_stream = next(stream for stream in probe['streams'] if stream['codec_type'] == 'video')
            return int(video_stream['nb_frames'])
        except Exception as e:
            print(f"❌ Error reading frame count from {video_path}: {e}")
            return -1

    def write_caption(self, output_file, caption_content=None):
        """
        Writes the provided caption_content into a .txt file 
        with the same base name as output_file.
        If caption_content is None, it uses the simple caption from the UI.
        Prepends the trigger word if provided.
        """
        caption = caption_content if caption_content is not None else getattr(self.main_app, 'simple_caption', '').strip()
        
        # Prepend trigger word if provided
        trigger_widget = getattr(self.main_app, 'trigger_word_input', None)
        if trigger_widget:
            trigger_word = trigger_widget.text().strip()
            if trigger_word and caption: # Only prepend if both trigger and caption exist
                caption = f"{trigger_word}, {caption}"

        if caption: # Only write if there's actually content
            base, _ = os.path.splitext(output_file)
            txt_file = base + ".txt"
            try:
                with open(txt_file, "w", encoding='utf-8') as f: # Specify encoding
                    f.write(caption)
                print(f"      ✅ Exported caption/description to {os.path.basename(txt_file)}")
            except Exception as e:
                print(f"      ❌ Error writing caption file {txt_file}: {e}")
        # else: # Optional: print if no caption was provided or generated
            # print(f"    ℹ️ No caption provided or generated for {output_file}.")

    def export_videos(self):
        """Exports selected videos based on their defined ranges and UI settings."""
        # --- Pre-checks and Folder Setup ---
        export_cropped_flag = self.main_app.export_cropped_checkbox.isChecked()
        export_uncropped_flag = self.main_app.export_uncropped_checkbox.isChecked()
        export_image_flag = self.main_app.export_image_checkbox.isChecked()
        generate_gemini_flag = self.main_app.gemini_caption_checkbox.isChecked()

        if not export_cropped_flag and not export_uncropped_flag and not export_image_flag:
            QMessageBox.warning(self.main_app, "Nothing to Export", "Please check at least one export option (Cropped, Uncropped, or Image).")
            return
            
        # Check Gemini API Key if Gemini generation is requested upfront
        if generate_gemini_flag:
            if not self.main_app.gemini_api_key_input.text():
                QMessageBox.warning(self.main_app, "API Key Missing", "Please enter your Gemini API key to generate descriptions/captions.")
                # Proceed but Gemini calls will fail later
            # Configure Gemini once at the start if the key is present and not already configured
            elif not self.gemini_model:
                self._configure_gemini() # Attempt configuration

        # Define output folders
        base_folder = self.main_app.folder_path
        if not base_folder or not os.path.isdir(base_folder):
            QMessageBox.critical(self.main_app, "Error", "Invalid base folder path selected.")
            return
             
        output_folder_cropped = os.path.join(base_folder, "cropped")
        output_folder_uncropped = os.path.join(base_folder, "uncropped")
        # Create folders only if needed by selected options
        if export_cropped_flag or (export_image_flag and export_cropped_flag):
            os.makedirs(output_folder_cropped, exist_ok=True)
        if export_uncropped_flag or (export_image_flag and export_uncropped_flag):
            os.makedirs(output_folder_uncropped, exist_ok=True)

        # Reset file counter (used if filename prefix is active)
        self.file_counter = 0
        items_to_export = []

        # --- Collect Selected Videos and Their Ranges ---
        selected_rows = {self.main_app.video_list.row(item) for item in self.main_app.video_list.selectedItems()} # Use selectedItems for clarity
        
        for i in range(self.main_app.video_list.count()):
            item = self.main_app.video_list.item(i)
            # Process checked items (using check state is more reliable for export intent)
            if item.checkState() == Qt.CheckState.Checked: 
                # Find corresponding entry in video_files (assuming order matches list index)
                if i >= len(self.main_app.video_files):
                     print(f"⚠️ Skipping checked item at index {i}: Mismatch with video_files data.")
                     continue
                video_entry = self.main_app.video_files[i] 
                original_path = video_entry.get("original_path")
                display_name = video_entry.get("display_name")
                
                if not original_path or not os.path.exists(original_path):
                    print(f"⚠️ Skipping invalid video entry: {display_name} (Path: {original_path})")
                    continue
                    
                # Get ranges for this video's original path
                video_ranges = self.main_app.video_data.get(original_path, {}).get("ranges", [])
                if not video_ranges:
                    print(f"ℹ️ No ranges defined for selected video: {display_name}. Skipping.")
                    continue
                    
                items_to_export.append({
                    "original_path": original_path,
                    "display_name": display_name, # Base display name for filename generation
                    "ranges": video_ranges
                })

        if not items_to_export:
             QMessageBox.information(self.main_app, "Nothing Selected", "Please select (check) at least one video file with defined ranges to export.")
             return
             
        print(f"--- Starting Export Process for {len(items_to_export)} video source(s) ---")

        # --- Process Each Selected Video Source ---
        for video_info in items_to_export:
            original_path = video_info["original_path"]
            base_display_name = video_info["display_name"] # Display name of the item in the list
            ranges = video_info["ranges"]
            print(f"Processing Source: {base_display_name} ({len(ranges)} ranges)")
            
            cap = None
            try:
                # Open video capture once per source file
                cap = cv2.VideoCapture(original_path)
                if not cap.isOpened():
                    print(f"❌ ERROR: Could not open video source {original_path}. Skipping.")
                    continue
                     
                fps = cap.get(cv2.CAP_PROP_FPS)
                orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                total_source_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                output_fps = round(fps) if fps > 0 else 30 # Ensure valid FPS
                if output_fps < 1: output_fps = 1
                print(f"   Source FPS: {fps:.2f}, Output FPS: {output_fps}, Total Frames: {total_source_frames}")

                # --- Loop Through Each Range Defined for this Video ---
                for range_data in ranges:
                    range_id = range_data["id"]
                    start_frame = range_data.get("start", 0)
                    end_frame = range_data.get("end", 0)
                    crop_tuple = range_data.get("crop") # Can be None
                    range_index = range_data.get("index", "X") # For filename
                    print(f"  Processing Range {range_index} [{start_frame}-{end_frame}], Crop: {crop_tuple is not None}")
                    
                    # Validate range frames against actual source length
                    if start_frame < 0 or start_frame >= total_source_frames:
                        print(f"    ⚠️ Skipping range: Start frame ({start_frame}) out of bounds (0-{total_source_frames-1}).")
                        continue
                    if end_frame <= start_frame:
                         print(f"    ⚠️ Skipping range: End frame ({end_frame}) must be greater than Start frame ({start_frame}).")
                         continue
                         
                    end_frame = min(end_frame, total_source_frames) # Clamp end frame to actual video length
                    if end_frame <= start_frame: # Double check after clamping
                         print(f"    ⚠️ Skipping range: End frame ({end_frame}) became <= Start frame ({start_frame}) after clamping.")
                         continue
                         
                    duration_frames = end_frame - start_frame
                    
                    # --- Generate Base Output Filename for this Range ---
                    prefix = getattr(self.main_app, 'export_prefix', '').strip()
                    if prefix:
                        self.file_counter += 1
                        # Incorporate range index into prefixed name
                        base_output_name = f"{prefix}_{self.file_counter:05d}_range{range_index}"
                    else:
                        # Use the display name from the list (which might include _copyX)
                        base_name_for_file, _ = os.path.splitext(base_display_name)
                        # Add range index to differentiate outputs from same list item (if it has multiple ranges)
                        base_output_name = f"{base_name_for_file}_range{range_index}"
                         
                    # Common variables for this range's export
                    ss = start_frame / fps if fps > 0 else 0 # Start time in seconds
                    t = duration_frames / fps if fps > 0 else 0 # Duration in seconds
                    image_paths_for_gemini = [] # Track images needing Gemini captioning for this range
                    video_path_for_gemini = None # Track video needing Gemini description for this range

                    # --- 1. Export Image (if requested) ---
                    if export_image_flag:
                        print(f"    Attempting image export for frame {start_frame}...")
                        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                        ret_img, frame = cap.read()
                        if ret_img and frame is not None:
                            # Export Cropped Image?
                            if export_cropped_flag and crop_tuple:
                                x, y, w, h = crop_tuple
                                if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > orig_w or y+h > orig_h:
                                    print(f"      ⚠️ Invalid crop region for image export in range {range_index}")
                                else:
                                    cropped_frame = frame[y:y+h, x:x+w]
                                    if cropped_frame.size > 0:
                                        img_name = f"{base_output_name}_cropped.png"
                                        img_path = os.path.join(output_folder_cropped, img_name)
                                        try:
                                            cv2.imwrite(img_path, cropped_frame)
                                            print(f"      🖼️ Exported Cropped Image: {os.path.basename(img_path)}")
                                            if generate_gemini_flag:
                                                image_paths_for_gemini.append(img_path)
                                            else:
                                                self.write_caption(img_path) # Write simple caption
                                        except Exception as e:
                                            print(f"      ❌ Error writing cropped image {img_path}: {e}")
                                    else: print(f"      ⚠️ Empty crop frame for image in range {range_index}")
                                    
                            # Export Uncropped Image?
                            if export_uncropped_flag:
                                img_name = f"{base_output_name}.png"
                                img_path = os.path.join(output_folder_uncropped, img_name)
                                try:
                                    cv2.imwrite(img_path, frame)
                                    print(f"      🖼️ Exported Uncropped Image: {os.path.basename(img_path)}")
                                    # Add for Gemini only if not already added (avoids duplicate captions if both exported)
                                    if generate_gemini_flag and img_path not in image_paths_for_gemini: 
                                        image_paths_for_gemini.append(img_path)
                                    elif not generate_gemini_flag:
                                        self.write_caption(img_path) # Write simple caption
                                except Exception as e:
                                    print(f"      ❌ Error writing uncropped image {img_path}: {e}")
                        else:
                            print(f"    ⚠️ Could not read frame {start_frame} for image export.")

                    # --- 2. Export Cropped Video (if requested) ---
                    exported_cropped_video = False
                    if export_cropped_flag and crop_tuple:
                        x, y, w, h = crop_tuple
                        # Basic validation for crop dimensions
                        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > orig_w or y + h > orig_h:
                            print(f"    ⚠️ Invalid crop dimensions {crop_tuple} for range {range_index}. Skipping cropped video export.")
                        else:
                            _, ext = os.path.splitext(original_path) # Use original extension
                            output_name = f"{base_output_name}_cropped{ext}"
                            output_path = os.path.join(output_folder_cropped, output_name)
                            print(f"    🎬 Exporting Cropped Video: {output_name}...")
                            try:
                                stream = ffmpeg.input(original_path, ss=ss, t=t)
                                stream = stream.filter('fps', fps=output_fps, round='up')
                                stream = stream.filter('crop', w, h, x, y)
                                # Optional scale filter (use self.main_app.longest_edge)
                                scale_filter_active = getattr(self.main_app, 'longest_edge', 1024) > 0 and self.main_app.resolution_input.text().strip() # Check if input has value
                                if scale_filter_active:
                                     print(f"      Applying scale filter, longest edge: {self.main_app.longest_edge}")
                                     # Ensure longest edge is even for compatibility?
                                     # longest_edge = self.main_app.longest_edge if self.main_app.longest_edge % 2 == 0 else self.main_app.longest_edge -1
                                     # if longest_edge <=0 : longest_edge = 2
                                     # stream = stream.filter('scale', longest_edge, -2) 
                                     stream = stream.filter('scale', self.main_app.longest_edge, -2) # Allow odd for now
                                     
                                stream = stream.output(output_path, r=output_fps, vsync='cfr', map_metadata='-1', **{'c:v': 'libx264', 'preset': 'medium', 'crf': 23}) # Added codec params
                                # Adding global_header flag might help some players
                                # stream = stream.global_args('-fflags', '+genpts') 
                                stream.run(overwrite_output=True, quiet=True)
                                
                                print(f"      ✅ Exported cropped: {os.path.basename(output_path)}")
                                video_path_for_gemini = output_path # Prioritize cropped for Gemini
                                exported_cropped_video = True
                                if not generate_gemini_flag:
                                    self.write_caption(output_path) # Write simple caption

                            except ffmpeg.Error as e:
                                print(f"    ❌ Error exporting cropped {output_name}: {e.stderr.decode('utf8', errors='ignore')}")
                            except Exception as e:
                                print(f"    ❌ Unexpected error exporting cropped {output_name}: {e}")

                    # --- 3. Export Uncropped Video (if requested) ---
                    if export_uncropped_flag:
                        _, ext = os.path.splitext(original_path)
                        output_name = f"{base_output_name}{ext}"
                        output_path = os.path.join(output_folder_uncropped, output_name)
                        print(f"    🎬 Exporting Uncropped Video: {output_name}...")
                        try:
                            stream = ffmpeg.input(original_path, ss=ss, t=t)
                            stream = stream.filter('fps', fps=output_fps, round='up')
                            # Optional scale filter
                            scale_filter_active = getattr(self.main_app, 'longest_edge', 1024) > 0 and self.main_app.resolution_input.text().strip()
                            if scale_filter_active:
                                 print(f"      Applying scale filter, longest edge: {self.main_app.longest_edge}")
                                 # stream = stream.filter('scale', longest_edge, -2) # Use adjusted even edge if needed
                                 stream = stream.filter('scale', self.main_app.longest_edge, -2)

                            stream = stream.output(output_path, r=output_fps, vsync='cfr', map_metadata='-1', **{'c:v': 'libx264', 'preset': 'medium', 'crf': 23})
                            # stream = stream.global_args('-fflags', '+genpts')
                            stream.run(overwrite_output=True, quiet=True)
                             
                            print(f"      ✅ Exported uncropped: {os.path.basename(output_path)}")
                            if video_path_for_gemini is None: # Use uncropped for Gemini only if cropped wasn't made
                                video_path_for_gemini = output_path
                            if not generate_gemini_flag:
                                self.write_caption(output_path) # Write simple caption
                                 
                        except ffmpeg.Error as e:
                            print(f"    ❌ Error exporting uncropped {output_name}: {e.stderr.decode('utf8', errors='ignore')}")
                        except Exception as e:
                            print(f"    ❌ Unexpected error exporting uncropped {output_name}: {e}")

                    # --- 4. Generate Gemini Descriptions/Captions (if requested for this range) ---
                    if generate_gemini_flag:
                        # --- Video Description ---
                        if video_path_for_gemini: # If a video (cropped or uncropped) was successfully exported
                            print(f"    🤖 Generating Gemini description for video: {os.path.basename(video_path_for_gemini)}...")
                            description = self.generate_gemini_video_description(video_path_for_gemini)
                            if description:
                                self.write_caption(video_path_for_gemini, caption_content=description)
                            else:
                                print(f"      ⚠️ Failed Gemini video description. Writing simple caption.")
                                self.write_caption(video_path_for_gemini) # Fallback to simple
                                
                        # --- Image Caption(s) ---
                        elif image_paths_for_gemini: # Only do image caption if NO video was suitable for Gemini
                            print(f"    🤖 Generating Gemini caption(s) for {len(image_paths_for_gemini)} image(s)...")
                            for img_path in image_paths_for_gemini:
                                caption = self.generate_gemini_caption(img_path)
                                if caption:
                                    self.write_caption(img_path, caption_content=caption)
                                else:
                                    print(f"      ⚠️ Failed Gemini image caption for {os.path.basename(img_path)}. Writing simple caption.")
                                    self.write_caption(img_path) # Fallback to simple
                                    
                    # --- End of processing for this range ---
                    print(f"  Finished Range {range_index}.")
                    
            except Exception as e:
                print(f"❌ UNEXPECTED ERROR processing source {base_display_name}: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # Release video capture object for the source file
                if cap and cap.isOpened():
                    cap.release()
                    print(f"   Released video source: {base_display_name}")
                     
        # --- End of Export Process --- 
        print(f"--- Export Process Finished ---")
        QMessageBox.information(self.main_app, "Export Complete", "Finished exporting selected video ranges.")