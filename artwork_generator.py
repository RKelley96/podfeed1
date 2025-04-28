import os
import openai
from openai import OpenAI
import logging
import tempfile
from PIL import Image
import requests
from io import BytesIO
import base64

class ArtworkGenerator:
    def __init__(self, openai_api_key):
        """Initialize the artwork generator with OpenAI API key."""
        self.client = openai.OpenAI(api_key=openai_api_key)

    def generate_artwork(self, title, topic, host1_name=None, host2_name=None, style="Realistic", mood="Professional", color_scheme="Vibrant", host1_photo_path=None, host2_photo_path=None, output_path="output/episode_artwork.png"):
        """
        Generate artwork for a podcast episode using DALL-E.
        
        Args:
            title (str): The episode title
            topic (str): The episode topic/content
            host1_name (str): Name of the first host
            host2_name (str): Name of the second host
            style (str): Art style (Realistic, Cartoon, Abstract, Minimalist, Vintage)
            mood (str): Mood of the artwork (Energetic, Serious, Playful, Mysterious, Professional)
            color_scheme (str): Color scheme (Vibrant, Pastel, Monochrome, Warm, Cool)
            host1_photo_path (str): Path to first host's photo
            host2_photo_path (str): Path to second host's photo
            output_path (str): Path to save the generated artwork
            
        Returns:
            str: Path to the generated artwork or error message
        """
        try:
            # Create a detailed prompt for DALL-E
            prompt = f"Create a professional podcast cover art for an episode titled '{title}' about {topic}. "
            
            # Add host information if available
            if host1_name and host2_name:
                prompt += f"The episode features hosts {host1_name} and {host2_name}. "
            
            # Add style description
            if style == "Realistic":
                prompt += "The artwork should be photorealistic and professional. "
            elif style == "Cartoon":
                prompt += "The artwork should be in a modern cartoon style, playful yet professional. "
            elif style == "Abstract":
                prompt += "The artwork should be abstract and artistic, using shapes and colors to represent the hosts. "
            elif style == "Minimalist":
                prompt += "The artwork should be minimalist and clean, using simple shapes and limited colors. "
            elif style == "Vintage":
                prompt += "The artwork should have a vintage, retro style with classic design elements. "
            
            # Add mood description
            prompt += f"The overall mood should be {mood.lower()}. "
            
            # Add color scheme
            prompt += f"Use a {color_scheme.lower()} color scheme. "
            
            # Add host photo references if available
            if host1_photo_path and os.path.exists(host1_photo_path):
                prompt += f"Reference the appearance of {host1_name} from their photo. "
            if host2_photo_path and os.path.exists(host2_photo_path):
                prompt += f"Reference the appearance of {host2_name} from their photo. "
            
            # Final requirements
            prompt += "The artwork should be suitable for a podcast cover, use a 1:1 aspect ratio, and be visually appealing. Do not include any text or logos in the image."
            
            # Generate the image
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            
            # Get the image URL
            image_url = response.data[0].url
            
            # Download and save the image
            response = requests.get(image_url)
            if response.status_code == 200:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                return output_path
            else:
                return f"Error: Failed to download image (status code: {response.status_code})"
                
        except openai.APIError as e:
            logging.error(f"OpenAI API error: {e}")
            return f"Error: OpenAI API error - {str(e)}"
        except openai.APIConnectionError as e:
            logging.error(f"OpenAI connection error: {e}")
            return f"Error: Failed to connect to OpenAI - {str(e)}"
        except openai.RateLimitError as e:
            logging.error(f"OpenAI rate limit error: {e}")
            return f"Error: Rate limit exceeded - {str(e)}"
        except Exception as e:
            logging.error(f"Unexpected error in artwork generation: {e}")
            return f"Error: Unexpected error - {str(e)}" 