import os
import logging
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, BadRequestError # Import specific errors, including BadRequestError
import re
import json # Import json

class PersonalityAnalyzer:
    """
    Analyzes text samples to extract personality traits, speech patterns, and topic interests
    using an LLM (like GPT-4o).
    """
    def __init__(self, openai_api_key=None):
        """
        Initializes the PersonalityAnalyzer with the provided OpenAI API key.
        Cleans the model name read from environment variables. # MODIFIED
        """
        if not openai_api_key:
            raise ValueError("OpenAI API key is required")

        self.client = OpenAI(api_key=openai_api_key)

        # Get model name from environment variable, default to 'gpt-4o' if not set
        # Clean the model name: remove comments and strip whitespace # MODIFIED
        raw_model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
        # --- Robust Cleaning ---
        # 1. Split at the first '#'
        model_name_no_comment = raw_model_name.split('#', 1)[0]
        # 2. Strip whitespace from the result
        self.model_name = model_name_no_comment.strip()
        # --- End Robust Cleaning ---

        # Log the cleaned model name # MODIFIED
        logging.info(f"PersonalityAnalyzer initialized with cleaned model name: '{self.model_name}'")


    def analyze_personality(self, name, text_sample):
        """
        Analyzes text sample to extract key personality traits, speech patterns, and topics.
        Uses the cleaned model name. # MODIFIED

        Parameters:
        ----------
        name : str
            The name of the personality being analyzed
        text_sample : str
            Text sample representing the personality (transcripts, writings, etc.)

        Returns:
        -------
        dict
            Dictionary with personality analysis results or error message
        """
        if not text_sample or len(text_sample.strip()) < 50:
            return {
                "error": "Text sample is too short for meaningful analysis. Please provide a longer sample."
            }

        # Trim text sample if it's too long to avoid token limitations
        max_length = 15000  # Approximately 3750 tokens
        if len(text_sample) > max_length:
            logging.info(f"Trimming text sample for {name} from {len(text_sample)} to {max_length} characters")
            text_sample = text_sample[:max_length] + "..."

        system_prompt = f"""
        You are an expert at analyzing linguistic patterns and extracting personality traits from text samples.
        Analyze the provided text sample for a personality named {name} and extract the following:

        1. A background description (3-4 sentences about their communication style, expertise areas, and approach)
        2. 10 common speech patterns or phrases they might use (exact phrases, not descriptions)
        3. 10 topics they frequently reference or are knowledgeable about

        Format your response as a JSON object with these keys:
        - "background": String with 3-4 sentences of background description
        - "speech_patterns": Array of 10 strings representing common phrases or expressions
        - "topics": Array of 10 strings representing frequent topics

        Ensure your analysis captures their authentic voice, interests, and communication style.
        """

        # Construct messages list
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text_sample}
        ]

        # Add explicit log to check the exact model string # NEW
        logging.info(f"--- analyze_personality using model: |{self.model_name}| ---")

        try:
            logging.debug(f"Sending personality analysis request to OpenAI for {name} with cleaned model '{self.model_name}'")
            # logging.debug(f"System Prompt: {system_prompt[:200]}...") # Log beginning of system prompt if needed
            # logging.debug(f"User Content Sample: {text_sample[:200]}...") # Log beginning of user content if needed

            completion = self.client.chat.completions.create(
                model=self.model_name, # Use cleaned model name
                temperature=0.7,
                response_format={"type": "json_object"},
                messages=messages
            )

            response = completion.choices[0].message.content

            # Parse JSON response
            try:
                personality_data = json.loads(response)
                # Validate structure
                if not all(k in personality_data for k in ["background", "speech_patterns", "topics"]):
                    logging.error(f"Missing required fields in personality analysis for {name}. Response: {response}") # Log response
                    return {
                        "error": "Invalid personality analysis result. Missing required fields."
                    }

                # Ensure lists have exactly 10 items
                if len(personality_data.get("speech_patterns", [])) != 10 or len(personality_data.get("topics", [])) != 10:
                    logging.warning(f"Unexpected number of items in personality analysis for {name}. Adjusting...")
                    # Adjust to exactly 10 items, handle potential missing keys gracefully
                    patterns = personality_data.get("speech_patterns", [])[:10]
                    topics = personality_data.get("topics", [])[:10]

                    # If we have fewer than 10, pad with generic items
                    while len(patterns) < 10:
                        patterns.append(f"As I always say")
                    while len(topics) < 10:
                        topics.append("general observations")

                    personality_data["speech_patterns"] = patterns
                    personality_data["topics"] = topics

                return personality_data

            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse JSON from personality analysis: {e}. Response: {response}") # Log the raw response
                # Attempt to extract the data using regex if JSON parsing fails
                return self._extract_fallback(response, name)

        except APIError as e:
            logging.error(f"OpenAI API returned an API Error during personality analysis for {name}: {e}", exc_info=True)
            return {"error": f"OpenAI API Error: {e}"}
        except APIConnectionError as e:
            logging.error(f"Failed to connect to OpenAI API during personality analysis for {name}: {e}", exc_info=True)
            return {"error": f"OpenAI Connection Error: {e}"}
        except RateLimitError as e:
            logging.error(f"OpenAI API request exceeded rate limit during personality analysis for {name}: {e}", exc_info=True)
            return {"error": f"OpenAI Rate Limit Error: {e}"}
        except BadRequestError as e: # Catch BadRequestError specifically
            logging.error(f"OpenAI API returned a BadRequestError (Code: {e.code}) during personality analysis for {name}. Model sent: |{self.model_name}|. Error: {e}", exc_info=True)
            return {"error": f"OpenAI Bad Request Error: {e}"}
        except Exception as e:
            logging.error(f"Unexpected error in personality analysis for {name}: {str(e)}", exc_info=True) # Log traceback
            return {
                "error": f"Failed to analyze personality: {str(e)}"
            }

    def _extract_fallback(self, text, name):
        """Fallback method to extract personality data using regex if JSON parsing fails"""
        logging.info(f"Using fallback extraction for {name}'s personality data")

        # Initialize with default values
        personality_data = {
            "background": f"{name} is a thoughtful communicator with a unique perspective.",
            "speech_patterns": [f"As {name}, I think", "I believe", "In my experience",
                               "Let me explain", "The way I see it", "To be honest",
                               "Here's the thing", "I'd say that", "Let's be real",
                               "What's interesting is"],
            "topics": ["personal experiences", "observations", "analysis", "opinions",
                      "perspectives", "ideas", "concepts", "theories", "examples",
                      "general knowledge"]
        }

        # Try to extract background
        background_match = re.search(r'"background"\s*:\s*"([^"]+)"', text)
        if background_match:
            personality_data["background"] = background_match.group(1).strip() # Add strip

        # Try to extract speech patterns
        patterns_match = re.search(r'"speech_patterns"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if patterns_match:
            patterns_text = patterns_match.group(1)
            patterns = [p.strip() for p in re.findall(r'"([^"]+)"', patterns_text)] # Add strip
            if patterns and len(patterns) > 0:
                personality_data["speech_patterns"] = patterns[:10]

        # Try to extract topics
        topics_match = re.search(r'"topics"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if topics_match:
            topics_text = topics_match.group(1)
            topics = [t.strip() for t in re.findall(r'"([^"]+)"', topics_text)] # Add strip
            if topics and len(topics) > 0:
                personality_data["topics"] = topics[:10]

        # Pad if necessary after fallback extraction
        while len(personality_data["speech_patterns"]) < 10:
            personality_data["speech_patterns"].append(f"As I always say")
        while len(personality_data["topics"]) < 10:
            personality_data["topics"].append("general observations")

        return personality_data


    def analyze_personalities_from_files(self, file_paths):
        """
        Analyzes personalities from text files.

        Parameters:
        ----------
        file_paths : dict
            Dictionary with keys as personality names and values as file paths

        Returns:
        -------
        dict
            Dictionary with personality analysis results
        """
        results = {}

        for name, path in file_paths.items():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read()
                results[name] = self.analyze_personality(name, text)
            except FileNotFoundError: # Specific error for file not found
                logging.error(f"File not found for {name}: {path}")
                results[name] = {"error": f"File not found: {path}"}
            except Exception as e:
                logging.error(f"Error reading or analyzing file for {name} at {path}: {str(e)}", exc_info=True)
                results[name] = {
                    "error": f"Failed to analyze personality from file {path}: {str(e)}"
                }

        return results