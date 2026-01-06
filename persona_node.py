import os
import json
import re
import shutil
from openai import OpenAI

# Define the directory for storing persona cards
PERSONA_DIR = os.path.join(os.path.dirname(__file__), "personas")
if not os.path.exists(PERSONA_DIR):
    os.makedirs(PERSONA_DIR)

class PersonaDirectorNode:
    def __init__(self):
        pass
    
    @classmethod
    def INPUT_TYPES(s):
        # 1. Scan the directory for existing JSON files
        files = [f for f in os.listdir(PERSONA_DIR) if f.endswith(".json")]
        # 2. Add the "Create New" option at the top
        selector_options = ["Create New (Smart)", "Force Reset (Overwrite)"] + files

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

    def robust_json_parse(self, raw_content):
        """
        Robustly extracts and parses JSON from the LLM response.
        Handles Markdown code blocks and prefixes.
        """
        try:
            return json.loads(raw_content.strip())
        except:
            pass

        # Regex to find the first JSON object { ... }
        match = re.search(r'(\{.*\})', raw_content, re.DOTALL)
        if match:
            clean_json = match.group(1)
            try:
                return json.loads(clean_json)
            except Exception as e:
                print(f"[Error] JSON Regex extraction failed: {e}")
        
        return None

    def generate_prompt(self, persona_selector, new_persona_name, user_instruction, api_url, api_key, model_name):
        
        # --- State Management Logic ---
        
        current_state_data = {}
        target_filename = ""
        is_new_creation = False
        
        # Branch A: Create New or Force Reset (Relies on new_persona_name)
        if persona_selector in ["Create New (Smart)", "Force Reset (Overwrite)"]:
            
            # Sanitize filename
            safe_name = "".join([c for c in new_persona_name if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).strip()
            if not safe_name: safe_name = "New_Character"
            target_filename = f"{safe_name}.json"
            file_path = os.path.join(PERSONA_DIR, target_filename)

            # Sub-Branch: Force Reset
            if persona_selector == "Force Reset (Overwrite)":
                is_new_creation = True
                status_msg = f"Reset Character: {target_filename}"
            
            # Sub-Branch: Smart Create (Upsert Logic)
            else:
                if os.path.exists(file_path):
                    # File exists -> Auto-switch to Evolve mode
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
                    # File missing -> Create new
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
                    return ("Error", "Error", f"Read Error: {e}")
            else:
                return ("Error", "Error", f"File not found: {target_filename}")

        # --- API Client Setup ---
        config_data = {}
        base_dir = os.path.dirname(__file__)
        config_path = os.path.join(base_dir, "config.json")
        example_path = os.path.join(base_dir, "config.json.example")

        if not os.path.exists(config_path) and os.path.exists(example_path):
            shutil.copy(example_path, config_path)
            print(f"[Persona Director] Auto-created config.json from example.")
            raise RuntimeError("config.json created from example. Please fill in your API details.")

        # 2. Resolve API Key (Priority: UI -> Config)
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception as e:
                print(f"[Persona Director] Warning: Failed to parse config.json: {e}")
        
        def get_param(ui_val, config_key):
            # 1. Check UI (Strip spaces)
            val = ui_val.strip()
            # 2. Check Config
            if not val:
                val = config_data.get(config_key, "").strip()
            return val
        final_api_key = get_param(api_key, "api_key")
        if not final_api_key:
            raise RuntimeError("API Key not found! Set it in the Node or /ComfyUI-Persona-Director/config.json")

        final_api_url = get_param(api_url, "api_url")
        if not final_api_url:
            raise RuntimeError("API URL not found! Set it in the Node or /ComfyUI-Persona-Director/config.json")
        final_model_name = get_param(model_name, "model_name")
        if not final_model_name:
            raise RuntimeError("Model Name not found! Please specify 'model_name' (e.g. 'gpt-4o', 'claude-3-5-sonnet') in the Node or /ComfyUI-Persona-Director/config.json")

        try:
            client = OpenAI(base_url=final_api_url, api_key=final_api_key)
        except Exception as e:
            raise RuntimeError(f"Client Init Error: {str(e)}")

        # --- System Prompt Construction ---
        # Defines the strict JSON schema for the LLM
        system_prompt = """
        You are an expert AI Director for Stable Diffusion XL.
        You manage a structured state of a character and generate image prompts.

        YOUR GOAL:
        1. Update the JSON state based on the User Instruction.
        2. Generate a flat string prompt optimized for Danbooru/SDXL tagging.
        IMPORTANT: You must use chain of thought before updating the state. 
        Old tags often conflict with new instructions. You must act as a "Cleanup Crew".

        JSON STATE STRUCTURE:
        {
            "reasoning": "Step-by-step logic. Analyze what MUST be removed/added based on the new instruction.",
            "character": "Identity tags. IF the character is a known/famous character (e.g., from Anime/Game), ONLY use their specific name tag (e.g., 'shirasu_azusa'). DO NOT describe hair/eyes unless the user explicitly asks to change them (Alt color). IF original character, describe full traits.",
            "outfit": "Clothing, Accessories, Shoes. Updates as a complete set usually.",
            "action": "Body Pose (standing, sitting), Gestures (hand on hip), Facial Expression (blush, smile).",
            "location": "Environment (bedroom, beach), Lighting (sunset, cinematic light), Weather.",
            "composition": "Camera Framing (cowboy shot, full body, portrait), Camera Angle (from below, dutch angle), Gaze (looking at viewer).",
            "style": "Art Direction (anime style, monochrome, oil painting, pixel art, cel shading). NOT quality tags.",
            "meta": "Technical Quality Tags. (highres, masterpiece, best quality).",
        }

        RULES:
        1. If this is a NEW character, populate fields based on the instruction.
        2. If this is an EXISTING character, ONLY update the specific fields mentioned in the instruction.
           - Example: If instruction is "change to maid outfit", update 'outfit' but KEEP 'character' exactly as is.
           - Example: If instruction is "running on beach", update 'action' and 'location'.
        LOGIC RULES:
        1. **Conflict Resolution**: 
           - If user says "focus on feet", you MUST REMOVE 'full body', 'upper body', 'looking at viewer'.
           
        2. **Nudity Logic**: 
           - 'completely nude' means wearing NOTHING.
           - If user adds ANY item (e.g., "wear socks"), you MUST REMOVE 'completely nude'.
           
        3. **Anti-Redundancy**:
           - Do NOT output "black thighhighs, black stockings". Just use "black thighhighs".

        4. **Negative Inference**: 
           - Based on the current state, infer what should NOT be in the image.
           - E.g., if 'beach', negative='indoors'. if 'nude', negative='clothes'.

        5. **Famous Character Simplification (Trust the Model)**:
           - If the user provides a specific name (e.g., "Hatsune Miku"), assume the image generator KNOWS this character.
           - **ACTION**: Output ONLY the name tag (e.g., "hatsune_miku") (and '1girl'/'1boy').
           - **FORBIDDEN**: Do NOT list hair color, eye color, or skin tone. This prevents hallucinations (e.g., mistakenly saying Miku has red hair).
           - **EXCEPTION**: Only describe traits if the user is creating an Original Character (OC) or explicitly changing the look (e.g., "Black haired Miku").
        
        6. **Tag injuection**:
           - if the user provides specific tags (e.g., "tag:(long_hair)"), you MUST include the exact tag in the relevant fields.
           - if the user provides specific character tag (e.g., "tag:(rem_(re:zero))"), you MUST use the exact tag (e.g., "rem_(re:zero)").
        OUTPUT FORMAT:
        You must return a single JSON object with two keys:
        {
            "updated_state": { ... the structure defined above ... },
            "positive_prompt": "The final comma-separated string for image generation",
            "negative_prompt": "Combine standard quality negatives + context-specific exclusions."
        }
        """

        # Prepare Context for LLM
        if is_new_creation:
            user_message = f"Task: Create a new character.\nDescription: {user_instruction}"
        else:
            # Convert current JSON state to string for the LLM to read
            state_str = json.dumps(current_state_data, indent=2, ensure_ascii=False)
            user_message = f"Current State JSON:\n{state_str}\n\nTask: Update state based on instruction.\nInstruction: {user_instruction}"

        # --- LLM Execution ---
        try:
            response = client.chat.completions.create(
                model=final_model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                response_format={ "type": "json_object" },
                temperature=0.5,
            )
            finish_reason = response.choices[0].finish_reason
            if finish_reason == "length":
                raise RuntimeError("LLM output truncated! (Max Tokens reached).")
            if finish_reason == "content_filter":
                raise RuntimeError("LLM refused to generate (Content Filter).")
            raw_content = response.choices[0].message.content
            parsed_data = self.robust_json_parse(raw_content)

            if not parsed_data:
                raise RuntimeError("Failed to parse LLM Response!\nRaw Content: {raw_content[:200]}...")
            
            # Extract results
            updated_state = parsed_data.get("updated_state", current_state_data)
            positive_prompt = parsed_data.get("positive_prompt", "")
            default_neg = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry"
            negative_prompt = parsed_data.get("negative_prompt", default_neg)
            if "reasoning" in updated_state:
                del updated_state["reasoning"]
            # Fallback if prompt is missing, reconstruct it from state
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

            # --- Save to Disk ---
            save_path = os.path.join(PERSONA_DIR, target_filename)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(updated_state, f, indent=4, ensure_ascii=False)
            
            print(f"[Success] State saved to {target_filename}")

            return (positive_prompt, negative_prompt, json.dumps(updated_state, indent=2, ensure_ascii=False))

        except Exception as e:
            print(f"[Error] API Failed: {e}")
            raise RuntimeError(f"LLM API Error: {str(e)}\nPlease check your API Key, Network, or Model Name.")

# Node Mapping
NODE_CLASS_MAPPINGS = {
    "PersonaDirectorNode": PersonaDirectorNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PersonaDirectorNode": "AI Director (Persona)"
}