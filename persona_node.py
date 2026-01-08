import os
import json
import re
import shutil
from openai import OpenAI
from .utils import load_prompt, robust_json_parse, normalize_json

# Define the directory for storing persona cards
PERSONA_DIR = os.path.join(os.path.dirname(__file__), "personas")
if not os.path.exists(PERSONA_DIR):
    os.makedirs(PERSONA_DIR)
PROMPTCONFIGS_DIR = os.path.join(os.path.dirname(__file__), "configs")
if not os.path.exists(PROMPTCONFIGS_DIR):
    os.makedirs(PROMPTCONFIGS_DIR)

# Constants
NEG_BASE = "modern, recent, old, oldest, cartoon, graphic, text, painting, crayon, graphite, abstract, glitch, deformed, mutated, ugly, disfigured, long body, lowres, bad anatomy, bad hands, missing fingers, extra digits, fewer digits, cropped, very displeasing, (worst quality, bad quality:1.2), bad anatomy, sketch, jpeg artifacts, signature, watermark, username, signature, simple background, conjoined, bad ai-generated"
POS_PREFIX = "masterpiece, best quality, amazing quality, 4k, very aesthetic, high resolution, ultra-detailed, absurdres, newest"
POS_SUFFIX = "depth of field, volumetric lighting"
MODE_CREATE_SMART = "Create New (Smart)"
MODE_FORCE_RESET = "Force Reset (Overwrite)"


class PersonaDirectorNode:
    def __init__(self):
        pass
    
    @classmethod
    def INPUT_TYPES(cls):
        # 1. Scan the directory for existing JSON files
        files = [f for f in os.listdir(PERSONA_DIR) if f.endswith(".json")]
        promptconfigfiles = [f for f in os.listdir(PROMPTCONFIGS_DIR) if f.endswith(".json")]
        # 2. Add the "Create New" option at the top
        selector_options = ["Create New (Smart)", "Force Reset (Overwrite)"] + files
        config_options = promptconfigfiles
        return {
            "required": {
                # [1] Persona Selector: Replaces the Mode switch
                "persona_selector": (selector_options, ),
                
                # [2] New Name: Only used when "Create New Persona" is selected
                "new_persona_name": ("STRING", {
                    "default": "New_Character", 
                    "multiline": False
                }),
                
                # [3] User Instruction: Handles both initial description and update commands
                "user_instruction": ("STRING", {
                    "multiline": True, 
                    "default": "A girl, white hair, blue eyes, wearing school uniform",
                    "placeholder": "Describe the character (if new) or the change (if existing)..."
                }),
                
                "promptconfig": (config_options, ),
                # [4] API Configuration
                "api_url": ("STRING", {"default": "","placeholder": "Leave empty to use config.json"}),
                "api_key": ("STRING", {"default": "","placeholder": "Leave empty to use config.json"}),
                "model_name": ("STRING", {"default": "","placeholder": "Leave empty to use config.json"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("positive_prompt", "negative_prompt", "debug_state")
    FUNCTION = "generate_prompt"
    CATEGORY = "Persona Director"

    def _sanitize_filename(self, name):
        """Sanitize user input to create a safe filename."""
        safe_name = re.sub(r'[^\w\-]', '_', name).strip('_')
        if not safe_name:
            safe_name = "New_Character"
        # Limit length to prevent filesystem issues
        return safe_name[:100]

    def _resolve_persona_state(self, persona_selector, new_persona_name):
        """
        Determine the target persona file and load existing state if applicable.
        
        Returns:
            tuple: (current_state_data, target_filename, is_new_creation, status_msg)
        """
        current_state_data = {}
        is_new_creation = False
        
        # Branch A: Create New or Force Reset
        if persona_selector in [MODE_CREATE_SMART, MODE_FORCE_RESET]:
            safe_name = self._sanitize_filename(new_persona_name)
            target_filename = f"{safe_name}.json"
            file_path = os.path.join(PERSONA_DIR, target_filename)

            if persona_selector == MODE_FORCE_RESET:
                is_new_creation = True
                status_msg = f"Reset Character: {target_filename}"
            else:
                # Smart Create: Check if file exists
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            current_state_data = json.load(f)
                        is_new_creation = False
                        status_msg = f"Smart Mode: Resuming existing {target_filename}"
                    except Exception as e:
                        # File corrupted -> Fallback to Create
                        is_new_creation = True
                        status_msg = f"Error reading file, resetting: {target_filename}"
                else:
                    is_new_creation = True
                    status_msg = f"Created New Character: {target_filename}"

        # Branch B: Select Existing File
        else:
            target_filename = persona_selector
            file_path = os.path.join(PERSONA_DIR, target_filename)
            is_new_creation = False
            status_msg = f"Loaded File: {target_filename}"

            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        current_state_data = json.load(f)
                except Exception as e:
                    raise RuntimeError(f"Read Error: {e}")
            else:
                raise RuntimeError(f"File not found: {target_filename}")
        current_state_data = normalize_json(current_state_data)
        return current_state_data, target_filename, is_new_creation, status_msg

    def _load_api_config(self, api_url, api_key, model_name):
        """
        Load API configuration from UI inputs or config.json.
        Priority: UI inputs > config.json
        
        Returns:
            dict: Configuration with keys 'api_url', 'api_key', 'model_name'
        """
        config_data = {}
        base_dir = os.path.dirname(__file__)
        config_path = os.path.join(base_dir, "config.json")
        example_path = os.path.join(base_dir, "config.json.example")

        # Auto-create config.json from example if missing
        if not os.path.exists(config_path) and os.path.exists(example_path):
            shutil.copy(example_path, config_path)
            print(f"[Persona Director] Auto-created config.json from example.")
            raise RuntimeError("config.json created from example. Please fill in your API details.")

        # Load config file
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception as e:
                print(f"[Persona Director] Warning: Failed to parse config.json: {e}")
        
        def get_param(ui_val, config_key):
            """Get parameter from UI or config, with UI taking priority."""
            val = ui_val.strip()
            if not val:
                val = config_data.get(config_key, "").strip()
            return val
        
        # Resolve parameters
        final_api_key = get_param(api_key, "api_key")
        if not final_api_key:
            raise RuntimeError("API Key not found! Set it in the Node or config.json")

        final_api_url = get_param(api_url, "api_url")
        if not final_api_url:
            raise RuntimeError("API URL not found! Set it in the Node or config.json")
        
        final_model_name = get_param(model_name, "model_name")
        if not final_model_name:
            raise RuntimeError(
                "Model Name not found! Please specify 'model_name' "
                "(e.g. 'gpt-4o', 'claude-3-5-sonnet') in the Node or config.json"
            )

        return {
            "api_url": final_api_url,
            "api_key": final_api_key,
            "model_name": final_model_name
        }

    def _build_user_message(self, is_new_creation, current_state_data, user_instruction):
        """
        Build the user message for LLM based on creation mode.
        
        Args:
            is_new_creation: Whether this is a new character creation
            current_state_data: Current persona state (empty if new)
            user_instruction: User's instruction text
            
        Returns:
            str: Formatted message for LLM
        """
        if is_new_creation:
            return f"Task: Create a new character.\nDescription: {user_instruction}"
        else:
            state_str = json.dumps(current_state_data, indent=2, ensure_ascii=False)
            return (
                f"Current State JSON:\n{state_str}\n\n"
                f"Task: Update state based on instruction.\n"
                f"Instruction: {user_instruction}"
            )

    def _call_llm(self, client, model_name, system_prompt, user_message):
        """
        Call the LLM API and parse the response.
        
        Returns:
            dict: Parsed JSON response from LLM
        """
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
        )
        
        finish_reason = response.choices[0].finish_reason
        if finish_reason == "length":
            raise RuntimeError("LLM output truncated! (Max Tokens reached).")
        if finish_reason == "content_filter":
            raise RuntimeError("LLM refused to generate (Content Filter).")
        
        raw_content = response.choices[0].message.content
        parsed_data = robust_json_parse(raw_content)

        if not parsed_data:
            raise RuntimeError(f"Failed to parse LLM Response!\nRaw Content: {raw_content[:200]}...")
        
        return parsed_data

    def _clean_and_merge_tags(self, text):
        """
        Utility function to normalize and deduplicate tags.
        
        Logic:
        1. Normalization: Convert to lowercase to ensure case-insensitive matching (SD CLIP is case-insensitive).
        2. Cleaning: Strip whitespace and remove empty strings.
        3. Deduplication: Remove duplicates while PRESERVING insertion order (critical for prompt weighting).
           Using dict.fromkeys() ensures O(N) time complexity compared to O(N^2) for list lookups.
        
        Args:
            text (str): Comma-separated string of tags.
            
        Returns:
            str: Cleaned, deduplicated, comma-separated string.
        """
        if not text:
            return ""
            
        # Split by comma, strip whitespace, and convert to lowercase
        # filter(None, ...) removes any empty strings resulting from trailing commas
        tags = [t.strip().lower() for t in text.split(",")]
        tags = list(filter(None, tags))
        
        # Ordered deduplication
        # Python 3.7+ guarantees insertion order for dict keys
        deduped_tags = list(dict.fromkeys(tags))
        
        return ", ".join(deduped_tags)

    def _extract_prompts(self, parsed_data, current_state_data):
        """
        Extract and process prompts from LLM response.
        
        Returns:
            tuple: (updated_state, positive_prompt, negative_prompt)
        """
        updated_state = parsed_data.get("updated_state", current_state_data)
        positive_prompt = parsed_data.get("positive_prompt", "")
        negative_prompt = parsed_data.get("negative_prompt", "")
        
        # Remove reasoning field if present
        if "reasoning" in updated_state:
            del updated_state["reasoning"]
        
        # Fallback: reconstruct prompt from state if missing
        if not positive_prompt and isinstance(updated_state, dict):
            parts = [
                updated_state.get("style", ""),
                updated_state.get("character", ""),
                updated_state.get("outfit", ""),
                updated_state.get("action", ""),
                updated_state.get("location", ""),
                updated_state.get("composition", ""),
                updated_state.get("meta", "")
            ]
            positive_prompt = ", ".join([p for p in parts if p])
        # Construct final positive prompt: Prefix -> LLM Content -> Suffix
        raw_full_pos = f"{POS_PREFIX}, {positive_prompt}, {POS_SUFFIX}"
        
        # Clean and deduplicate (removes redundant 'masterpiece' if LLM hallucinated it)
        final_positive = self._clean_and_merge_tags(raw_full_pos)


        # --- 2. Process Negative Prompt ---
        
        # Construct final negative prompt: Base Quality Tags -> LLM Specific Exclusions
        raw_full_neg = f"{NEG_BASE}, {negative_prompt}"
        
        # Clean and deduplicate
        final_negative = self._clean_and_merge_tags(raw_full_neg)
        return updated_state, final_positive, final_negative

    def _save_persona_state(self, target_filename, state_data, positive_prompt, negative_prompt, user_instruction):
        """Save persona state and prompts to disk."""
        payload = {
            "updated_state": state_data,
            "inference_cache":{
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt,
            },
            "system_meta":{
                "last_instruction": user_instruction
            }
        }
        save_path = os.path.join(PERSONA_DIR, target_filename)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
        print(f"[Success] State saved to {target_filename}")


    def generate_prompt(self, persona_selector, new_persona_name, user_instruction, 
                       promptconfig, api_url, api_key, model_name):
        """
        Main entry point: Generate prompts using LLM-based persona state management.
        
        Returns:
            tuple: (positive_prompt, negative_prompt, debug_state_json)
        """
        try:
            # Step 1: Resolve persona state
            state_data, target_filename, is_new_creation, status_msg = \
                self._resolve_persona_state(persona_selector, new_persona_name)
            current_state_data = state_data["updated_state"]
            positive_prompt = state_data.get("inference_cache").get("positive_prompt", "")
            negative_prompt = state_data.get("inference_cache").get("negative_prompt", "")
            if user_instruction.strip() == "" or user_instruction == state_data.get("system_meta", {}).get("last_instruction", ""):
                return (positive_prompt, negative_prompt, json.dumps(current_state_data, indent=2, ensure_ascii=False))
            # Step 2: Load API configuration
            api_config = self._load_api_config(api_url, api_key, model_name)
            
            # Step 3: Initialize API client
            try:
                client = OpenAI(
                    base_url=api_config["api_url"],
                    api_key=api_config["api_key"]
                )
            except Exception as e:
                raise RuntimeError(f"Client Init Error: {str(e)}")
            
            # Step 4: Load system prompt
            base_dir = os.path.dirname(__file__)
            system_prompt = load_prompt(os.path.join(base_dir, PROMPTCONFIGS_DIR, promptconfig))
            
            # Step 5: Build user message
            user_message = self._build_user_message(
                is_new_creation, current_state_data, user_instruction
            )
            
            # Step 6: Call LLM
            parsed_data = self._call_llm(
                client, api_config["model_name"], system_prompt, user_message
            )
            
            # Step 7: Extract prompts
            updated_state, positive_prompt, negative_prompt = \
                self._extract_prompts(parsed_data, current_state_data)
            
            # Step 8: Save to disk (state + prompts)
            self._save_persona_state(target_filename, updated_state, positive_prompt, negative_prompt, user_instruction)
            
            # Step 9: Return results
            debug_state = json.dumps(updated_state, indent=2, ensure_ascii=False)
            return (positive_prompt, negative_prompt, debug_state)

        except Exception as e:
            print(f"[Error] API Failed: {e}")
            raise RuntimeError(
                f"LLM API Error: {str(e)}\n"
                "Please check your API Key, Network, or Model Name."
            )

# Node Mapping
NODE_CLASS_MAPPINGS = {
    "PersonaDirectorNode": PersonaDirectorNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PersonaDirectorNode": "AI Director (Persona)"
}