import os
import xml.etree.ElementTree as ET
from datetime import datetime
import logging
from urllib.parse import quote

class RssFeedManager:
    def __init__(self, github_username, repo_name, branch="main"):
        """
        Initialize the RSS feed manager with GitHub Pages configuration.
        
        Parameters:
        ----------
        github_username : str
            Your GitHub username
        repo_name : str
            Name of your podcast repository
        branch : str
            Branch used for GitHub Pages (default: "main")
        """
        self.base_url = f"https://{github_username}.github.io/{repo_name}"
        self.feed_path = "output/feed.xml"
        self.episodes_dir = "output"
        self.itunes_ns = "http://www.itunes.com/dtds/podcast-1.0.dtd"
        
        # Register iTunes namespace
        ET.register_namespace('itunes', self.itunes_ns)
        
        logging.info(f"RSS Feed Manager initialized with base URL: {self.base_url}")

    def _ensure_feed_exists(self):
        """Ensure the RSS feed file exists with basic structure."""
        if not os.path.exists(self.feed_path):
            root = ET.Element('rss', version='2.0')
            root.set(f'xmlns:{self.itunes_ns.split("/")[-2]}', self.itunes_ns)
            
            channel = ET.SubElement(root, 'channel')
            ET.SubElement(channel, 'title').text = "CALL HIM DADDY, JOE"
            ET.SubElement(channel, 'link').text = self.base_url
            ET.SubElement(channel, 'description').text = "Custom podcast episodes generated with AI"
            ET.SubElement(channel, 'language').text = "en-us"
            
            # iTunes-specific tags
            ET.SubElement(channel, f'{{{self.itunes_ns}}}author').text = "PodCraft LLC"
            ET.SubElement(channel, f'{{{self.itunes_ns}}}summary').text = "AI-generated podcast episodes featuring dynamic conversations on various topics."
            ET.SubElement(channel, f'{{{self.itunes_ns}}}explicit').text = "yes"
            ET.SubElement(channel, f'{{{self.itunes_ns}}}category', text="Society & Culture")
            ET.SubElement(channel, f'{{{self.itunes_ns}}}owner').text = "PodCraft LLC"
            
            tree = ET.ElementTree(root)
            tree.write(self.feed_path, encoding='utf-8', xml_declaration=True)
            logging.info("Created new RSS feed file")

    def add_episode(self, episode_data):
        """
        Add a new episode to the RSS feed.
        
        Parameters:
        ----------
        episode_data : dict
            Dictionary containing episode information:
            - title: Episode title
            - description: Episode description
            - audio_file: Local path to audio file
            - artwork_file: Local path to artwork file
            - duration: Audio duration in HH:MM:SS format
        """
        try:
            self._ensure_feed_exists()
            
            # Parse existing feed
            tree = ET.parse(self.feed_path)
            root = tree.getroot()
            channel = root.find('channel')
            
            # Create new episode item
            item = ET.SubElement(channel, 'item')
            
            # Basic episode info
            ET.SubElement(item, 'title').text = episode_data['title']
            ET.SubElement(item, 'description').text = episode_data['description']
            ET.SubElement(item, 'pubDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
            ET.SubElement(item, 'guid', isPermaLink="false").text = f"episode-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Audio file
            audio_filename = os.path.basename(episode_data['audio_file'])
            audio_url = f"{self.base_url}/{self.episodes_dir}/{quote(audio_filename)}"
            ET.SubElement(item, 'enclosure', 
                         url=audio_url,
                         type="audio/mpeg",
                         length=str(os.path.getsize(episode_data['audio_file'])))
            
            # iTunes-specific tags
            ET.SubElement(item, f'{{{self.itunes_ns}}}title').text = episode_data['title']
            ET.SubElement(item, f'{{{self.itunes_ns}}}summary').text = episode_data['description']
            ET.SubElement(item, f'{{{self.itunes_ns}}}duration').text = episode_data.get('duration', '00:30:00')
            ET.SubElement(item, f'{{{self.itunes_ns}}}explicit').text = "yes"
            
            # Artwork
            if episode_data.get('artwork_file'):
                artwork_filename = os.path.basename(episode_data['artwork_file'])
                artwork_url = f"{self.base_url}/{self.episodes_dir}/{quote(artwork_filename)}"
                ET.SubElement(item, f'{{{self.itunes_ns}}}image').text = artwork_url
            
            # Save updated feed
            tree.write(self.feed_path, encoding='utf-8', xml_declaration=True)
            logging.info(f"Added episode '{episode_data['title']}' to RSS feed")
            
            return True
            
        except Exception as e:
            logging.error(f"Error adding episode to RSS feed: {e}", exc_info=True)
            return False

    def get_feed_url(self):
        """Get the public URL for the RSS feed."""
        return f"{self.base_url}/{self.feed_path}" 