import os
import logging
import requests
from pydub import AudioSegment
import tempfile

class SoundEffects:
    def __init__(self, api_key):
        self.api_key = api_key
        self.cache_dir = "cache/sfx"
        os.makedirs(self.cache_dir, exist_ok=True)
        self.sfx_mapping = {
            "door slam": "door slamming",
            "applause": "audience applause",
            "laugh": "audience laughter",
            "drum roll": "drum roll",
            "suspense": "suspenseful music",
            "fight": "fight scene sound effects",
            "exit": "door closing and footsteps",
            "mic drop": "mic drop sound effect"
        }

    def generate_sfx(self, prompt, output_path=None):
        """Generate a sound effect using ElevenLabs API."""
        try:
            # Check cache first
            cache_path = os.path.join(self.cache_dir, f"{prompt.replace(' ', '_')}.mp3")
            if os.path.exists(cache_path):
                logging.info(f"Using cached SFX for: {prompt}")
                return cache_path

            url = "https://api.elevenlabs.io/v1/sound-effects"
            headers = {"xi-api-key": self.api_key}
            payload = {"text": prompt}
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.ok:
                # Use provided output path or create a temporary one
                if not output_path:
                    output_path = cache_path
                
                with open(output_path, "wb") as f:
                    f.write(response.content)
                
                logging.info(f"Generated SFX for: {prompt}")
                return output_path
            else:
                logging.error(f"Failed to generate SFX: {response.text}")
                return None
                
        except Exception as e:
            logging.error(f"Error generating SFX: {str(e)}")
            return None

    def process_script_for_sfx(self, script):
        """Process script to find and extract sound effect cues."""
        sfx_cues = []
        lines = script.split('\n')
        
        for i, line in enumerate(lines):
            # Look for sound effect cues in brackets
            if '[' in line and ']' in line:
                start = line.find('[')
                end = line.find(']')
                if start < end:
                    cue = line[start+1:end].lower().strip()
                    # Check if it's a known sound effect
                    if cue in self.sfx_mapping:
                        sfx_cues.append({
                            'line': i,
                            'cue': cue,
                            'prompt': self.sfx_mapping[cue]
                        })
        
        return sfx_cues

    def insert_sfx_into_audio(self, main_audio_path, sfx_cues, output_path):
        """Insert sound effects into the main audio at specified positions."""
        try:
            # Load main audio
            main_audio = AudioSegment.from_file(main_audio_path)
            
            # Process each sound effect
            for cue in sfx_cues:
                # Generate the sound effect
                sfx_path = self.generate_sfx(cue['prompt'])
                if sfx_path:
                    sfx_audio = AudioSegment.from_file(sfx_path)
                    
                    # Calculate position (roughly based on line number)
                    # This is a simple approximation - you might want to adjust timing
                    position_ms = cue['line'] * 2000  # Assuming ~2 seconds per line
                    
                    # Insert the sound effect
                    main_audio = main_audio.overlay(sfx_audio, position=position_ms)
            
            # Export the final audio
            main_audio.export(output_path, format="mp3")
            return output_path
            
        except Exception as e:
            logging.error(f"Error inserting SFX: {str(e)}")
            return None 