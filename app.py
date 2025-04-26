import streamlit as st
import os
import re
import random # Import random for the leaving chance
from genai import GenAI
from voice import VoiceSynthesizer
from utils import extract_text_from_url, extract_text_from_image, format_script
from personality_analyzer import PersonalityAnalyzer
from artwork_generator import ArtworkGenerator
from dotenv import load_dotenv
import logging
import tempfile
from datetime import datetime
from rss_manager import RssFeedManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration Loading ---
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Get OpenAI model name and clean it
raw_model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
OPENAI_MODEL_NAME = raw_model_name.strip('"\'')  # Remove any quotes
logging.info(f"Using OpenAI model: {OPENAI_MODEL_NAME}")

# --- Helper Functions ---

def load_css(file_name):
    """Loads CSS from a file and injects it into the Streamlit app."""
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
        logging.info(f"Successfully loaded CSS from {file_name}")
    except FileNotFoundError:
        logging.error(f"CSS file not found: {file_name}")
        st.error(f"Error: Stylesheet '{file_name}' not found. Styling may be incorrect.")

def extract_title(script):
    """
    Extracts the episode title from the script using regex for flexibility.
    Handles multiple title formats and provides a more descriptive default.
    """
    # Try multiple title patterns
    title_patterns = [
        r"EPISODE TITLE:\s*(.*)",  # Standard format
        r"TITLE:\s*(.*)",          # Alternative format
        r"PODCAST TITLE:\s*(.*)",  # Another alternative
        r"^#\s*(.*)",             # Markdown-style title
        r"^##\s*(.*)",            # Markdown-style subtitle
        r"^Title:\s*(.*)",        # Case-insensitive with colon
        r"^Episode:\s*(.*)"       # Episode prefix
    ]

    for pattern in title_patterns:
        match = re.match(pattern, script, re.IGNORECASE | re.MULTILINE)
        if match:
            title = match.group(1).strip()
            # Clean up the title
            title = re.sub(r'\s*--*$', '', title)  # Remove trailing dashes
            title = re.sub(r'^["\']|["\']$', '', title)  # Remove surrounding quotes
            title = title.strip()
            if title:  # Only return if we found a non-empty title
                return title

    # If no title found, generate a descriptive default
    logging.warning("Could not find a title in the script. Using generated default.")
    return "Dynamic Podcast Episode - " + datetime.now().strftime("%B %d, %Y")

def get_safe_filename(title):
    """Creates a safe filename from a title string."""
    # Remove or replace invalid characters
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
    safe_title = safe_title.replace(" ", "_")
    # Limit length if necessary
    return safe_title[:100] # Limit filename length

def handle_text_input():
    """Handles text input type."""
    content = st.text_area("Enter a topic:",
                           placeholder="e.g., Climate change, cryptocurrency, or fitness routines",
                           height=100,
                           key="text_input_area")
    return content, "text"

def handle_url_input():
    """Handles URL input type."""
    url_input = st.text_input("Enter article URL:",
                            placeholder="https://example.com/article",
                            key="url_input_field")
    content = ""
    if url_input:
        with st.spinner("Extracting content from URL..."):
            content = extract_text_from_url(url_input)
            if content.startswith("Error:") or content.startswith("Warning:"):
                st.error(content)
                content = "" # Reset content on error
            elif content:
                 st.success("Content extracted successfully!")
            else:
                 st.warning("Could not extract content from URL.")

    return content, "url"

def handle_image_input():
    """Handles image input type."""
    uploaded_image = st.file_uploader("Upload an image:",
                                    type=["jpg", "jpeg", "png"],
                                    key="image_uploader")
    content = ""
    if uploaded_image:
        col1, col2 = st.columns([1, 2]) # Keep image display
        with col1:
            st.image(uploaded_image, caption="Uploaded Image", use_column_width=True)
        with st.spinner("Analyzing image..."):
            content = extract_text_from_image(uploaded_image)
            if content.startswith("Error:"):
                st.error(content)
                content = "" # Reset content on error
            elif content:
                st.success("Image analyzed successfully!")
            else:
                st.warning("Could not get description from image.")

    return content, "image"

def handle_personality_input(host_number):
    """Handles personality input for a host, now with URL option."""
    host_name = st.text_input(
        f"Host {host_number} Name:",
        placeholder=f"Enter name for Host {host_number}",
        key=f"host{host_number}_name"
    )

    input_method = st.radio(
        f"Host {host_number} Personality Input Method:",
        ["Text Input", "File Upload", "URL"],
        key=f"host{host_number}_input_method"
    )

    personality_text = ""
    if input_method == "Text Input":
        personality_text = st.text_area(
            f"Enter text sample for {host_name or f'Host {host_number}'}:",
            placeholder="Paste interviews, articles, transcripts, or other text that represents this personality's style and interests.",
            height=150,
            key=f"host{host_number}_text_input"
        )
    elif input_method == "File Upload":
        uploaded_file = st.file_uploader(
            f"Upload text file for {host_name or f'Host {host_number}'}:",
            type=["txt", "md", "doc", "docx", "pdf"],
            key=f"host{host_number}_file_upload"
        )
        if uploaded_file:
            try:
                personality_text = uploaded_file.getvalue().decode("utf-8")
                st.success(f"File for {host_name or f'Host {host_number}'} uploaded successfully!")
            except Exception as e:
                st.error(f"Error reading file: {e}")
                personality_text = ""
    elif input_method == "URL":
        url = st.text_input(
            f"Enter a URL for {host_name or f'Host {host_number}'}'s personality:",
            placeholder="https://example.com/interview-or-profile",
            key=f"host{host_number}_url_input"
        )
        if url:
            with st.spinner("Extracting content from URL..."):
                content = extract_text_from_url(url)
                if content.startswith("Error:") or content.startswith("Warning:"):
                    st.error(content)
                    personality_text = ""
                else:
                    st.success("Content extracted successfully!")
                    personality_text = content

    # Add photo upload option after text input
    use_photo = st.checkbox(
        "Upload photo for custom art?",
        key=f"use_photo_{host_number}"
    )
    
    host_photo = None
    if use_photo:
        host_photo = st.file_uploader(
            f"Upload photo for {host_name or f'Host {host_number}'}:",
            type=["jpg", "jpeg", "png"],
            key=f"host{host_number}_photo"
        )

    return host_name, personality_text, host_photo

def display_podcast_output(title, display_script, host1_name, host2_name, audio_path=None, artwork_path=None):
    """Displays the generated podcast title, script, audio player, and download buttons."""
    st.subheader("EPISODE TITLE")
    # Display title using the CSS class
    st.markdown(f'<div class="episode-title"><h2>{title}</h2></div>', unsafe_allow_html=True)

    # Generate and display episode description
    description = f"{host1_name} and {host2_name} tackle {title.lower()}. {host1_name} brings his signature mix of curiosity and skepticism, while {host2_name} offers her unfiltered take on the subject. Expect unexpected insights, heated debates, and plenty of laughs."
    
    st.markdown("### EPISODE DESCRIPTION")
    st.markdown(f'<div class="episode-description">{description}</div>', unsafe_allow_html=True)

    # Display script using the formatting function and CSS classes
    st.subheader("PODCAST SCRIPT")
    formatted_script_html = format_script(display_script, host1_name, host2_name)
    st.markdown(formatted_script_html, unsafe_allow_html=True)

    # Script Download Button
    st.markdown("### SCRIPT OPTIONS")
    safe_title = get_safe_filename(title)
    script_bytes = display_script.encode('utf-8')
    st.download_button(
        label="DOWNLOAD SCRIPT",
        data=script_bytes,
        file_name=f"{safe_title}_script.txt",
        mime="text/plain",
        key="download_script_button"
    )

    # Audio Section
    if audio_path is not None and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
        st.subheader("PODCAST AUDIO")
        try:
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            if audio_bytes:
                 st.audio(audio_bytes, format="audio/mp3")
                 st.download_button(
                    label="DOWNLOAD PODCAST MP3",
                    data=audio_bytes,
                    file_name=f"{safe_title}_podcast.mp3",
                    mime="audio/mpeg",
                    key="download_audio_button"
                 )
            else:
                 st.error(f"Audio file appears to be empty: {audio_path}")

        except Exception as e:
            logging.error(f"Error reading or displaying audio file {audio_path}: {e}")
            st.error("Error loading audio file.")
    elif audio_path is None and ELEVENLABS_API_KEY:
        st.info("Audio generation was attempted but did not produce a file. Check logs or error messages above.")

    # Display artwork at the end and smaller
    if artwork_path and os.path.exists(artwork_path):
        st.subheader("EPISODE ARTWORK")
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.image(artwork_path, width=300)  # Fixed width for smaller display
            # Add download button for artwork
            with open(artwork_path, "rb") as f:
                artwork_bytes = f.read()
            st.download_button(
                label="DOWNLOAD ARTWORK",
                data=artwork_bytes,
                file_name=f"{safe_title}_artwork.png",
                mime="image/png",
                key="download_artwork_button"
            )

    # Add RSS publishing section
    st.header("Publish to RSS Feed")
    
    if st.button("Publish Episode to RSS Feed"):
        # Prepare episode data
        episode_data = {
            'title': title,
            'description': f"{host1_name} and {host2_name} tackle {title.lower()}. {host1_name} brings his signature mix of curiosity and skepticism, while {host2_name} offers her unfiltered take on the subject. Expect unexpected insights, heated debates, and plenty of laughs.",
            'audio_file': audio_path,
            'artwork_file': artwork_path,
            'duration': '00:30:00'  # Default duration, can be made dynamic
        }
        
        # Add episode to RSS feed
        if rss_manager.add_episode(episode_data):
            st.success("Episode published to RSS feed!")
            st.info(f"RSS Feed URL: {rss_manager.get_feed_url()}")
            st.markdown("""
            **Next Steps:**
            1. Push the updated files to your GitHub repository
            2. Submit your RSS feed URL to podcast directories (Apple Podcasts, Spotify, etc.)
            """)
        else:
            st.error("Failed to publish episode to RSS feed. Check the logs for details.")


# --- Streamlit App ---

# Set page configuration (should be the first Streamlit command)
st.set_page_config(
    page_title="Dynamic Podcast Generator",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load external CSS
load_css("style.css")

# Initialize AI instances
genai = None
voice_synth = None
personality_analyzer = None
artwork_generator = None

# Add GitHub configuration section
st.sidebar.header("GitHub Configuration")
github_username = st.sidebar.text_input("GitHub Username", value="yourusername")
repo_name = st.sidebar.text_input("Repository Name", value="yourpodcast")

# Initialize RSS manager
rss_manager = RssFeedManager(github_username, repo_name)

if not OPENAI_API_KEY:
    st.error("OpenAI API key not found. Please set OPENAI_API_KEY in your .env file or environment variables. Script generation disabled.")
else:
    try:
        genai = GenAI(OPENAI_API_KEY)
        personality_analyzer = PersonalityAnalyzer(OPENAI_API_KEY)
        artwork_generator = ArtworkGenerator(OPENAI_API_KEY)
        logging.info("GenAI, PersonalityAnalyzer, and ArtworkGenerator initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize AI modules: {e}")
        st.error(f"Error initializing AI modules: {e}")

if not ELEVENLABS_API_KEY:
    st.warning("ElevenLabs API key not found. Please set ELEVENLABS_API_KEY in your environment to enable audio generation.")
else:
    try:
        voice_synth = VoiceSynthesizer(ELEVENLABS_API_KEY)
        logging.info("VoiceSynthesizer initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize VoiceSynthesizer: {e}")
        st.error(f"Error initializing Voice Synthesizer module: {e}")
        voice_synth = None # Disable voice synth if init fails

# --- UI Layout ---

# Inject Google Fonts (Montserrat)
st.markdown(
    """
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600&display=swap" rel="stylesheet">
    """,
    unsafe_allow_html=True
)

st.title("CALL HIM DADDY, JOE")
st.markdown(
    '''
    <div class="subheading-container">
        <span class="subheading">Custom Podcasts</span>
    </div>
    ''',
    unsafe_allow_html=True
)

# --- Personality Input Section ---
with st.container(border=False):
    st.header("🎭 Choose Your Podcast Hosts")

    # Mode selection: Legacy mode (Joe & Alex) or Custom Hosts
    mode = st.radio(
        "Choose Mode:",
        ["Custom", "Legacy (Rogan & Cooper)"],
        horizontal=True,
        key="mode_selection"
    )

    # Only show personality inputs if custom hosts mode is selected
    if mode == "Custom":
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Host")
            # handle_personality_input returns the name entered in the text_input widget
            # The widget itself uses the key 'host1_name'
            host1_name_input, host1_text, host1_photo = handle_personality_input(1)

        with col2:
            st.subheader("Guest")
            # The widget itself uses the key 'host2_name'
            host2_name_input, host2_text, host2_photo = handle_personality_input(2)
    else:
        # Legacy mode - use default Joe Rogan and Alex Cooper
        # These are the names used for generation, not directly tied to input widgets in this mode
        host1_name_input = "Joe Rogan"
        host2_name_input = "Alex Cooper"
        host1_text = ""
        host2_text = ""

        st.info("Using legacy mode with pre-defined Joe Rogan and Alex Cooper personalities.")

# --- Topic Input Section ---
with st.container(border=False):
    st.header("🔥 CHOOSE YOUR PODCAST TOPIC & SETTINGS") # Updated header

    col1, col2 = st.columns([3, 2])
    with col1:
        input_type = st.radio(
            "Choose input type:",
            ["Text", "URL", "Image"],
            horizontal=True,
            key="input_type_radio"
        )
    with col2:
        podcast_length = st.radio(
            "Podcast Length:",
            ["Short (3-5 min)", "Medium (5-10 min)", "Long (10-15 min)"],
            horizontal=True,
            index=0, # Default to Short
            key="podcast_length_radio"
        )
        length_param = podcast_length.split(" ")[0].lower()

    # Get content based on selected input type using helper functions
    topic_content = ""
    format_type = "text" # Default

    if input_type == "Text":
        topic_content, format_type = handle_text_input()
    elif input_type == "URL":
        topic_content, format_type = handle_url_input()
    elif input_type == "Image":
        topic_content, format_type = handle_image_input()

    # --- Mode Selection ---
    st.subheader("🎭 Episode Modes")
    
    fight_mode = st.checkbox(
        "🥊 Fight Mode",
        key="fight_mode_checkbox",
        help="Generates a script with intense arguments, less respect, and a possibility one host storms out."
    )
    
    qa_mode = st.checkbox(
        "❓ Q&A Mode",
        key="qa_mode_checkbox",
        help="Includes audience questions in the second half of the episode."
    )
    
    flirt_mode = st.checkbox(
        "💘 Flirt Mode",
        key="flirt_mode_checkbox",
        help="Adds subtle romantic tension that builds throughout the episode."
    )
    
    ad_mode = st.checkbox(
        "💰 Ad Mode",
        key="ad_mode_checkbox",
        help="Includes a personality-appropriate ad read in the middle of the episode."
    )

    # Generate Button
    generate_button = st.button("Generate Podcast",
                                type="primary",
                                use_container_width=True,
                                key="generate_button")

# --- Results Section ---
# Use flags in session state to track if generation has occurred
if 'generation_complete' not in st.session_state:
    st.session_state.generation_complete = False

if generate_button:
    # Reset generation state and clear previous results
    st.session_state.generation_complete = False
    if 'script' in st.session_state: del st.session_state['script']
    if 'display_script' in st.session_state: del st.session_state['display_script']
    if 'episode_title' in st.session_state: del st.session_state['episode_title']
    if 'audio_path' in st.session_state: del st.session_state['audio_path']
    if 'host1_data' in st.session_state: del st.session_state['host1_data']
    if 'host2_data' in st.session_state: del st.session_state['host2_data']
    # Clear the final host names as well
    if 'final_host1_name' in st.session_state: del st.session_state['final_host1_name']
    if 'final_host2_name' in st.session_state: del st.session_state['final_host2_name']


    if not topic_content:
        st.error("Please provide input (text, valid URL, or image) before generating.")
    elif not genai:
        st.error("AI module not initialized. Cannot generate script. Check OpenAI API key.")
    elif mode == "Custom" and (not host1_name_input or not host2_name_input):
        st.error("Please provide names for both hosts.")
    elif mode == "Custom" and (not host1_text or not host2_text):
        st.error("Please provide text samples for both hosts.")
    else:
        # 1. Analyze personalities if in custom mode
        host1_data = None
        host2_data = None

        if mode == "Custom":
            with st.spinner("🧠 Analyzing host personalities..."):
                try:
                    host1_data = personality_analyzer.analyze_personality(host1_name_input, host1_text)
                    host2_data = personality_analyzer.analyze_personality(host2_name_input, host2_text)

                    # Check for errors in analysis
                    if "error" in host1_data:
                        st.error(f"Error analyzing {host1_name_input}'s personality: {host1_data['error']}")
                        host1_data = None
                    else:
                        # Add name to the data
                        host1_data["name"] = host1_name_input
                        st.success(f"Successfully analyzed {host1_name_input}'s personality!")

                    if "error" in host2_data:
                        st.error(f"Error analyzing {host2_name_input}'s personality: {host2_data['error']}")
                        host2_data = None
                    else:
                        # Add name to the data
                        host2_data["name"] = host2_name_input
                        st.success(f"Successfully analyzed {host2_name_input}'s personality!")

                    # Store in session state
                    st.session_state.host1_data = host1_data
                    st.session_state.host2_data = host2_data

                    # If either analysis failed, stop
                    if not host1_data or not host2_data:
                        st.error("Personality analysis failed. Please try again with different text samples.")
                        script = None # Ensure script generation is skipped
                    else:
                        logging.info("Personality analysis completed successfully.")
                except Exception as e:
                    logging.error(f"Exception during personality analysis: {e}", exc_info=True)
                    st.error(f"An unexpected error occurred during personality analysis: {e}")
                    script = None # Ensure script generation is skipped

        # 2. Generate Script
        script = None
        # Proceed only if not in custom mode OR if personality analysis succeeded
        if mode == "Legacy (Rogan & Cooper)" or (mode == "Custom" and host1_data and host2_data):
            # --- Determine if a host should leave (50% chance if fight_mode is on) ---
            host_leaves = False
            if fight_mode and random.random() < 0.5: # 50% chance
                host_leaves = True
                logging.info("Fight Mode: A host will leave the episode.")
            # --- End leaving chance ---

            spinner_text = "🧠 Generating podcast script..."
            if fight_mode:
                spinner_text = "🥊 Generating INTENSE podcast script (Fight Mode!)..."
            elif flirt_mode:
                spinner_text = "💘 Generating ROMANTIC podcast script..."
            elif qa_mode:
                spinner_text = "❓ Generating Q&A podcast script..."
            elif ad_mode:
                spinner_text = "💰 Generating podcast script with ads..."

            with st.spinner(spinner_text):
                try:
                    if mode == "Legacy (Rogan & Cooper)":
                        script = genai.generate_podcast_script(
                            topic_content,
                            format_type,
                            length_param,
                            fight_mode=fight_mode,
                            host_leaves=host_leaves,
                            qa_mode=qa_mode,
                            flirt_mode=flirt_mode,
                            ad_mode=ad_mode
                        )
                    else: # Custom mode with successful analysis
                        # Use dynamic script generation with analyzed personalities
                        script = genai.generate_dynamic_podcast_script(
                            topic_content,
                            host1_data,
                            host2_data,
                            format_type,
                            length_param,
                            fight_mode=fight_mode,
                            host_leaves=host_leaves,
                            qa_mode=qa_mode,
                            flirt_mode=flirt_mode,
                            ad_mode=ad_mode
                        )

                    if not script or script.startswith("Error"):
                        st.error(script if script else "Error: Script generation failed (empty response).")
                        script = None # Ensure script is None on error
                    else:
                        logging.info("Script generated successfully.")
                        st.success("Script generation complete!")
                except Exception as e:
                    logging.error(f"Exception during script generation: {e}", exc_info=True)
                    st.error(f"An unexpected error occurred during script generation: {e}")
                    script = None

        # Proceed only if script generation was successful
        if script:
            # Extract title and prepare display script
            episode_title = extract_title(script)
            
            # If we got the default title in legacy mode, try to generate a better one
            if mode == "Legacy (Rogan & Cooper)" and episode_title.startswith("Dynamic Podcast Episode"):
                # Try to extract a topic-based title from the first few lines
                first_lines = script.split('\n')[:5]
                for line in first_lines:
                    if ':' in line and not any(x in line.lower() for x in ['episode', 'title', 'host', 'guest']):
                        # Found a potential topic line
                        topic = line.split(':', 1)[1].strip()
                        if topic and len(topic) < 100:  # Reasonable length check
                            episode_title = f"{topic} - Joe & Alex Discuss"
                            break

            # Remove title line from display script if it exists
            display_script = script
            if script.split("\n")[0].strip().upper().startswith(("EPISODE TITLE:", "TITLE:", "PODCAST TITLE:")):
                display_script = "\n".join(script.split("\n")[1:]).strip()

            # Store results in session state
            st.session_state.script = script # Store original script if needed
            st.session_state.display_script = display_script
            st.session_state.episode_title = episode_title
            st.session_state.audio_path = None # Reset audio path for new generation

            # *** FIX: Store the host names used for generation under DIFFERENT keys ***
            # Use the names determined earlier (either from input or defaults)
            st.session_state.final_host1_name = host1_name_input
            st.session_state.final_host2_name = host2_name_input
            # *** END FIX ***

            # Store personality data for review
            if mode == "Custom":
                st.session_state.host1_personality = host1_data
                st.session_state.host2_personality = host2_data
            else:
                # For legacy mode, store the predefined personalities
                from joealex_data import JOE_ROGAN_PERSONALITY, ALEX_COOPER_PERSONALITY
                st.session_state.host1_personality = {
                    "name": "Joe Rogan",
                    "background": JOE_ROGAN_PERSONALITY["background"],
                    "speech_patterns": JOE_ROGAN_PERSONALITY["speech_patterns"],
                    "topics": JOE_ROGAN_PERSONALITY["topics"]
                }
                st.session_state.host2_personality = {
                    "name": "Alex Cooper",
                    "background": ALEX_COOPER_PERSONALITY["background"],
                    "speech_patterns": ALEX_COOPER_PERSONALITY["speech_patterns"],
                    "topics": ALEX_COOPER_PERSONALITY["topics"]
                }

            # 3. Generate Artwork (if possible and script exists)
            artwork_path = None

            # Generate artwork if possible
            if artwork_generator:
                with st.spinner("🎨 Generating episode artwork..."):
                    try:
                        # Get host photos from session state
                        host1_photo = st.session_state.get(f"host1_photo")
                        host2_photo = st.session_state.get(f"host2_photo")
                        
                        # In legacy mode, we don't have photos but can still generate artwork
                        if mode == "Legacy (Rogan & Cooper)":
                            st.info("Artwork generation not available in legacy mode.")
                            artwork_path = None
                        else:
                            artwork_result = artwork_generator.generate_artwork(
                                episode_title,
                                topic_content,
                                output_path=f"output/{get_safe_filename(episode_title)}_artwork.png",
                                host1_photo=host1_photo,
                                host2_photo=host2_photo
                            )
                            
                            if isinstance(artwork_result, str) and not artwork_result.startswith("Error"):
                                artwork_path = artwork_result
                                st.session_state.artwork_path = artwork_path  # Store in session state
                                st.success("Artwork generated successfully!")
                            else:
                                st.warning("Artwork generation failed.")
                    except Exception as e:
                        logging.error(f"Error generating artwork: {e}", exc_info=True)
                        st.warning("Artwork generation failed. Continuing without artwork.")

            # 4. Audio Generation Confirmation
            if voice_synth and ELEVENLABS_API_KEY:
                st.markdown("---")
                st.subheader("🎙️ Audio Generation")
                st.info("Audio generation uses ElevenLabs credits. Would you like to generate audio for this episode?")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Generate Audio", type="primary"):
                        with st.spinner("🎙️ Synthesizing podcast audio (this may take a few minutes)..."):
                            try:
                                # Ensure display_script is not empty before sending to TTS
                                if display_script and display_script.strip():
                                    # Use the final host names stored in session state for audio generation
                                    current_host1 = st.session_state.final_host1_name
                                    current_host2 = st.session_state.final_host2_name

                                    audio_result = voice_synth.generate_audio(
                                        display_script,
                                        host1_name=current_host1,
                                        host2_name=current_host2
                                    )

                                    if isinstance(audio_result, str) and audio_result.startswith("Error"):
                                        st.error(f"Audio Generation Failed: {audio_result}")
                                    elif os.path.exists(audio_result) and os.path.getsize(audio_result) > 0:
                                        audio_path = audio_result
                                        st.session_state.audio_path = audio_path # Store successful path
                                        st.success("Audio generation complete!")
                                        logging.info(f"Audio generated successfully at {audio_path}")
                                    else:
                                        st.error("Audio generation finished, but the output file seems invalid or empty.")
                                        logging.error(f"Audio generation failed or produced invalid file: {audio_result}")
                                else:
                                    st.warning("Script content is empty after removing title. Skipping audio generation.")
                                    logging.warning("Skipping audio generation due to empty display_script.")

                            except Exception as e:
                                logging.error(f"Exception during audio generation: {e}", exc_info=True)
                                st.error(f"An unexpected error occurred during audio generation: {e}")
                with col2:
                    if st.button("Skip Audio Generation"):
                        st.info("Audio generation skipped. You can generate audio later if needed.")
            elif ELEVENLABS_API_KEY:
                st.warning("Voice synthesizer failed to initialize. Cannot generate audio. Check logs/API key.")
            else:
                st.info("ElevenLabs API key not configured. Audio generation not available.")

            # Mark generation as complete
            st.session_state.generation_complete = True


# --- Display Current Results Section (if generation completed in this run or previous) ---
if st.session_state.generation_complete and 'display_script' in st.session_state and 'episode_title' in st.session_state:
    st.markdown("---") # Separator

    display_podcast_output(
        st.session_state.episode_title,
        st.session_state.display_script,
        st.session_state.final_host1_name, # Pass the retrieved final names
        st.session_state.final_host2_name, # Pass the retrieved final names
        st.session_state.get('audio_path'), # Use .get for safety in case it's still None
        st.session_state.get('artwork_path') # Add artwork path
    )

    # Add personality review dropdown at the end
    with st.expander("Review Personality Data", expanded=False):
        st.markdown("### Host 1 Personality")
        st.json(st.session_state.host1_personality)
        st.markdown("### Host 2 Personality")
        st.json(st.session_state.host2_personality)

# --- Footer ---
st.markdown("---")
st.caption("© 2025, PodCraft LLC.")

