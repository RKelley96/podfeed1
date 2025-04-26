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
                "short": "3-5 minutes",
                "medium": "5-10 minutes",
                "long": "10-15 minutes"
            }
            target_length = length_params.get(length, "3-5 minutes")

            # Add sound effect instructions to system prompt
            sfx_instructions = """
            You may include sound effects in the script using square brackets, but use them EXTREMELY SPARINGLY and only for truly dramatic moments. Available sound effects:
            - [door slam] - ONLY when a host dramatically storms out (max once per episode)
            - [applause] - ONLY for major breakthroughs or shocking revelations
            - [laugh] - ONLY for the absolute funniest punchline of the episode
            - [drum roll] - ONLY before the biggest reveal or announcement
            - [suspense] - ONLY for major cliffhangers before commercial breaks
            - [fight] - ONLY for actual physical altercations in fight mode
            - [exit] - ONLY when a host permanently leaves the show
            - [mic drop] - ONLY for the absolute final line of the episode

            STRICT Guidelines:
            1. Use sound effects VERY sparingly - ideally just 1-2 per episode
            2. Never use more than one sound effect in any 5-minute segment
            3. Only use sound effects at natural break points in the conversation
            4. Make sure the dialogue naturally builds up to the sound effect
            5. Never use sound effects in the first 2 minutes of the episode
            6. Never use sound effects in the last 30 seconds (except [mic drop])
            7. Always leave at least 2 minutes between sound effects
            8. Never use [applause] and [laugh] in the same episode
            9. Only use [door slam] in fight mode or when a host leaves
            10. [mic drop] must be the very last thing in the episode

            Example of good usage (sparse and impactful):
            "After months of investigation, I can finally reveal... [drum roll] The truth about the missing files!"

            Example of bad usage (overused):
            "That's hilarious! [laugh] Anyway, let me tell you about... [drum roll] The time I... [applause]"
            """

            # Construct system prompt with personality data
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
1. Start each line with the speaker's name followed by a colon
2. No parentheses or additional labels
3. No sound effects or stage directions
4. Each speaker's dialogue should be on its own line
5. Keep responses concise and natural
6. Create natural back-and-forth dialogue
7. Maintain distinct personalities throughout

The episode should be approximately {target_length} long.

{f'Include a Q&A segment in the second half where the hosts answer 2-3 audience questions related to the topic.' if qa_mode else ''}
{f'Include subtle romantic tension that builds throughout the episode, with the hosts showing increasing interest in each other.' if flirt_mode else ''}
{f'Include a natural ad read in the middle of the episode that fits the hosts\' personalities and the topic.' if ad_mode else ''}
{f'Make the conversation more confrontational with less respect between hosts.' if fight_mode else ''}
{f'Have {host1_data["name"]} leave the episode dramatically about 2/3 through.' if host_leaves else ''}

The topic is: {topic}

{sfx_instructions}
"""

            # Generate the script
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Generate the podcast script."}
                ],
                temperature=0.7,
                max_tokens=2000
            )

            script = response.choices[0].message.content.strip()
            logging.info("Script generated successfully")
            return script

        except Exception as e:
            logging.error(f"Error generating script: {e}", exc_info=True)
            return f"Error generating script: {str(e)}"

    def generate_podcast_script(self, topic, format_type="text", length="medium", fight_mode=False, host_leaves=False, qa_mode=False, flirt_mode=False, ad_mode=False):
        """
        Legacy method for backwards compatibility - uses hardcoded Joe Rogan and Alex Cooper personalities.
        Passes fight_mode, host_leaves, qa_mode, flirt_mode, and ad_mode flags to the dynamic generator.

        For new dynamic personality support, use generate_dynamic_podcast_script instead.
        """
        logging.warning("Using legacy podcast script generation with hardcoded personalities")

        # Import the original personality data
        try:
            from joealex_data import JOE_ROGAN_PERSONALITY, ALEX_COOPER_PERSONALITY

            # Create host data structures for compatibility with new method
            joe_data = {
                "name": "Joe Rogan",
                "background": JOE_ROGAN_PERSONALITY["background"],
                "speech_patterns": JOE_ROGAN_PERSONALITY["speech_patterns"],
                "topics": JOE_ROGAN_PERSONALITY["topics"]
            }

            alex_data = {
                "name": "Alex Cooper",
                "background": ALEX_COOPER_PERSONALITY["background"],
                "speech_patterns": ALEX_COOPER_PERSONALITY["speech_patterns"],
                "topics": ALEX_COOPER_PERSONALITY["topics"]
            }

            # Call the new dynamic method with the legacy data AND all mode flags
            return self.generate_dynamic_podcast_script(
                topic,
                joe_data,
                alex_data,
                format_type,
                length,
                fight_mode=fight_mode,
                host_leaves=host_leaves,
                qa_mode=qa_mode,
                flirt_mode=flirt_mode,
                ad_mode=ad_mode
            )

        except ImportError:
            # If personality_data.py is removed, use minimal default personalities
            logging.error("personality_data.py not found, using minimal default personalities")

            joe_data = {
                "name": "Joe Rogan",
                "background": "Joe Rogan is a comedian, podcast host, and UFC commentator known for his conversational interview style and wide-ranging interests.",
                "speech_patterns": ["It's entirely possible that", "A hundred percent", "That's crazy, man",
                                   "Have you ever tried", "What's interesting about that is",
                                   "I was just talking to someone about this", "The thing is",
                                   "Here's the deal", "Listen", "I've been saying this for years"],
                "topics": ["martial arts", "hunting", "comedy", "fitness", "psychedelics",
                          "wildlife", "technology", "free speech", "comedy", "conspiracy theories"]
            }

            alex_data = {
                "name": "Alex Cooper",
                "background": "Alex Cooper is the host of the popular podcast 'Call Her Daddy' where she discusses relationships, sex, and social dynamics with a focus on female empowerment.",
                "speech_patterns": ["I'm literally obsessed with", "That's so toxic", "It's giving...",
                                   "Let me just say", "I'm actually dead", "So here's the situation",
                                   "That's the energy we need", "It's the vibe for me",
                                   "Stop, that's insane", "The daddy gang knows"],
                "topics": ["dating strategies", "female empowerment", "social media", "mental health",
                          "celebrity gossip", "career development", "friendship", "personal growth",
                          "dating apps", "relationships"]
            }

            # Call the dynamic method with the default data AND the fight mode flags
            return self.generate_dynamic_podcast_script(
                topic,
                joe_data,
                alex_data,
                format_type,
                length,
                fight_mode=fight_mode, # Pass flag
                host_leaves=host_leaves, # Pass flag
                qa_mode=qa_mode,
                flirt_mode=flirt_mode,
                ad_mode=ad_mode
            )
