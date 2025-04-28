import os
import openai
from openai import OpenAI
import logging
import random # Import random for leaving chance

class GenAI:
    def __init__(self, openai_api_key=None):
        """
        Initializes the GenAI class with the provided OpenAI API key.
        Reads model configuration from environment variables and cleans it.
        """
        if not openai_api_key:
            raise ValueError("OpenAI API key is required")

        self.client = OpenAI(api_key=openai_api_key)

        # Get model name from environment variable, default to 'gpt-4o' if not set
        # Clean the model name: remove comments and strip whitespace
        raw_model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
        # --- Robust Cleaning ---
        # 1. Split at the first '#'
        model_name_no_comment = raw_model_name.split('#', 1)[0]
        # 2. Strip whitespace from the result
        self.model_name = model_name_no_comment.strip()
        # --- End Robust Cleaning ---


        # Log the cleaned model name
        logging.info(f"GenAI initialized with cleaned model name: '{self.model_name}'")


    def generate_text(self, prompt, instructions='You are a helpful AI', temperature=1):
        """
        Generates a text completion using the OpenAI API.
        Uses the cleaned model name.
        """
        # Add logging before the API call for debugging
        logging.debug(f"Calling OpenAI chat completion with model: '{self.model_name}'")
        # Add explicit log to check the exact model string # NEW
        logging.info(f"--- generate_text using model: |{self.model_name}| ---")
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name, # Use cleaned model name
                temperature=temperature,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": prompt}
                ]
            )
            response = completion.choices[0].message.content
            return response
        except Exception as e: # Catch potential errors during API call
            logging.error(f"OpenAI API call failed in generate_text: {e}", exc_info=True)
            return f"Error during OpenAI API call: {e}"


    def generate_dynamic_podcast_script(self, topic, host1_data, host2_data, format_type="text", length="short", fight_mode=False, host_leaves=False, qa_mode=False, flirt_mode=False, ad_mode=False):
        """
        Generates a podcast script with dynamic personalities and sound effects.

        Parameters:
        ----------
        topic : str
            The topic to discuss
        host1_data : dict
            Personality data for the first host
        host2_data : dict
            Personality data for the second host
        format_type : str
            The format of the input (text, url, image)
        length : str
            Desired length of the podcast (short, medium, long)
        fight_mode : bool
            Whether to generate a high-conflict script
        host_leaves : bool
            Whether a host should leave during the episode
        qa_mode : bool
            Whether to include audience Q&A in the second half
        flirt_mode : bool
            Whether to include subtle romantic tension
        ad_mode : bool
            Whether to include a personality-appropriate ad read
        """
        try:
            # Determine length parameters
            length_params = {
                "super_short": "30 seconds",
                "short": "3-5 minutes",
                "medium": "5-10 minutes",
                "long": "10-15 minutes"
            }
            target_length = length_params.get(length, "3-5 minutes")

            # Construct system prompt
            system_prompt = f"""You are a podcast script generator. Create a natural, engaging conversation between two hosts for a podcast episode.

Host 1 ({host1_data['name']}):
- Background: {host1_data['background']}
- Speaking Style: {', '.join(host1_data['speech_patterns'][:5])}
- Common Topics: {', '.join(host1_data['topics'][:5])}

Host 2 ({host2_data['name']}):
- Background: {host2_data['background']}
- Speaking Style: {', '.join(host2_data['speech_patterns'][:5])}
- Common Topics: {', '.join(host2_data['topics'][:5])}

Format the script with the following rules:
1. Start with "EPISODE TITLE: [create an engaging, specific title that reflects the topic and promises value to listeners]"
2. After the title, begin the dialogue with each line starting with the speaker's name followed by a colon
3. Use exactly these names: "{host1_data['name']}:" and "{host2_data['name']}:"
4. No parentheses or additional labels
5. Do not include any sound effects or stage directions
6. Each speaker's dialogue should be on its own line
7. Keep responses concise and natural
8. Create natural back-and-forth dialogue
9. Maintain distinct personalities throughout

The episode should be approximately {target_length} long.

{f'Include a Q&A segment in the second half where the hosts answer 2-3 audience questions related to the topic.' if qa_mode else ''}
{f'Include subtle romantic tension that builds throughout the episode, with the hosts showing increasing interest in each other.' if flirt_mode else ''}
{f'Include a natural ad read in the middle of the episode that fits the hosts\' personalities and the topic.' if ad_mode else ''}
{f'Make the conversation more confrontational with less respect between hosts.' if fight_mode else ''}
{f'Have {host1_data["name"]} leave the episode dramatically about 2/3 through.' if host_leaves else ''}

The topic is: {topic}
"""

            # Generate the script
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate a podcast script about {topic}. Create a specific, engaging title that reflects the topic and promises value to listeners."}
                ],
                temperature=0.7,
                max_tokens=2000
            )

            script = response.choices[0].message.content.strip()
            
            # Verify the script format
            if not any(line.startswith((f"{host1_data['name']}:", f"{host2_data['name']}:")) for line in script.split('\n')):
                logging.error("Generated script does not contain proper dialogue format")
                logging.error(f"Script content: {script}")
                return "Error: Script format invalid - missing dialogue lines"
            
            logging.info("Script generated successfully")
            return script

        except Exception as e:
            logging.error(f"Error generating script: {e}", exc_info=True)
            return f"Error generating script: {str(e)}"

    def generate_podcast_script(self, topic, format_type, length, fight_mode=False, host_leaves=False, qa_mode=False, flirt_mode=False, ad_mode=False):
        """
        Generates a podcast script using the specified parameters.
        
        Parameters:
        ----------
        topic : str
            The topic to discuss
        format_type : str
            The format of the input (text, url, or image)
        length : str
            The desired length of the podcast (short, medium, or long)
        fight_mode : bool
            Whether to generate a high-conflict script
        host_leaves : bool
            Whether a host should leave during the episode
        qa_mode : bool
            Whether to include audience Q&A in the second half
        flirt_mode : bool
            Whether to include subtle romantic tension
        ad_mode : bool
            Whether to include a personality-appropriate ad read
        """
        try:
            # Determine length parameters
            length_params = {
                "super_short": "30 seconds",
                "short": "3-5 minutes",
                "medium": "5-10 minutes",
                "long": "10-15 minutes"
            }
            target_length = length_params.get(length, "3-5 minutes")

            # Construct system prompt
            system_prompt = f"""You are a podcast script generator. Create a natural, engaging conversation between Joe Rogan and Alex Cooper for a podcast episode.

Format the script with the following rules:
1. Start with "EPISODE TITLE: [create an engaging, specific title that reflects the topic and promises value to listeners]"
2. After the title, begin the dialogue with each line starting with the speaker's name followed by a colon
3. Use exactly these names: "Joe Rogan:" and "Alex Cooper:"
4. No parentheses or additional labels
5. No sound effects or stage directions
6. Each speaker's dialogue should be on its own line
7. Keep responses concise and natural
8. Create natural back-and-forth dialogue
9. Maintain distinct personalities throughout

The episode should be approximately {target_length} long.

{f'Include a Q&A segment in the second half where the hosts answer 2-3 audience questions related to the topic.' if qa_mode else ''}
{f'Include subtle romantic tension that builds throughout the episode, with the hosts showing increasing interest in each other.' if flirt_mode else ''}
{f'Include a natural ad read in the middle of the episode that fits the hosts\' personalities and the topic.' if ad_mode else ''}
{f'Make the conversation more confrontational with less respect between hosts.' if fight_mode else ''}
{f'Have Joe Rogan leave the episode dramatically about 2/3 through.' if host_leaves else ''}

The topic is: {topic}
"""

            # Generate the script
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate a podcast script about {topic}. Create a specific, engaging title that reflects the topic and promises value to listeners."}
                ],
                temperature=0.7,
                max_tokens=2000
            )

            script = response.choices[0].message.content.strip()
            
            # Verify the script format
            if not any(line.startswith(("Joe Rogan:", "Alex Cooper:")) for line in script.split('\n')):
                logging.error("Generated script does not contain proper dialogue format")
                logging.error(f"Script content: {script}")
                return "Error: Script format invalid - missing dialogue lines"
            
            logging.info("Script generated successfully")
            return script

        except Exception as e:
            logging.error(f"Error generating script: {e}", exc_info=True)
            return f"Error generating script: {str(e)}"
