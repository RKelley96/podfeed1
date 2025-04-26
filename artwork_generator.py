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
    def __init__(self, openai_api_key=None):
        """
        Initializes the ArtworkGenerator class with the provided OpenAI API key.
        """
        if not openai_api_key:
            raise ValueError("OpenAI API key is required")

        self.client = OpenAI(api_key=openai_api_key)
        logging.info("ArtworkGenerator initialized successfully")

    def _encode_image(self, image_file):
        """Helper function to encode an image file to base64."""
        if not image_file:
            return None
        try:
            image_bytes = image_file.getvalue()
            return base64.b64encode(image_bytes).decode('utf-8')
        except Exception as e:
            logging.error(f"Error encoding image: {e}")
            return None

    def generate_artwork(self, title, topic, output_path="output/episode_artwork.png", host1_photo=None, host2_photo=None):
        """
        Generates artwork for a podcast episode using DALL-E.
        
        Parameters:
        ----------
        title : str
            The episode title
        topic : str
            The episode topic
        output_path : str
            Path to save the generated artwork
        host1_photo : UploadedFile
            Photo of the first host
        host2_photo : UploadedFile
            Photo of the second host
            
        Returns:
        -------
        str
            Path to the generated artwork file, or an error message string
        """
        try:
            # Create a descriptive prompt for the artwork
            prompt = f"Create a podcast cover art for an episode titled '{title}' about {topic}. "
            
            # Add host photo references to the prompt if available
            if host1_photo or host2_photo:
                prompt += "The artwork should incorporate the visual style and appearance of the hosts. "
                if host1_photo:
                    prompt += "Use the first host's photo as a reference for their appearance. "
                if host2_photo:
                    prompt += "Use the second host's photo as a reference for their appearance. "
            
            prompt += "The artwork should be professional, modern, and eye-catching. " \
                    "Use a 1:1 aspect ratio. " \
                    "Include elements that represent the topic while maintaining a clean, podcast-appropriate design. " \
                    "Avoid text or logos in the image itself."

            logging.info(f"Generating artwork with prompt: {prompt}")

            # Prepare the image generation request
            request_data = {
                "model": "dall-e-3",
                "prompt": prompt,
                "size": "1024x1024",
                "quality": "standard",
                "n": 1,
            }

            # If host photos are provided, add them as reference images
            if host1_photo or host2_photo:
                request_data["reference_images"] = []
                if host1_photo:
                    encoded_photo1 = self._encode_image(host1_photo)
                    if encoded_photo1:
                        request_data["reference_images"].append(encoded_photo1)
                if host2_photo:
                    encoded_photo2 = self._encode_image(host2_photo)
                    if encoded_photo2:
                        request_data["reference_images"].append(encoded_photo2)

            # Generate the image using DALL-E
            response = self.client.images.generate(**request_data)

            # Get the image URL from the response
            image_url = response.data[0].url

            # Download the image
            response = requests.get(image_url)
            if response.status_code != 200:
                return f"Error: Failed to download image from URL. Status code: {response.status_code}"

            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Save the image
            with open(output_path, 'wb') as f:
                f.write(response.content)

            logging.info(f"Artwork generated successfully and saved to {output_path}")
            return output_path

        except openai.APIError as e:
            logging.error(f"OpenAI API returned an API Error: {e}", exc_info=True)
            return f"Error: OpenAI API returned an API Error: {e}"
        except openai.APIConnectionError as e:
            logging.error(f"Failed to connect to OpenAI API: {e}", exc_info=True)
            return f"Error: Failed to connect to OpenAI API: {e}"
        except openai.RateLimitError as e:
            logging.error(f"OpenAI API request exceeded rate limit: {e}", exc_info=True)
            return f"Error: OpenAI API request exceeded rate limit: {e}"
        except Exception as e:
            logging.error(f"Error generating artwork: {e}", exc_info=True)
            return f"Error generating artwork: {str(e)}" 