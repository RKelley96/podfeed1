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
import json
import base64

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
    """
    # Regex to find "EPISODE TITLE:" possibly followed by whitespace, then capture the rest of the line
    match = re.match(r"EPISODE TITLE:\s*(.*)", script, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        # Remove potential trailing dashes left by the model
        title = re.sub(r'\s*--*$', '', title).strip()
        return title
    else:
        logging.warning("Could not find 'EPISODE TITLE:' line in the script.")
        return "Dynamic Podcast - Episode" # Generic default title

def get_safe_filename(title):
    """Creates a safe filename from a title string."""
    # Remove or replace invalid characters
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
    safe_title = safe_title.replace(" ", "_")
    # Limit length if necessary
    return safe_title[:100] # Limit filename length

def handle_text_input():
    """Handles text input type."""
    value = st.session_state.get("random_topic", "")
    content = st.text_area("Enter a topic:",
                           placeholder="",
                           height=100,
                           key="text_input_area",
                           value=value)
    # If user types, update random_topic
    st.session_state["random_topic"] = content
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

def handle_youtube_input():
    """Handles YouTube URL input and transcript extraction (no preview, no speaker selection)."""
    youtube_url = st.text_input(
        "Enter YouTube URL:",
        placeholder="https://www.youtube.com/watch?v=...",
        key="youtube_url_input"
    )
    content = ""
    if youtube_url:
        with st.spinner("Extracting transcript from YouTube video..."):
            result = extract_text_from_url(youtube_url)
            if isinstance(result, str) and (result.startswith("Error:") or result.startswith("Warning:")):
                st.error(result)
                content = "" # Reset content on error
            elif isinstance(result, dict) and result["type"] == "youtube":
                # Remove [Music] and similar tags, and lines that are just music or filler
                lines = result["transcript"].split('\n')
                cleaned_lines = []
                for line in lines:
                    l = line.strip()
                    # Remove lines that are just [Music], [Applause], etc. or empty
                    if re.match(r"^\[.*?\]$", l, re.IGNORECASE):
                        continue
                    # Remove lines that are just speaker tags with no content
                    if re.match(r"^\[.*?\]:\s*$", l):
                        continue
                    # Remove lines that are just numbers or timestamps
                    if re.match(r"^\[?\d+\]?[:\.]?$", l):
                        continue
                    # Remove lines that are just filler like 'listening', 'I'm running late', etc. (optional, can expand)
                    if l.lower() in ["listening", "i'm running late", "oh", "dear", "the freconomics radio network", "the hidden side of everything"]:
                        continue
                    cleaned_lines.append(l)
                content = "\n".join(cleaned_lines)
                st.success("Transcript extracted successfully!")
            else:
                st.warning("Could not extract transcript from YouTube video.")
    return content, "youtube"

def handle_personality_input(host_number):
    import json
    if f"host{host_number}_sources" not in st.session_state:
        st.session_state[f"host{host_number}_sources"] = []
    if f"host{host_number}_source_types" not in st.session_state:
        st.session_state[f"host{host_number}_source_types"] = []

    host_name = st.text_input(
        "",
        placeholder=f"Enter name for Guest" if host_number == 2 else "Enter name for Host",
        key=f"host{host_number}_name"
    )

    input_method = st.radio(
        "",
        ["Text Input", "File Upload", "URL", "YouTube"],
        horizontal=True,
        key=f"host{host_number}_input_method"
    )

    text_input_val = ""
    uploaded_file = None
    url_input_val = ""
    youtube_input_val = ""
    if input_method == "Text Input":
        text_input_val = st.text_area(
            "Enter text sample:",
            placeholder="Paste interviews, articles, transcripts, or other text that represents this personality's style and interests.",
            height=100,
            key=f"host{host_number}_text_input_new"
        )
    elif input_method == "File Upload":
        uploaded_file = st.file_uploader(
            "Upload text file:",
            type=["txt", "md", "doc", "docx", "pdf"],
            key=f"host{host_number}_file_upload_new"
        )
    elif input_method == "URL":
        url_input_val = st.text_input(
            "Enter a URL:",
            placeholder="https://example.com/interview-or-profile",
            key=f"host{host_number}_url_input_new"
        )
    elif input_method == "YouTube":
        youtube_input_val = st.text_input(
            "Enter YouTube URL:",
            placeholder="https://www.youtube.com/watch?v=...",
            key=f"host{host_number}_youtube_input_new"
        )

    if st.button("Add Source", key=f"add_source_{host_number}"):
        new_source = ""
        new_source_type = input_method
        if input_method == "Text Input":
            new_source = text_input_val.strip()
        elif input_method == "File Upload":
            if uploaded_file:
                try:
                    new_source = uploaded_file.getvalue().decode("utf-8").strip()
                except Exception as e:
                    st.error(f"Error reading file: {e}")
                    new_source = ""
            else:
                st.warning("Please upload a file before adding.")
        elif input_method == "URL":
            if url_input_val:
                with st.spinner("Extracting content from URL..."):
                    content = extract_text_from_url(url_input_val)
                    if content.startswith("Error:") or content.startswith("Warning:"):
                        st.error(content)
                        new_source = ""
                    else:
                        new_source = content.strip()
            else:
                st.warning("Please enter a URL before adding.")
        elif input_method == "YouTube":
            if youtube_input_val:
                with st.spinner("Extracting transcript from YouTube video..."):
                    result = extract_text_from_url(youtube_input_val)
                    if isinstance(result, str) and (result.startswith("Error:") or result.startswith("Warning:")):
                        st.error(result)
                        new_source = ""
                    elif isinstance(result, dict) and result["type"] == "youtube":
                        lines = result["transcript"].split('\n')
                        cleaned_lines = []
                        for line in lines:
                            l = line.strip()
                            if re.match(r"^\[.*?\]$", l, re.IGNORECASE):
                                continue
                            if re.match(r"^\[.*?\]:\s*$", l):
                                continue
                            if re.match(r"^\[?\d+\]?[:\.]?$", l):
                                continue
                            if l.lower() in ["listening", "i'm running late", "oh", "dear", "the freconomics radio network", "the hidden side of everything"]:
                                continue
                            cleaned_lines.append(l)
                        new_source = "\n".join(cleaned_lines).strip()
                        if not new_source:
                            st.warning("Transcript was found but is empty after cleaning. Try a different video or check captions.")
                            st.info(f"Raw transcript result: {result['transcript'][:500]}...")
                    else:
                        st.warning("Could not extract transcript from YouTube video. (Debug: " + str(result)[:300] + ")")
            else:
                st.warning("Please enter a YouTube URL before adding.")
        if new_source:
            st.session_state[f"host{host_number}_sources"].append(new_source)
            st.session_state[f"host{host_number}_source_types"].append(new_source_type)
            st.success("Source added!")
        elif input_method == "Text Input":
            st.warning("Please provide some content before adding.")

    combined_text = ""
    if st.session_state[f"host{host_number}_sources"]:
        st.markdown("**Current Sources:**")
        for i, src in enumerate(st.session_state[f"host{host_number}_sources"]):
            src_type = st.session_state[f"host{host_number}_source_types"][i] if i < len(st.session_state[f"host{host_number}_source_types"]) else "Source"
            with st.expander(f"Source {i+1}: {src_type}"):
                st.text_area(f"Source {i+1} Content", src, height=80, key=f"host{host_number}_source_{i}", disabled=True)
                if st.button(f"Remove Source {i+1}", key=f"remove_source_{host_number}_{i}"):
                    st.session_state[f"host{host_number}_sources"].pop(i)
                    st.session_state[f"host{host_number}_source_types"].pop(i)
                    st.rerun()

        personality_json = None
        combined_text = "\n\n---\n\n".join(st.session_state[f"host{host_number}_sources"])
        if combined_text and host_name:
            if st.button(f"Generate Personality for {host_name or ('Guest' if host_number == 2 else 'Host')}", key=f"generate_personality_{host_number}"):
                with st.spinner("Analyzing personality..."):
                    try:
                        analyzer = PersonalityAnalyzer(os.getenv("OPENAI_API_KEY"))
                        personality_json = analyzer.analyze_personality(host_name, combined_text)
                        st.success("Personality generated!")
                    except Exception as e:
                        st.error(f"Error generating personality: {e}")
                        personality_json = None
        if personality_json:
            with st.expander(f"Show Personality JSON for {host_name or ('Guest' if host_number == 2 else 'Host')}"):
                st.code(json.dumps(personality_json, indent=2), language="json")
    return host_name, combined_text

def display_podcast_output(title, display_script, host1_name, host2_name, audio_path=None, artwork_path=None):
    """Displays the generated podcast title, script, audio player, and download buttons."""
    st.subheader("EPISODE TITLE")
    # Display title using the CSS class
    st.markdown(f'<div class="episode-title"><h2>{title}</h2></div>', unsafe_allow_html=True)

    # Generate and display episode description
    description = f"In this explosive episode, {host1_name} and {host2_name} dive deep into a heated discussion that will leave you questioning everything you thought you knew. With {host1_name}'s unique perspective and {host2_name}'s sharp insights, this conversation takes unexpected turns that you won't want to miss. Whether you're a long-time listener or new to the show, this episode promises to be one of the most memorable yet. Tune in for a conversation that's as entertaining as it is thought-provoking."
    
    st.markdown("### EPISODE DESCRIPTION")
    st.markdown(f'<div class="episode-description">{description}</div>', unsafe_allow_html=True)

    # Display script using the formatting function and CSS classes
    st.subheader("PODCAST SCRIPT")
    formatted_script_html = format_script(display_script, host1_name, host2_name)
    st.markdown(formatted_script_html, unsafe_allow_html=True)

    # Script Download Button (moved directly after script, removed heading)
    safe_title = get_safe_filename(title)
    script_bytes = display_script.encode('utf-8')
    st.download_button(
        label="DOWNLOAD SCRIPT",
        data=script_bytes,
        file_name=f"{safe_title}_script.txt",
        mime="text/plain",
        key="download_script_button"
    )

    # Display artwork
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

PERSONALITY_DIR = "personalities"
os.makedirs(PERSONALITY_DIR, exist_ok=True)

def load_saved_personalities():
    personalities = []
    names = []
    for fname in os.listdir(PERSONALITY_DIR):
        if fname.endswith(".json"):
            with open(os.path.join(PERSONALITY_DIR, fname), "r") as f:
                data = json.load(f)
                personalities.append(data)
                names.append(data["name"])
    return personalities, names

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

st.title("🎙️ Call Him Daddy, Joe")  # Updated app name with microphone emojis
st.markdown(
    '''
    <div style="text-align:center; margin-top:-1rem; margin-bottom:2rem;">
        <span style="font-size:1.2rem; color:#FF1493; letter-spacing:1px;">
            Custom Podcasts
        </span>
    </div>
    ''',
    unsafe_allow_html=True
)

# Remove legacy mode and restore Custom mode as the only workflow
mode = "Custom"

# --- Personality Input Section ---
tab1, tab_manager, tab2, tab3, tab_audio, tab_artwork, tab_rss = st.tabs(["Personality Creator", "Personality Manager", "Host & Guest Selection", "Episode Topic and Settings", "Audio", "Artwork", "RSS Upload"])

# On app start, load all saved personalities from disk
if 'personalities' not in st.session_state or 'personality_names' not in st.session_state:
    personalities, names = load_saved_personalities()
    st.session_state['personalities'] = personalities
    st.session_state['personality_names'] = names

# --- Personality Manager Tab ---
with tab_manager:
    st.subheader("Personality Manager")
    if st.session_state['personalities']:
        for i, p in enumerate(st.session_state['personalities']):
            with st.expander(p['name']):
                # Delete button at the top
                if st.button("🗑️ Delete Profile", key=f"delete_personality_manager_{i}"):
                    json_path = os.path.join(PERSONALITY_DIR, f"{p['name']}.json")
                    if os.path.exists(json_path):
                        os.remove(json_path)
                    photo_path = os.path.join(PERSONALITY_DIR, "photos", f"{p['name']}.jpg")
                    if os.path.exists(photo_path):
                        os.remove(photo_path)
                    st.session_state['personalities'].pop(i)
                    st.session_state['personality_names'].pop(i)
                    st.success(f"Deleted {p['name']}")
                    st.rerun()
                # Restore background description and audio
                if 'background' in p:
                    st.markdown(f"<div style='font-size:0.95rem; color:#aaa; margin-bottom:0.5rem'>{p['background']}</div>", unsafe_allow_html=True)
                if p.get('background_audio'):
                    st.audio(os.path.join(PERSONALITY_DIR, p['background_audio']), format="audio/mp3")
                # --- Photo Management ---
                st.markdown("<div style='margin-top:0.5rem; margin-bottom:0.5rem; font-size:0.95rem; color:#fff;'>Photo:</div>", unsafe_allow_html=True)
                photo_path = os.path.join(PERSONALITY_DIR, "photos", f"{p['name']}.jpg")
                if os.path.exists(photo_path):
                    st.markdown("""
                        <div style='width: 100px; height: 100px; overflow: hidden; border-radius: 4px; margin-bottom: 0.5rem;'>
                            <img src='data:image/jpeg;base64,{}' style='width: 100%; height: 100%; object-fit: cover;' />
                        </div>
                    """.format(base64.b64encode(open(photo_path, 'rb').read()).decode()), unsafe_allow_html=True)
                    if st.button("🗑️ Delete Photo", key=f"delete_photo_{i}"):
                        os.remove(photo_path)
                        st.success("Photo deleted!")
                        st.rerun()
                else:
                    photo_file = st.file_uploader(
                        "Upload photo",
                        type=["jpg", "jpeg", "png"],
                        key=f"photo_upload_{i}"
                    )
                    if photo_file:
                        os.makedirs(os.path.join(PERSONALITY_DIR, "photos"), exist_ok=True)
                        with open(photo_path, "wb") as f:
                            f.write(photo_file.getvalue())
                        st.success("Photo uploaded!")
                        st.rerun()
    else:
        st.info("No personalities saved yet.")
    st.markdown('<div style="text-align:center; margin: 2rem 0; font-size:1.1rem; color:#FF1493;"><b>© 2025 PodCraft LLC</b></div>', unsafe_allow_html=True)

# Personality Creator: agnostic, single workflow
with tab1:
    st.subheader("Personality Creator")
    if 'new_personality_sources' not in st.session_state:
        st.session_state['new_personality_sources'] = []
    if 'new_personality_source_types' not in st.session_state:
        st.session_state['new_personality_source_types'] = []
    if 'new_personality_json' not in st.session_state:
        st.session_state['new_personality_json'] = None

    new_name = st.text_input("Personality Name", key="new_personality_name")
    input_method = st.radio(
        "Input Type:",
        ["Text Input", "File Upload", "URL", "YouTube"],
        horizontal=True,
        key="personality_input_method"
    )
    text_input_val = ""
    uploaded_file = None
    url_input_val = ""
    youtube_input_val = ""
    if input_method == "Text Input":
        text_input_val = st.text_area("Enter text sample:", height=100, key="personality_text_input")
    elif input_method == "File Upload":
        uploaded_file = st.file_uploader("Upload text file:", type=["txt", "md", "doc", "docx", "pdf"], key="personality_file_upload")
    elif input_method == "URL":
        url_input_val = st.text_input("Enter a URL:", key="personality_url_input")
    elif input_method == "YouTube":
        youtube_input_val = st.text_input("Enter YouTube URL:", key="personality_youtube_input")

    if st.button("Add Source", key="add_new_personality_source"):
        new_source = ""
        new_source_type = input_method
        if input_method == "Text Input":
            new_source = text_input_val.strip()
        elif input_method == "File Upload":
            if uploaded_file:
                try:
                    new_source = uploaded_file.getvalue().decode("utf-8").strip()
                except Exception as e:
                    st.error(f"Error reading file: {e}")
                    new_source = ""
            else:
                st.warning("Please upload a file before adding.")
        elif input_method == "URL":
            if url_input_val:
                with st.spinner("Extracting content from URL..."):
                    content = extract_text_from_url(url_input_val)
                    if content.startswith("Error:") or content.startswith("Warning:"):
                        st.error(content)
                        new_source = ""
                    else:
                        new_source = content.strip()
            else:
                st.warning("Please enter a URL before adding.")
        elif input_method == "YouTube":
            if youtube_input_val:
                with st.spinner("Extracting transcript from YouTube video..."):
                    result = extract_text_from_url(youtube_input_val)
                    if isinstance(result, str) and (result.startswith("Error:") or result.startswith("Warning:")):
                        st.error(result)
                        new_source = ""
                    elif isinstance(result, dict) and result["type"] == "youtube":
                        lines = result["transcript"].split('\n')
                        cleaned_lines = []
                        for line in lines:
                            l = line.strip()
                            if re.match(r"^\[.*?\]$", l, re.IGNORECASE):
                                continue
                            if re.match(r"^\[.*?\]:\s*$", l):
                                continue
                            if re.match(r"^\[?\d+\]?[:\.]?$", l):
                                continue
                            if l.lower() in ["listening", "i'm running late", "oh", "dear", "the freconomics radio network", "the hidden side of everything"]:
                                continue
                            cleaned_lines.append(l)
                        new_source = "\n".join(cleaned_lines).strip()
                        if not new_source:
                            st.warning("Transcript was found but is empty after cleaning. Try a different video or check captions.")
                            st.info(f"Raw transcript result: {result['transcript'][:500]}...")
                    else:
                        st.warning("Could not extract transcript from YouTube video. (Debug: " + str(result)[:300] + ")")
            else:
                st.warning("Please enter a YouTube URL before adding.")
        if new_source:
            st.session_state['new_personality_sources'].append(new_source)
            st.session_state['new_personality_source_types'].append(new_source_type)
            st.success("Source added!")
        elif input_method == "Text Input":
            st.warning("Please provide some content before adding.")

    combined_text = ""
    if st.session_state['new_personality_sources']:
        st.markdown("**Current Sources:**")
        for i, src in enumerate(st.session_state['new_personality_sources']):
            src_type = st.session_state['new_personality_source_types'][i] if i < len(st.session_state['new_personality_source_types']) else "Source"
            with st.expander(f"Source {i+1}: {src_type}"):
                st.text_area(f"Source {i+1} Content", src, height=80, key=f"new_personality_source_{i}", disabled=True)
                if st.button(f"Remove Source {i+1}", key=f"remove_new_personality_source_{i}"):
                    st.session_state['new_personality_sources'].pop(i)
                    st.session_state['new_personality_source_types'].pop(i)
                    st.rerun()
        combined_text = "\n\n---\n\n".join(st.session_state['new_personality_sources'])

    if combined_text and new_name:
        # Only show the button if not currently generating
        if 'generating_new_personality' not in st.session_state or not st.session_state['generating_new_personality']:
            if st.button("Generate Personality", key="generate_new_personality"):
                st.session_state['generating_new_personality'] = True
                with st.spinner("Analyzing personality..."):
                    try:
                        analyzer = PersonalityAnalyzer(os.getenv("OPENAI_API_KEY"))
                        personality_json = analyzer.analyze_personality(new_name, combined_text)
                        st.session_state['new_personality_json'] = personality_json
                        st.success("Personality generated!")
                    except Exception as e:
                        st.error(f"Error generating personality: {e}")
                        st.session_state['new_personality_json'] = None
                st.session_state['generating_new_personality'] = False
        # Do not render any button (enabled or disabled) while generating
        if st.session_state['new_personality_json']:
            with st.expander(f"Show Personality JSON for {new_name}"):
                st.code(json.dumps(st.session_state['new_personality_json'], indent=2), language="json")
            # --- Audio Sample Upload for Voice Cloning (after JSON, before Save, outside expander) ---
            st.markdown("<div style='margin-top:1.2rem; margin-bottom:0.5rem; font-size:1rem; font-weight:600;'>Audio sample:</div>", unsafe_allow_html=True)
            audio_file = st.file_uploader(
                label="Upload audio sample (MP3 or WAV)",
                type=["mp3", "wav"],
                key="personality_audio_upload",
                label_visibility="collapsed"
            )
            st.markdown("""
            <style>
            [data-testid='stFileUploader']:has(input[type=\"file\"][accept*='audio']) {
                max-width: 400px !important;
                margin-bottom: 1.5rem;
            }
            [data-testid='stFileUploader']:has(input[type=\"file\"][accept*='audio']) button {
                font-size: 1rem !important;
                padding: 8px 18px !important;
                min-width: 120px !important;
                max-width: 180px !important;
                border-radius: 4px !important;
            }
            </style>
            """, unsafe_allow_html=True)
            st.markdown("<div style='margin-top:0.5rem; margin-bottom:0.5rem; font-size:1rem; font-weight:600;'>Photo (Optional):</div>", unsafe_allow_html=True)
            photo_file = st.file_uploader(
                label="Upload photo (JPG or PNG)",
                type=["jpg", "jpeg", "png"],
                key="personality_photo_upload",
                label_visibility="collapsed"
            )
            st.markdown("""
            <style>
            [data-testid='stFileUploader']:has(input[type=\"file\"][accept*='image']) {
                max-width: 400px !important;
                margin-bottom: 1.5rem;
            }
            [data-testid='stFileUploader']:has(input[type=\"file\"][accept*='image']) button {
                font-size: 1rem !important;
                padding: 8px 18px !important;
                min-width: 120px !important;
                max-width: 180px !important;
                border-radius: 4px !important;
            }
            </style>
            """, unsafe_allow_html=True)
            if st.button("Save Personality", key="save_new_personality"):
                # Save both the name and the JSON part to disk, override if exists
                json_path = os.path.join(PERSONALITY_DIR, f"{new_name}.json")
                to_save = {"name": new_name}
                to_save.update(st.session_state['new_personality_json'])
                # --- ElevenLabs Voice Cloning Integration ---
                voice_id = None
                audio_sample_url = None
                background_audio_path = None
                if audio_file is not None:
                    import requests
                    elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
                    if not elevenlabs_api_key:
                        st.warning("No ElevenLabs API key found. Audio sample will not be cloned.")
                    else:
                        with st.spinner("Uploading audio sample to ElevenLabs and creating custom voice..."):
                            try:
                                url = "https://api.elevenlabs.io/v1/voices/add"
                                headers = {"xi-api-key": elevenlabs_api_key}
                                files = {"files": (audio_file.name, audio_file, audio_file.type or "audio/mpeg")}
                                data = {"name": new_name, "description": f"Voice for {new_name} created via PodCraft"}
                                response = requests.post(url, headers=headers, data=data, files=files)
                                response.raise_for_status()
                                voice_id = response.json().get("voice_id")
                                to_save["voice_id"] = voice_id
                                st.success("Custom ElevenLabs voice created and linked!")
                                # --- Optional: Generate a sample with the new voice ---
                                sample_text = f"Hello, this is the AI voice for {new_name}. Welcome to your custom podcast!"
                                tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                                tts_headers = {"xi-api-key": elevenlabs_api_key, "Content-Type": "application/json"}
                                tts_data = {"text": sample_text, "voice_settings": {"stability": 0.5, "similarity_boost": 0.5}}
                                tts_response = requests.post(tts_url, headers=tts_headers, json=tts_data)
                                if tts_response.status_code == 200:
                                    audio_sample_url = f"data:audio/mp3;base64,{tts_response.content.hex()}"
                                    st.audio(tts_response.content, format="audio/mp3")
                                    st.success("Here is a sample of the new voice!")
                                else:
                                    st.warning("Voice created, but could not generate sample audio.")
                                # --- Generate background audio and save path ---
                                if "background" in to_save and to_save["background"] and voice_id:
                                    background_text = to_save["background"]
                                    tts_data_bg = {"text": background_text, "voice_settings": {"stability": 0.5, "similarity_boost": 0.5}}
                                    tts_response_bg = requests.post(tts_url, headers=tts_headers, json=tts_data_bg)
                                    if tts_response_bg.status_code == 200:
                                        AUDIO_DIR = os.path.join(PERSONALITY_DIR, "audio")
                                        os.makedirs(AUDIO_DIR, exist_ok=True)
                                        background_audio_path = os.path.join(AUDIO_DIR, f"{new_name}_background.mp3")
                                        with open(background_audio_path, "wb") as f:
                                            f.write(tts_response_bg.content)
                                        to_save["background_audio"] = f"audio/{new_name}_background.mp3"
                                    else:
                                        to_save["background_audio"] = None
                            except Exception as e:
                                st.error(f"Error creating ElevenLabs voice: {e}")
                else:
                    to_save["background_audio"] = None
                with open(json_path, "w") as f:
                    json.dump(to_save, f, indent=2)
                # Update session state (override if exists)
                if new_name in st.session_state['personality_names']:
                    idx = st.session_state['personality_names'].index(new_name)
                    st.session_state['personalities'][idx] = to_save
                else:
                    st.session_state['personality_names'].append(new_name)
                    st.session_state['personalities'].append(to_save)
                # Show a cool animated confirmation and clear the form
                st.markdown(
                    """
                    <div style='\n                        display: flex;\n                        flex-direction: column;\n                        align-items: center;\n                        margin: 2rem 0;\n                        font-size: 1.5rem;\n                        color: #fff;\n                        font-weight: bold;\n                        background: linear-gradient(90deg, #FF1493 0%, #FF69B4 100%);\n                        border-radius: 12px;\n                        padding: 1.5rem 2rem;\n                        box-shadow: 0 4px 24px rgba(255,20,147,0.2);\n                        animation: pop 0.7s cubic-bezier(.68,-0.55,.27,1.55);\n                    '>
                        Personality saved successfully!
                    </div>
                    <style>
                    @keyframes pop {
                      0% { transform: scale(0.7); opacity: 0; }
                      80% { transform: scale(1.1); opacity: 1; }
                      100% { transform: scale(1); }
                    }
                    </style>
                    """,
                    unsafe_allow_html=True
                )
                st.session_state.update({
                    'new_personality_sources': [],
                    'new_personality_source_types': [],
                    'new_personality_json': None
                })
                st.rerun()

    # Remove the Saved Personalities section entirely
    # Add centered copyright to the middle of the tab
    st.markdown('<div style="text-align:center; margin: 2rem 0; font-size:1.1rem; color:#FF1493;"><b>© 2025 PodCraft LLC</b></div>', unsafe_allow_html=True)

# Host & Guest Selection: assign from created personalities
with tab2:
    st.subheader("Host & Guest Selection")
    personality_names = st.session_state.get('personality_names', [])
    host1_text = ""
    host2_text = ""
    host1_background = ""
    host2_background = ""
    # --- Custom Button Grid for Host/Guest Selection ---
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("<span style='font-size:1.5rem; font-weight:800;'>Select Host</span>", unsafe_allow_html=True)
        host1_name_input = st.radio(
            label="Host",
            options=personality_names if personality_names else [""],
            index=personality_names.index(st.session_state.get('host1_select', personality_names[0] if personality_names else "")) if personality_names else 0,
            key="host1_select_radio",
            label_visibility="collapsed"
        )
        for p in st.session_state.get('personalities', []):
            if p['name'] == host1_name_input:
                host1_text = p.get('text', '')
                host1_background = p.get('background', '')
        if host1_name_input:
            st.markdown(f'<div class="episode-description">{host1_background}</div>', unsafe_allow_html=True)
    with col2:
        st.markdown("<span style='font-size:1.5rem; font-weight:800;'>Select Guest</span>", unsafe_allow_html=True)
        guest_default = personality_names[1] if len(personality_names) > 1 else (personality_names[0] if personality_names else "")
        host2_name_input = st.radio(
            label="Guest",
            options=personality_names if personality_names else [""],
            index=personality_names.index(st.session_state.get('host2_select', guest_default)) if personality_names else 0,
            key="host2_select_radio",
            label_visibility="collapsed"
        )
        for p in st.session_state.get('personalities', []):
            if p['name'] == host2_name_input:
                host2_text = p.get('text', '')
                host2_background = p.get('background', '')
        if host2_name_input:
            st.markdown(f'<div class="episode-description">{host2_background}</div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center; margin: 2rem 0; font-size:1.1rem; color:#FF1493;"><b>© 2025 PodCraft LLC</b></div>', unsafe_allow_html=True)

with tab3:
    st.subheader("Episode Topic and Settings")
    # --- Get Host & Guest selections from session_state ---
    personality_names = st.session_state.get('personality_names', [])
    host1_name_input = st.session_state.get('host1_select_radio', personality_names[0] if personality_names else "")
    host2_name_input = st.session_state.get('host2_select_radio', personality_names[1] if len(personality_names) > 1 else (personality_names[0] if personality_names else ""))
    host1_json = None
    host2_json = None
    for p in st.session_state.get('personalities', []):
        if p['name'] == host1_name_input:
            host1_json = p
        if p['name'] == host2_name_input:
            host2_json = p
    input_type = st.radio(
        "Choose Input Type:",
        ["Text", "URL", "Image"],
        horizontal=True,
        key="input_type_radio"
    )
    topic_content = ""
    format_type = "text" # Default
    if input_type == "Text":
        topic_content, format_type = handle_text_input()
    elif input_type == "URL":
        topic_content, format_type = handle_url_input()
    elif input_type == "Image":
        topic_content, format_type = handle_image_input()
    
    # --- Generate Random Topic Button ---
    random_topics = [
        "Should men pay on the first date?",
        "Is social media destroying society?",
        "Cancel culture vs. free speech",
        "Is AI a threat to humanity?",
        "Should college be free?",
        "Is remote work here to stay?",
        "Are billionaires good for society?",
        "Does monogamy still make sense?",
        "Is influencer culture toxic?",
        "Should voting be mandatory?"
    ]
    if st.button("Generate Random Topic", key="generate_random_topic"):
        import random
        st.session_state["random_topic"] = random.choice(random_topics)
        st.rerun()

    # Define podcast_length before using it
    podcast_length = st.radio(
        "Podcast Length:",
        ["Super Short (30 sec)", "Short (3-5 min)", "Medium (5-10 min)", "Long (10-15 min)"],
        horizontal=True,
        index=0, # Default to Super Short for testing
        key="podcast_length_radio"
    )
    
    if podcast_length == "Super Short (30 sec)":
        length_param = "super_short"
    else:
        length_param = podcast_length.split(" ")[0].lower()
    mode_options = ["None", "🥊 Fight", "❓ Q&A", "💘 Flirt", "💰 Ad"]
    selected_mode = st.radio(
        "Special Episode Type:",
        mode_options,
        horizontal=True,
        key="episode_mode_radio"
    )

    generate_button = st.button("Generate Podcast",
                                type="primary",
                                use_container_width=True,
                                key="generate_button")

    # --- Results Section ---
    if 'generation_complete' not in st.session_state:
        st.session_state.generation_complete = False

    if generate_button:
        st.session_state.generation_complete = False
        if 'script' in st.session_state: del st.session_state['script']
        if 'display_script' in st.session_state: del st.session_state['display_script']
        if 'episode_title' in st.session_state: del st.session_state['episode_title']
        if 'audio_path' in st.session_state: del st.session_state['audio_path']
        if 'host1_data' in st.session_state: del st.session_state['host1_data']
        if 'host2_data' in st.session_state: del st.session_state['host2_data']
        if 'final_host1_name' in st.session_state: del st.session_state['final_host1_name']
        if 'final_host2_name' in st.session_state: del st.session_state['final_host2_name']

        if not topic_content:
            st.error("Please provide input (text, valid URL, or image) before generating.")
        elif not genai:
            st.error("AI module not initialized. Cannot generate script. Check OpenAI API key.")
        elif not host1_name_input or not host2_name_input:
            st.error("Please select both a host and a guest in the previous tab.")
        elif not host1_json or not host2_json:
            st.error("Please ensure both selected hosts have valid personality data.")
        else:
            # 1. Analyze personalities
            host1_data = {
                "name": host1_json["name"],
                "background": host1_json.get("background", ""),
                "speech_patterns": host1_json.get("speech_patterns", []),
                "topics": host1_json.get("topics", [])
            }
            host2_data = {
                "name": host2_json["name"],
                "background": host2_json.get("background", ""),
                "speech_patterns": host2_json.get("speech_patterns", []),
                "topics": host2_json.get("topics", [])
            }

            if "error" in host1_data:
                st.error(f"Error analyzing {host1_data['name']}'s personality: {host1_data['error']}")
                host1_data = None

            if "error" in host2_data:
                st.error(f"Error analyzing {host2_data['name']}'s personality: {host2_data['error']}")
                host2_data = None

            st.session_state.host1_data = host1_data
            st.session_state.host2_data = host2_data

            if not host1_data or not host2_data:
                st.error("Personality analysis failed. Please try again with different text samples.")
                script = None
            else:
                logging.info("Personality analysis completed successfully.")

            st.session_state.final_host1_name = host1_data["name"]
            st.session_state.final_host2_name = host2_data["name"]

            spinner_text = "🧠 Generating podcast script..."
            if selected_mode != "None":
                spinner_text = f"🧠 Generating podcast script with {selected_mode}..."
            with st.spinner(spinner_text):
                try:
                    host_leaves = False
                    if selected_mode == "🥊 Fight" and random.random() < 0.5:
                        host_leaves = True
                        logging.info("Fight Mode: A host will leave the episode.")

                    fight_mode = selected_mode == "🥊 Fight"
                    qa_mode = selected_mode == "❓ Q&A"
                    flirt_mode = selected_mode == "💘 Flirt"
                    ad_mode = selected_mode == "💰 Ad"
                    
                    # Initialize script variable
                    script = None
                    
                    # Generate the script
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
                        script = None
                    else:
                        logging.info("Script generated successfully.")
                        st.success("Script generation complete!")

                        # Ensure script has proper dialogue format
                        lines = script.split('\n')
                        formatted_lines = []
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue
                            # Skip the title line
                            if line.upper().startswith("EPISODE TITLE:"):
                                formatted_lines.append(line)
                                continue
                            # Ensure each dialogue line starts with a speaker name and colon
                            if not any(line.startswith(f"{host1_data['name']}:") or line.startswith(f"{host2_data['name']}:") for line in lines):
                                # Add speaker names if missing
                                if len(formatted_lines) % 2 == 0:
                                    formatted_lines.append(f"{host1_data['name']}: {line}")
                                else:
                                    formatted_lines.append(f"{host2_data['name']}: {line}")
                            else:
                                formatted_lines.append(line)

                        script = '\n'.join(formatted_lines)
                        episode_title = extract_title(script)
                        display_script = script
                        if script.split("\n")[0].strip().upper().startswith("EPISODE TITLE:"):
                            display_script = "\n".join(script.split("\n")[1:]).strip()

                        st.session_state.script = script
                        st.session_state.display_script = display_script
                        st.session_state.episode_title = episode_title

                except Exception as e:
                    logging.error(f"Exception during script generation: {e}", exc_info=True)
                    st.error(f"An unexpected error occurred during script generation: {e}")
                    script = None

            st.session_state.generation_complete = True

    # --- Display Current Results Section (if generation completed in this run or previous) ---
    if st.session_state.generation_complete and 'display_script' in st.session_state and 'episode_title' in st.session_state:
        st.markdown("---")
        current_host1 = st.session_state.get('final_host1_name', "Host 1")
        current_host2 = st.session_state.get('final_host2_name', "Host 2")
        # --- Show only title, description, and transcript ---
        st.subheader("EPISODE TITLE")
        st.markdown(f'<div class="episode-title"><h2>{st.session_state.episode_title}</h2></div>', unsafe_allow_html=True)

        description = f"In this explosive episode, {current_host1} and {current_host2} dive deep into a heated discussion that will leave you questioning everything you thought you knew. With {current_host1}'s unique perspective and {current_host2}'s sharp insights, this conversation takes unexpected turns that you won't want to miss. Whether you're a long-time listener or new to the show, this episode promises to be one of the most memorable yet. Tune in for a conversation that's as entertaining as it is thought-provoking."
        st.markdown("### EPISODE DESCRIPTION")
        st.markdown(f'<div class="episode-description">{description}</div>', unsafe_allow_html=True)

        st.subheader("PODCAST SCRIPT")
        formatted_script_html = format_script(st.session_state.display_script, current_host1, current_host2)
        st.markdown(formatted_script_html, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown('<div style="text-align:center; margin: 2rem 0; font-size:1.1rem; color:#FF1493;"><b>© 2025 PodCraft LLC</b></div>', unsafe_allow_html=True)

# --- Artwork Tab ---
with tab_artwork:
    st.subheader("Episode Artwork")
    episode_title = st.session_state.get('episode_title', None)
    script = st.session_state.get('script', None)
    host1_name = st.session_state.get('final_host1_name', None)
    host2_name = st.session_state.get('final_host2_name', None)

    if not episode_title or not script or not host1_name or not host2_name:
        st.info("Please generate a podcast episode first to create artwork.")
    else:
        st.markdown(f"<span style='color: #FF1493'><b>Episode Title:</b></span> {episode_title}", unsafe_allow_html=True)
        
        # Check for existing host photos
        host1_photo_path = os.path.join(PERSONALITY_DIR, "photos", f"{host1_name}.jpg")
        host2_photo_path = os.path.join(PERSONALITY_DIR, "photos", f"{host2_name}.jpg")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"<span style='color: #FF1493'><b>{host1_name}'s Photo:</b></span>", unsafe_allow_html=True)
            if os.path.exists(host1_photo_path):
                st.markdown("""
                    <div style='width: 100px; height: 100px; overflow: hidden; border-radius: 4px; margin-bottom: 0.5rem;'>
                        <img src='data:image/jpeg;base64,{}' style='width: 100%; height: 100%; object-fit: cover;' />
                    </div>
                """.format(base64.b64encode(open(host1_photo_path, 'rb').read()).decode()), unsafe_allow_html=True)
            else:
                st.markdown(f"<span style='color: #aaa'><i>No photo available for {host1_name}</i></span>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<span style='color: #FF1493'><b>{host2_name}'s Photo:</b></span>", unsafe_allow_html=True)
            if os.path.exists(host2_photo_path):
                st.markdown("""
                    <div style='width: 100px; height: 100px; overflow: hidden; border-radius: 4px; margin-bottom: 0.5rem;'>
                        <img src='data:image/jpeg;base64,{}' style='width: 100%; height: 100%; object-fit: cover;' />
                    </div>
                """.format(base64.b64encode(open(host2_photo_path, 'rb').read()).decode()), unsafe_allow_html=True)
            else:
                st.markdown(f"<span style='color: #aaa'><i>No photo available for {host2_name}</i></span>", unsafe_allow_html=True)

        # Artwork style selection
        style_options = ["Realistic", "Cartoon", "Abstract", "Minimalist", "Vintage"]
        selected_style = st.radio(
            "Artwork Style:",
            style_options,
            horizontal=True,
            key="artwork_style_radio"
        )

        # Generate artwork button
        if st.button("Generate Artwork", key="generate_artwork_button"):
            if not artwork_generator:
                st.error("Artwork generation not available. Please check your OpenAI API key.")
            else:
                with st.spinner("Generating artwork..."):
                    try:
                        # Generate artwork based on episode content and settings
                        artwork_path = artwork_generator.generate_artwork(
                            title=episode_title,
                            topic=script,
                            host1_name=host1_name,
                            host2_name=host2_name,
                            style=selected_style,
                            host1_photo_path=host1_photo_path if os.path.exists(host1_photo_path) else None,
                            host2_photo_path=host2_photo_path if os.path.exists(host2_photo_path) else None
                        )
                        
                        if artwork_path and os.path.exists(artwork_path):
                            st.session_state.artwork_path = artwork_path
                            # Store artwork bytes in session state
                            with open(artwork_path, "rb") as f:
                                st.session_state.artwork_bytes = f.read()
                            st.success("Artwork generated successfully!")
                            
                            # Display artwork
                            col1, col2, col3 = st.columns([1,2,1])
                            with col2:
                                st.image(st.session_state.artwork_bytes, width=300)
                                
                                # Add download button using session state
                                st.download_button(
                                    label="Download Artwork",
                                    data=st.session_state.artwork_bytes,
                                    file_name=f"{get_safe_filename(episode_title)}_artwork.png",
                                    mime="image/png"
                                )
                        else:
                            st.error("Failed to generate artwork.")
                    except Exception as e:
                        logging.error(f"Error generating artwork: {e}", exc_info=True)
                        st.error(f"An error occurred while generating artwork: {str(e)}")

    st.markdown('<div style="text-align:center; margin: 2rem 0; font-size:1.1rem; color:#FF1493;"><b>© 2025 PodCraft LLC</b></div>', unsafe_allow_html=True)

# --- Audio Tab ---
with tab_audio:
    st.subheader("Audio Generation")
    # Get the most recent episode title and script
    episode_title = st.session_state.get('episode_title', None)
    script = st.session_state.get('script', None)

    if episode_title:
        st.markdown(f"<span style='color: #FF1493'><b>Episode Title:</b></span> {episode_title}", unsafe_allow_html=True)
    else:
        st.info("No episode generated yet.")
    if script:
        # Estimate length and cost
        words = len(script.split())
        avg_wpm = 150
        minutes = words / avg_wpm
        seconds = int(minutes * 60)
        char_count = len(script)
        # ElevenLabs: 1 credit = 1000 characters
        credits = char_count / 1000
        st.markdown(f"<span style='color: #FF1493'><b>Estimated Audio Length:</b></span> {minutes:.1f} minutes ({char_count} characters)", unsafe_allow_html=True)
        st.markdown(f"<span style='color: #FF1493'><b>Estimated ElevenLabs Cost:</b></span> {credits:.2f} credits ≈ ${credits * 0.15:.2f}", unsafe_allow_html=True)
        
        if st.button("Generate Audio"):
            if not voice_synth:
                st.error("Voice synthesis not available. Please check your ElevenLabs API key.")
            else:
                with st.spinner("Generating audio..."):
                    try:
                        # Get host voice IDs
                        host1_voice_id = None
                        host2_voice_id = None
                        for p in st.session_state.get('personalities', []):
                            if p['name'] == st.session_state.get('final_host1_name'):
                                host1_voice_id = p.get('voice_id')
                            if p['name'] == st.session_state.get('final_host2_name'):
                                host2_voice_id = p.get('voice_id')
                        
                        if not host1_voice_id or not host2_voice_id:
                            st.error("Could not find voice IDs for both hosts. Please ensure both hosts have valid voice IDs in their personality profiles.")
                        else:
                            # Generate audio
                            audio_path = voice_synth.generate_audio(
                                script,
                                st.session_state.get('final_host1_name'),
                                st.session_state.get('final_host2_name'),
                                voice1_id=host1_voice_id,
                                voice2_id=host2_voice_id
                            )
                            
                            if audio_path and os.path.exists(audio_path):
                                st.session_state.audio_path = audio_path
                                st.success("Audio generated successfully!")
                                
                                # Display audio player using file path
                                st.audio(audio_path, format="audio/mp3")
                                
                                # Add download button reading file only when needed
                                with open(audio_path, "rb") as f:
                                    audio_bytes = f.read()
                                st.download_button(
                                    label="Download Audio",
                                    data=audio_bytes,
                                    file_name=f"{get_safe_filename(episode_title)}.mp3",
                                    mime="audio/mp3"
                                )
                            else:
                                st.error("Failed to generate audio file.")
                    except Exception as e:
                        logging.error(f"Error generating audio: {e}", exc_info=True)
                        st.error(f"An error occurred while generating audio: {str(e)}")
    else:
        st.info("No script available to estimate audio length or cost.")

# --- RSS Upload Tab ---
with tab_rss:
    st.subheader("RSS Upload")
    st.info("🎙️ RSS feed upload functionality coming soon! Stay tuned for updates.")
    st.markdown('<div style="text-align:center; margin: 2rem 0; font-size:1.1rem; color:#FF1493;"><b>© 2025 PodCraft LLC</b></div>', unsafe_allow_html=True)

