import os
import requests
import json
import time
import logging # Use logging instead of print for internal messages
import re
import tempfile # Import tempfile
# Import pydub - ensure it's installed: pip install pydub
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    logging.error("pydub library not found. Please install it: pip install pydub")
    PYDUB_AVAILABLE = False
from sound_effects import SoundEffects


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def clean_env_var(env_var_value):
    """Helper function to clean environment variable values."""
    if not env_var_value:
        return ""
    # 1. Split at the first '#' to remove comments
    value_no_comment = env_var_value.split('#', 1)[0]
    # 2. Strip leading/trailing whitespace
    cleaned_value = value_no_comment.strip()
    # 3. Strip potential quotes AFTER stripping whitespace # MODIFIED
    cleaned_value = cleaned_value.strip('"\'')
    return cleaned_value

class VoiceSynthesizer:
    """
    A class for synthesizing voices using ElevenLabs API directly via HTTP requests.
    Reads configuration (API Key, Voice IDs, Model, Settings) from environment variables.
    """
    def __init__(self, elevenlabs_api_key):
        """
        Initializes the VoiceSynthesizer with the ElevenLabs API key
        and reads configuration from environment variables, cleaning the values.
        """
        if not elevenlabs_api_key:
            raise ValueError("ElevenLabs API key is required")

        # Clean API key just in case
        self.api_key = clean_env_var(elevenlabs_api_key) # Use cleaned key
        self.base_url = "https://api.elevenlabs.io/v1"
        self.headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key # Use cleaned key
        }

        # --- Get configuration from environment variables and CLEAN them ---
        # Default voices - now used more flexibly for any host
        self.default_voice_1 = clean_env_var(os.getenv("ELEVENLABS_HOST1_VOICE_ID", "NQS8M290ViUV7Mdca3qT")) # Default: Adam
        self.default_voice_2 = clean_env_var(os.getenv("ELEVENLABS_HOST2_VOICE_ID", "E1eTKENSf2k6nMCQpG8n")) # Default: Rachel

        # Keep legacy voice IDs for backward compatibility, also clean them
        self.joe_rogan_voice_id = clean_env_var(os.getenv("ELEVENLABS_JOE_VOICE_ID", self.default_voice_1))
        self.alex_cooper_voice_id = clean_env_var(os.getenv("ELEVENLABS_ALEX_VOICE_ID", self.default_voice_2))

        self.model_id = clean_env_var(os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2"))

        # Voice settings with defaults - clean boolean specifically
        try:
            self.stability = float(clean_env_var(os.getenv("ELEVENLABS_STABILITY", "0.4")))
            self.similarity_boost = float(clean_env_var(os.getenv("ELEVENLABS_SIMILARITY", "0.8")))
            self.style = float(clean_env_var(os.getenv("ELEVENLABS_STYLE", "0.15")))
            # Handle boolean conversion carefully after cleaning
            use_speaker_boost_str = clean_env_var(os.getenv("ELEVENLABS_USE_SPEAKER_BOOST", "True")).lower()
            self.use_speaker_boost = use_speaker_boost_str == 'true'
        except ValueError:
             logging.warning("Invalid format for ElevenLabs voice settings in .env. Using defaults.")
             self.stability = 0.4
             self.similarity_boost = 0.8
             self.style = 0.15
             self.use_speaker_boost = True

        self.voice_settings = {
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
            "style": self.style,
            "use_speaker_boost": self.use_speaker_boost
        }
        # -----------------------------------------------------

        # Create output directory if it doesn't exist
        os.makedirs('output', exist_ok=True)

        # Log cleaned values
        logging.info(f"Initialized VoiceSynthesizer.")
        logging.info(f"  Default Voice 1: '{self.default_voice_1}'")
        logging.info(f"  Default Voice 2: '{self.default_voice_2}'")
        logging.info(f"  Joe Rogan Voice: '{self.joe_rogan_voice_id}'")
        logging.info(f"  Alex Cooper Voice: '{self.alex_cooper_voice_id}'")
        logging.info(f"  Model ID: '{self.model_id}'")
        logging.info(f"  Voice Settings: {self.voice_settings}")

        self.sound_effects = SoundEffects(elevenlabs_api_key)

    def get_available_voices(self):
        """
        Gets a list of available voices from the ElevenLabs API.
        Returns a list of (voice_id, name) tuples or an empty list on error.
        """
        url = f"{self.base_url}/voices"
        # Use temporary headers without content-type for this GET request
        get_headers = {
            "Accept": "application/json",
            "xi-api-key": self.api_key
        }

        try:
            response = requests.get(url, headers=get_headers, timeout=10)
            response.raise_for_status() # Raise exception for bad status codes

            voices_data = response.json().get("voices", [])
            voices = [(voice["voice_id"], voice["name"]) for voice in voices_data]
            logging.info(f"Successfully retrieved {len(voices)} voices.")
            return voices

        except requests.exceptions.RequestException as e:
            logging.error(f"Error getting voices (request failed): {str(e)}")
            return []
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON response from /voices: {e}. Response text: {response.text}")
            return []
        except Exception as e:
            logging.error(f"Unexpected error getting voices: {str(e)}", exc_info=True)
            return []

    def extract_dialogue(self, script, host1_name="Joe Rogan", host2_name="Alex Cooper"):
        """
        Extracts dialogue lines for each speaker from the script.
        More robust parsing to handle potential variations with dynamic host names.

        Parameters:
        ----------
        script : str
            The script to extract dialogue from
        host1_name : str
            Name of the first host
        host2_name : str
            Name of the second host

        Returns:
        -------
        list
            Ordered list of tuples: [('host1', 'dialogue text'), ('host2', 'dialogue text'), ...]
        """
        dialogue_turns = []
        lines = script.split("\n")
        current_speaker = None
        current_line = ""

        # Escape special characters for regex pattern matching
        host1_pattern = re.escape(host1_name)
        host2_pattern = re.escape(host2_name)

        for line in lines:
            line_strip = line.strip()
            if not line_strip: # Skip empty lines
                continue

            # Match with regex to be more flexible with formats (ensure match is at the start ^)
            is_host1 = re.match(rf"^\s*{host1_pattern}\s*:", line_strip, re.IGNORECASE)
            is_host2 = re.match(rf"^\s*{host2_pattern}\s*:", line_strip, re.IGNORECASE)

            if is_host1 or is_host2:
                # If we were accumulating text for a previous speaker, save it
                if current_speaker and current_line:
                    dialogue_turns.append((current_speaker, current_line.strip()))

                # Start new speaker
                if is_host1:
                    current_speaker = "host1"
                    # Get text after the matched pattern (including colon)
                    current_line = line_strip[is_host1.end():].strip()
                else: # is_host2
                    current_speaker = "host2"
                    # Get text after the matched pattern (including colon)
                    current_line = line_strip[is_host2.end():].strip()

            elif current_speaker and line_strip: # Continue accumulating lines for the current speaker
                # Only append if it's not another speaker line starting
                if not re.match(rf"^\s*({host1_pattern}|{host2_pattern})\s*:", line_strip, re.IGNORECASE):
                    current_line += " " + line_strip

        # Add the last accumulated line if it exists
        if current_speaker and current_line:
            dialogue_turns.append((current_speaker, current_line.strip()))

        logging.info(f"Extracted {len(dialogue_turns)} dialogue turns.")
        return dialogue_turns

    def text_to_speech(self, text, voice_id, output_path):
        """
        Converts text to speech using the ElevenLabs API.
        Returns the output_path on success, or an error message string on failure.
        """
        # Basic check for empty text
        if not text or not text.strip():
             logging.warning("Skipping empty text for TTS.")
             return "Skipped: Empty text provided." # Indicate skipped, not error

        # --- Clean the passed voice_id AGAIN just before use --- # NEW
        cleaned_voice_id = clean_env_var(voice_id)

        # Check if cleaned_voice_id is valid before making API call
        if not cleaned_voice_id or not isinstance(cleaned_voice_id, str) or len(cleaned_voice_id) < 5: # Basic sanity check
             error_message = f"Error: Invalid voice_id provided for TTS after cleaning: '{cleaned_voice_id}' (Original: '{voice_id}')"
             logging.error(error_message)
             return error_message

        url = f"{self.base_url}/text-to-speech/{cleaned_voice_id}" # Use cleaned_voice_id

        data = {
            "text": text,
            "model_id": self.model_id, # Assumes model_id was cleaned in __init__
            "voice_settings": self.voice_settings
        }

        # Add explicit log before API call
        logging.info(f"--- text_to_speech sending request ---")
        logging.info(f"  URL: {url}")
        logging.info(f"  Voice ID Used: |{cleaned_voice_id}|") # Log cleaned ID with pipes
        logging.info(f"  Model ID: |{self.model_id}|") # Log with pipes
        logging.info(f"  Text Sample: '{text[:60]}...'")

        try:
            response = requests.post(url, json=data, headers=self.headers, timeout=90) # Increased timeout for synthesis

            if response.status_code == 200:
                content_length = len(response.content)
                logging.info(f"TTS request successful, content length: {content_length} bytes")

                if content_length > 0:
                    # Save the audio content to a file
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    logging.info(f"Saved audio to {output_path}")
                    # Check file size again after writing
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        return output_path
                    else:
                        error_message = f"Error: Audio file empty or not saved correctly at {output_path}"
                        logging.error(error_message)
                        # Attempt to remove empty file
                        try:
                            if os.path.exists(output_path): os.remove(output_path)
                        except OSError: pass
                        return error_message
                else:
                    # API returned 200 OK but with empty content
                    error_message = f"Error: ElevenLabs API returned status 200 but with empty audio content for voice '{cleaned_voice_id}'."
                    logging.error(error_message)
                    # Try to get more info from headers if available
                    if 'application/json' in response.headers.get('Content-Type', ''):
                         try:
                              error_detail = response.json()
                              logging.error(f"API JSON response: {error_detail}")
                              error_message += f" Details: {error_detail.get('detail', {}).get('message', 'Unknown')}"
                         except json.JSONDecodeError:
                              pass # Ignore if response is not valid JSON
                    return error_message
            else:
                # Handle non-200 status codes
                error_message = f"Error: ElevenLabs API returned status code {response.status_code} for voice '{cleaned_voice_id}'."
                try:
                    # Try to parse JSON error detail
                    error_detail = response.json()
                    message = error_detail.get("detail", {}).get("message", response.text)
                    error_message += f" Message: {message}"
                except json.JSONDecodeError:
                    # Fallback to raw text if not JSON
                    error_message += f" Response: {response.text}"
                logging.error(error_message)
                return error_message
        except requests.exceptions.Timeout:
             error_message = f"Error: Timeout during ElevenLabs API request for voice '{cleaned_voice_id}'."
             logging.error(error_message)
             return error_message
        except requests.exceptions.RequestException as e:
            error_message = f"Error: Network error during ElevenLabs API request for voice '{cleaned_voice_id}': {str(e)}"
            logging.error(error_message, exc_info=True)
            return error_message
        except Exception as e:
            error_message = f"Error during text_to_speech call for voice '{cleaned_voice_id}': {str(e)}"
            logging.exception(error_message) # Log full traceback for unexpected errors
            return error_message

    def concatenate_audio_pydub(self, segment_files, output_path):
        """Concatenates audio files using pydub."""
        if not PYDUB_AVAILABLE:
            return "Error: pydub library is not available. Cannot concatenate audio."
        if not segment_files:
            return "Error: No audio segments provided for concatenation."

        try:
            combined = AudioSegment.empty()
            # Add a small silence buffer between segments
            silence = AudioSegment.silent(duration=250) # 250ms silence

            for i, file in enumerate(segment_files):
                if os.path.exists(file) and os.path.getsize(file) > 0:
                    try:
                        segment = AudioSegment.from_mp3(file)
                        combined += segment
                        if i < len(segment_files) - 1: # Don't add silence after the last segment
                            combined += silence
                    except Exception as e:
                         logging.error(f"Error loading or processing segment {file} with pydub: {e}")
                         # Optionally skip the problematic segment or return an error
                         # return f"Error processing audio segment {file}: {e}"
                         continue # Skip problematic segment
                else:
                    logging.warning(f"Skipping invalid or missing segment file: {file}")

            if len(combined) == 0:
                return "Error: Concatenation resulted in an empty audio file (all segments might have failed)."

            # Export the combined audio
            combined.export(output_path, format="mp3")
            logging.info(f"Successfully concatenated {len(segment_files)} segments to {output_path}")
            return output_path
        except Exception as e:
            error_message = f"Error during audio concatenation with pydub: {str(e)}"
            logging.exception(error_message)
            return error_message

    def generate_audio(self, script, host1_name="Joe Rogan", host2_name="Alex Cooper", output_path="output/podcast.mp3", voice1_id=None, voice2_id=None):
        """Generate audio from the podcast script with sound effects."""
        try:
            # First generate the main audio
            main_audio_path = self._generate_main_audio(script, host1_name, host2_name, output_path, voice1_id, voice2_id)
            if not main_audio_path:
                return None

            # Process script for sound effects
            sfx_cues = self.sound_effects.process_script_for_sfx(script)
            
            if sfx_cues:
                logging.info(f"Found {len(sfx_cues)} sound effects to add")
                # Insert sound effects into the main audio
                final_audio_path = self.sound_effects.insert_sfx_into_audio(
                    main_audio_path,
                    sfx_cues,
                    output_path
                )
                if final_audio_path:
                    return final_audio_path
            
            # If no sound effects or insertion failed, return the main audio
            return main_audio_path

        except Exception as e:
            logging.error(f"Error in generate_audio: {str(e)}")
            return None

    def _generate_main_audio(self, script, host1_name, host2_name, output_path="output/podcast.mp3", voice1_id=None, voice2_id=None):
        """Generate the main podcast audio without sound effects."""
        try:
            logging.info("Starting audio generation...")
            logging.info(f"Script length: {len(script)} characters")
            logging.info(f"Hosts: {host1_name} and {host2_name}")

            # Set voice IDs with prioritization: parameter > legacy-specific > default
            final_voice1_id = voice1_id if voice1_id else (self.joe_rogan_voice_id if host1_name.lower() == "joe rogan" else self.default_voice_1)
            final_voice2_id = voice2_id if voice2_id else (self.alex_cooper_voice_id if host2_name.lower() == "alex cooper" else self.default_voice_2)

            logging.info(f"Using Voice ID for {host1_name}: '{final_voice1_id}'")
            logging.info(f"Using Voice ID for {host2_name}: '{final_voice2_id}'")

            # Extract dialogue turns in order with dynamic host names
            dialogue_turns = self.extract_dialogue(script, host1_name, host2_name)
            if not dialogue_turns:
                logging.warning("No dialogue turns extracted from the script.")
                return None

            segment_files = []
            errors = []
            temp_dir = tempfile.mkdtemp() # Create a temporary directory for segments
            logging.info(f"Using temporary directory for audio segments: {temp_dir}")

            # Process each turn
            for i, (speaker, text) in enumerate(dialogue_turns):
                if not text.strip(): # Skip empty text turns
                    continue

                # Map speaker to voice ID
                voice_id_to_use = final_voice1_id if speaker == "host1" else final_voice2_id
                # Define path for the temporary segment file
                segment_file_path = os.path.join(temp_dir, f"segment_{i+1}.mp3")

                speaker_name = host1_name if speaker == "host1" else host2_name
                logging.info(f"Synthesizing turn {i+1}/{len(dialogue_turns)} (Speaker: {speaker_name}, Voice: '{voice_id_to_use}')") # Log the ID being passed
                # Call text_to_speech, which will internally clean the ID again
                result = self.text_to_speech(text, voice_id_to_use, segment_file_path)

                if isinstance(result, str) and (result.startswith("Error:") or result.startswith("Skipped:")):
                    errors.append(f"Turn {i+1} ({speaker_name}, Voice: {voice_id_to_use}): {result}")
                    # Clean up the specific temp file if synthesis failed
                    if os.path.exists(segment_file_path):
                        try: os.remove(segment_file_path)
                        except OSError: pass
                    # Stop on first error
                    logging.error(f"Stopping audio generation due to error in turn {i+1}.")
                    # Clean up the temporary directory and any previously generated segments
                    for f in segment_files: # segment_files list might be empty if first turn failed
                        try: os.remove(f)
                        except OSError: pass
                    try: os.rmdir(temp_dir) # Remove temp dir if empty
                    except OSError: pass
                    return None
                elif os.path.exists(segment_file_path) and os.path.getsize(segment_file_path) > 0:
                    segment_files.append(segment_file_path)
                else:
                    # Handle unexpected case where TTS didn't return error but file is bad
                    error_msg = f"Turn {i+1} ({speaker_name}, Voice: {voice_id_to_use}): TTS succeeded but output file is invalid or empty."
                    errors.append(error_msg)
                    if os.path.exists(segment_file_path):
                        try: os.remove(segment_file_path)
                        except OSError: pass
                    # Decide whether to stop or continue
                    logging.error(f"Stopping audio generation due to invalid file for turn {i+1}.")
                    # Clean up
                    for f in segment_files:
                        try: os.remove(f)
                        except OSError: pass
                    try: os.rmdir(temp_dir)
                    except OSError: pass
                    return None

                # Add a small delay between API calls if needed (less critical for paid tiers)
                # time.sleep(0.1) # Short delay

            if not segment_files:
                 logging.error("No audio segments were successfully generated.")
                 # Report accumulated errors if any
                 error_summary = ". ".join(errors) if errors else "Unknown reason."
                 try: os.rmdir(temp_dir) # Clean up temp dir
                 except OSError: pass
                 return None

            if errors:
                 logging.warning(f"Generated audio with {len(errors)} skipped/failed turns.")
                 # Optionally inform user about partial generation

            # Concatenate using pydub
            logging.info(f"Concatenating {len(segment_files)} audio segments...")
            concatenation_result = self.concatenate_audio_pydub(segment_files, output_path)

            # Clean up temporary directory and individual segment files
            logging.info(f"Cleaning up temporary directory: {temp_dir}")
            for file in segment_files: # Use the list of successfully created files
                try:
                    if os.path.exists(file):
                        os.remove(file)
                except OSError as e:
                     logging.warning(f"Could not remove temporary segment file {file}: {e}")
            try:
                os.rmdir(temp_dir) # Remove the temporary directory
            except OSError as e:
                logging.warning(f"Could not remove temporary directory {temp_dir}: {e}")


            logging.info("Audio generation process completed.")
            return concatenation_result # Return path or error message from concatenation

        except Exception as e:
            error_message = f"Unexpected error during generate_audio: {str(e)}"
            logging.exception(error_message) # Log traceback
            # Clean up any leftover temp files/dir if possible
            if 'segment_files' in locals():
                 for file in segment_files:
                      if os.path.exists(file):
                          try: os.remove(file)
                          except OSError: pass
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                 try: os.rmdir(temp_dir)
                 except OSError: pass
            return None
