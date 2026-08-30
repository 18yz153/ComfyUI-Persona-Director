import os
import json
import shutil

from .schema import StateSchema, build_tool
from .state import sanitize_filename, load_persona, save_persona, normalize
from .render import render_positive, render_negative
from .llm import LLMBackend

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODE_CREATE_SMART = "Create New (Smart)"
MODE_FORCE_RESET = "Force Reset (Overwrite)"


class PersonaDirectorEngine:
    """Config-driven engine shared by all director nodes.

    The engine is stateless w.r.t. the prompt; the config file decides the
    state schema (keys), render mode (tags vs natural language), and the
    system prompt template.
    """

    def __init__(self, config_path, persona_dir):
        self.config_path = config_path
        self.persona_dir = persona_dir
        os.makedirs(self.persona_dir, exist_ok=True)
        self.cfg = self._load_config(config_path)
        self.schema = StateSchema.from_config(self.cfg)

    def _load_config(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_personas(self):
        return sorted(f for f in os.listdir(self.persona_dir) if f.endswith(".json"))

    def build_system_prompt(self):
        sys = self.cfg.get("system", {})
        parts = [
            "\n".join(sys.get("instructions", [])),
            "JSON STATE STRUCTURE:\n" + self.schema.to_state_structure_text(),
            "LOGIC RULES:\n" + "\n".join(sys.get("logic_rules", [])),
            "OUTPUT:\n" + "\n".join(sys.get("output_format", [])),
        ]
        return "\n\n".join(p for p in parts if p)

    def _resolve(self, selector, new_name):
        empty = {"updated_state": {}, "inference_cache": {}, "system_meta": {}}

        if selector in (MODE_CREATE_SMART, MODE_FORCE_RESET):
            fname = sanitize_filename(new_name) + ".json"
            path = os.path.join(self.persona_dir, fname)
            if selector == MODE_FORCE_RESET:
                return empty, fname, True, "Reset: " + fname
            if os.path.exists(path):
                try:
                    return normalize(load_persona(path), self.schema), fname, False, "Resume: " + fname
                except Exception:
                    return empty, fname, True, "Corrupted, reset: " + fname
            return empty, fname, True, "New: " + fname

        fname = selector
        path = os.path.join(self.persona_dir, fname)
        if not os.path.exists(path):
            raise RuntimeError("File not found: " + fname)
        return normalize(load_persona(path), self.schema), fname, False, "Loaded: " + fname

    def _build_user_message(self, is_new, state, instruction):
        if is_new:
            return "Task: Create a new image state.\nDescription: " + instruction
        return (
            "Current State JSON:\n" + json.dumps(state, indent=2, ensure_ascii=False) + "\n\n"
            + "Task: Update state based on instruction.\nInstruction: " + instruction
        )

    def _load_api_config(self, api_url, api_key, model_name):
        config_path = os.path.join(BASE_DIR, "config.json")
        example_path = os.path.join(BASE_DIR, "config.json.example")
        if not os.path.exists(config_path) and os.path.exists(example_path):
            shutil.copy(example_path, config_path)
            print("[Persona Director] Auto-created config.json from example.")
            raise RuntimeError("config.json created from example. Please fill in your API details.")

        cfg = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception as e:
                print("[Persona Director] Warning: failed to parse config.json: " + str(e))

        def pick(ui, key):
            v = (ui or "").strip()
            if not v:
                v = str(cfg.get(key, "") or "").strip()
            return v

        key = pick(api_key, "api_key")
        url = pick(api_url, "api_url")
        model = pick(model_name, "model_name")
        if not key:
            raise RuntimeError("API Key not found! Set it in the Node or config.json")
        if not url:
            raise RuntimeError("API URL not found! Set it in the Node or config.json")
        if not model:
            raise RuntimeError("Model name not found! Set 'model_name' in the Node or config.json")
        return {"api_url": url, "api_key": key, "model_name": model}

    def generate(self, persona_selector, new_persona_name, user_instruction,
                 api_url, api_key, model_name, tool_mode="auto"):
        try:
            state_data, fname, is_new, _status = self._resolve(persona_selector, new_persona_name)
            current_state = state_data.get("updated_state", {}) or {}
            cache = state_data.get("inference_cache") or {}
            meta = state_data.get("system_meta") or {}

            positive = cache.get("positive_prompt", "")
            negative = cache.get("negative_prompt", "")
            last_instr = meta.get("last_instruction", "")

            instr = (user_instruction or "").strip()
            if not instr or instr == last_instr:
                return positive, negative, json.dumps(current_state, indent=2, ensure_ascii=False)

            api_cfg = self._load_api_config(api_url, api_key, model_name)
            backend = LLMBackend(api_cfg["api_url"], api_cfg["api_key"], api_cfg["model_name"])

            system_prompt = self.build_system_prompt()

            # Regenerate the positive prompt each call: never send the stale one to the LLM.
            if "positive" in self.schema.by_key:
                current_state["positive"] = ""

            user_message = self._build_user_message(is_new, current_state, instr)

            parsed = backend.complete(
                system_prompt, user_message,
                tools=build_tool(self.schema), tool_mode=tool_mode,
            )

            # Legacy echo wrappers return {"updated_state": {...}}; tool calls
            # return the state dict directly.
            if isinstance(parsed, dict) and isinstance(parsed.get("updated_state"), dict):
                parsed = parsed["updated_state"]

            parsed_state = {k: v for k, v in parsed.items()
                            if k in self.schema.keys and k != "reasoning"}
            updated = dict(current_state)
            updated.update(parsed_state)

            if is_new:
                missing = self.schema.missing_required(updated)
                if missing:
                    print("[Persona Director] Warning: new state missing fields: %s" % ", ".join(missing))

            positive = render_positive(updated, self.schema, self.cfg.get("prompt", {}))
            negative = render_negative(updated, self.cfg.get("prompt", {}))

            save_persona(os.path.join(self.persona_dir, fname), updated, positive, negative, instr)

            return positive, negative, json.dumps(updated, indent=2, ensure_ascii=False)

        except Exception as e:
            print("[Error] " + str(e))
            raise RuntimeError(
                "LLM API Error: " + str(e) + "\n"
                "Please check your API Key, Network, or Model Name."
            )
