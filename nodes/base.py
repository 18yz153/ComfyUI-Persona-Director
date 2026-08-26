import os

from ..core.engine import PersonaDirectorEngine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIGS_DIR = os.path.join(BASE_DIR, "configs")


class BaseDirectorNode:
    """Shared ComfyUI node shell. Subclasses set PERSONA_DIR + DEFAULT_CONFIG."""

    PERSONA_DIR = os.path.join(BASE_DIR, "personas")
    DEFAULT_CONFIG = "default.json"

    @classmethod
    def INPUT_TYPES(cls):
        persona_dir = os.path.abspath(cls.PERSONA_DIR)
        os.makedirs(persona_dir, exist_ok=True)
        files = sorted(f for f in os.listdir(persona_dir) if f.endswith(".json"))
        configs = sorted(f for f in os.listdir(CONFIGS_DIR) if f.endswith(".json"))
        configs.sort(key=lambda f: (f != cls.DEFAULT_CONFIG, f))
        selector = ["Create New (Smart)", "Force Reset (Overwrite)"] + files
        return {
            "required": {
                "persona_selector": (selector,),
                "new_persona_name": ("STRING", {"default": "New_Character", "multiline": False}),
                "user_instruction": ("STRING", {
                    "multiline": True,
                    "default": "A girl, white hair, blue eyes, wearing school uniform",
                    "placeholder": "Describe the character (if new) or the change (if existing)...",
                }),
                "promptconfig": (configs,),
                "tool_mode": (["auto", "tool", "json_only"],),
                "api_url": ("STRING", {"default": "", "placeholder": "Leave empty to use config.json"}),
                "api_key": ("STRING", {"default": "", "placeholder": "Leave empty to use config.json"}),
                "model_name": ("STRING", {"default": "", "placeholder": "Leave empty to use config.json"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("positive_prompt", "negative_prompt", "debug_state")
    FUNCTION = "generate_prompt"
    CATEGORY = "Persona Director"

    def generate_prompt(self, persona_selector, new_persona_name, user_instruction,
                        promptconfig, tool_mode, api_url, api_key, model_name):
        config_path = os.path.join(CONFIGS_DIR, promptconfig)
        engine = PersonaDirectorEngine(config_path, os.path.abspath(self.PERSONA_DIR))
        return engine.generate(
            persona_selector, new_persona_name, user_instruction,
            api_url, api_key, model_name, tool_mode,
        )
