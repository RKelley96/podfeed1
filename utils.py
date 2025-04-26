from dotenv import load_dotenv
import os
import requests
from bs4 import BeautifulSoup
import re
import io
import base64
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, BadRequestError # Import specific errors, including BadRequestError
import logging # Import logging

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- Clean the vision model name --- # NEW SECTION
raw_vision_model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o") # Use same env var
# 1. Split at the first '#'
model_name_no_comment = raw_vision_model_name.split('#', 1)[0]
# 2. Strip whitespace from the result
OPENAI_VISION_MODEL = model_name_no_comment.strip()
# Log the cleaned name
logging.info(f"Utils using cleaned vision model name: '{OPENAI_VISION_MODEL}'")
# --- End cleaning ---


def extract_text_from_url(url):
    """
    Fetches and extracts text content from a URL.
    Handles potential request errors more specifically.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15) # Increased timeout
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

        soup = BeautifulSoup(response.content, 'html.parser')

        # Remove script, style, nav, footer elements for cleaner extraction
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.extract()

        # Extract title
        title = soup.title.string if soup.title else "Article" # Use .string for cleaner title

        # Try to find main content area (common tags/attributes)
        main_content = soup.find('article') or soup.find('main') or soup.find(id='content') or soup.find(class_='content') or soup
        if main_content is None:
            main_content = soup # Fallback to whole soup if no specific content area found

        # Extract paragraphs from the main content area
        paragraphs = main_content.find_all('p')
        text = ' '.join([p.get_text(strip=True) for p in paragraphs]) # Use strip=True

        # Clean up text: remove multiple spaces/newlines
        text = re.sub(r'\s+', ' ', text).strip()

        # Limit to a reasonable length
        if len(text) > 3000:
            text = text[:3000] + "..."

        if not text:
            return f"Warning: Could not extract significant text content from URL: {url}"

        return f"Title: {title}\n\nContent: {text}"

    except requests.exceptions.Timeout:
        logging.error(f"Request timed out while fetching URL: {url}") # Log error
        return f"Error: Request timed out while fetching URL: {url}"
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error {e.response.status_code} while fetching URL: {url}", exc_info=True) # Log error
        return f"Error: HTTP error {e.response.status_code} while fetching URL: {url}"
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching URL content: {str(e)}", exc_info=True) # Log error
        return f"Error fetching URL content: {str(e)}"
    except Exception as e:
        # Catch-all for other potential errors (e.g., BeautifulSoup issues)
        logging.error(f"Error processing URL {url}: {str(e)}", exc_info=True) # Log error
        return f"Error processing URL {url}: {str(e)}"


def extract_text_from_image(image_file):
    """
    Sends an image to OpenAI's Vision API to extract and describe its content.
    Uses the cleaned model specified by OPENAI_MODEL_NAME env var. # MODIFIED
    Handles specific OpenAI API errors.
    """
    if not OPENAI_API_KEY:
        logging.error("OPENAI_API_KEY not configured for image extraction.") # Log error
        return "Error: OPENAI_API_KEY not configured."

    client = OpenAI(api_key=OPENAI_API_KEY)

    try:
        # Convert image to base64 string
        image_bytes = image_file.getvalue()
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        # Add explicit log to check the exact model string # NEW
        logging.info(f"--- extract_text_from_image using model: |{OPENAI_VISION_MODEL}| ---")

        response = client.chat.completions.create(
            model=OPENAI_VISION_MODEL, # Use cleaned model name
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image in detail, focusing on what would be relevant for a podcast discussion:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}" # Assuming jpeg, adjust if needed or detect type
                            }
                        }
                    ]
                }
            ],
            max_tokens=300
        )

        return response.choices[0].message.content

    except APIError as e:
        logging.error(f"OpenAI API returned an API Error during image extraction: {e}", exc_info=True) # Log error
        return f"Error: OpenAI API returned an API Error: {e}"
    except APIConnectionError as e:
        logging.error(f"Failed to connect to OpenAI API during image extraction: {e}", exc_info=True) # Log error
        return f"Error: Failed to connect to OpenAI API: {e}"
    except RateLimitError as e:
        logging.error(f"OpenAI API request exceeded rate limit during image extraction: {e}", exc_info=True) # Log error
        return f"Error: OpenAI API request exceeded rate limit: {e}"
    # Catch BadRequestError specifically # NEW
    except BadRequestError as e:
        logging.error(f"OpenAI API returned a BadRequestError (Code: {e.code}) during image extraction. Model sent: |{OPENAI_VISION_MODEL}|. Error: {e}", exc_info=True)
        return f"Error: OpenAI API returned a Bad Request (likely invalid input): {e}"
    except Exception as e:
        logging.error(f"Error processing image: {str(e)}", exc_info=True) # Log error
        return f"Error processing image: {str(e)}"

def format_script(script_text, host1_name="Joe Rogan", host2_name="Alex Cooper"):
    """
    Formats the raw script text for better display using CSS classes.
    Supports dynamic host names.

    Parameters:
    ----------
    script_text : str
        Raw script text
    host1_name : str
        Name of the first host
    host2_name : str
        Name of the second host

    Returns:
    -------
    str
        Formatted HTML script with CSS classes for styling.
    """
    # Remove any ending markers more robustly
    script_text = re.sub(r'\[End of Episode\]|\[End of Podcast\]|\*End of Episode\*|\*End of Podcast\*', '', script_text, flags=re.IGNORECASE).strip()

    lines = script_text.split("\n")
    formatted_lines = []

    # Escape special characters for regex pattern matching
    host1_pattern = re.escape(host1_name)
    host2_pattern = re.escape(host2_name)

    # --- Dynamic Speaker Class Assignment --- # NEW
    # Assign classes dynamically based on first appearance
    speaker_map = {}
    speaker_class_counter = 1
    # --- End Dynamic Speaker Class ---

    for line in lines:
        line_strip = line.strip()

        # Skip empty lines or lines that just contain dashes
        if not line_strip or line_strip == "---" or line_strip == "--":
            if not line_strip: # Add space for empty lines
                 formatted_lines.append('<div class="script-empty-line"></div>')
            continue

        # Skip any line that contains ending indicators (already done above, but as safeguard)
        if any(ending in line.lower() for ending in ["end of episode", "end of podcast"]):
            continue

        # Use regex to match dynamic host names at the beginning of the line
        match1 = re.match(rf"^({host1_pattern})\s*:", line_strip, re.IGNORECASE)
        match2 = re.match(rf"^({host2_pattern})\s*:", line_strip, re.IGNORECASE)

        speaker_name = None
        dialogue = None
        speaker_class = None

        if match1:
            speaker_name = match1.group(1) # Get the actual matched name (preserves case if needed)
            dialogue = line_strip[match1.end():].strip() # Get text after the colon
        elif match2:
            speaker_name = match2.group(1)
            dialogue = line_strip[match2.end():].strip()

        if speaker_name and dialogue is not None:
            # Assign CSS class dynamically based on speaker name
            if speaker_name not in speaker_map:
                if speaker_class_counter <= 2: # Limit to 2 distinct speaker classes
                    speaker_map[speaker_name] = f"speaker-{speaker_class_counter}"
                    speaker_class_counter += 1
                else:
                    speaker_map[speaker_name] = "speaker-other" # Fallback class if more than 2 speakers

            speaker_class = speaker_map.get(speaker_name, "speaker-other") # Get assigned class

            # Use CSS classes instead of hardcoded speaker names in class attribute
            formatted_line = f'<div class="dialogue-line"><strong class="{speaker_class}">{speaker_name}:</strong><span class="dialogue-text">{dialogue}</span></div>'

        else:
            # Handle other lines (e.g., intro, scene descriptions)
            formatted_line = f'<div class="script-other-line">{line_strip}</div>'

        formatted_lines.append(formatted_line)

    # Join the formatted lines and wrap in the main container div
    return f'<div class="podcast-script-container">{"".join(formatted_lines)}</div>'

