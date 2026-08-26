import os
import re
import json


def sanitize_filename(name):
    safe = re.sub(r"[^\w\-]", "_", name).strip("_")
    if not safe:
        safe = "New_Character"
    return safe[:100]


def normalize(raw, schema):
    """Coerce whatever was on disk into the wrapped state envelope."""
    if isinstance(raw, dict) and "updated_state" in raw:
        return raw
    if isinstance(raw, dict) and any(k in raw for k in schema.keys if k != "reasoning"):
        return {"updated_state": raw, "inference_cache": {}, "system_meta": {}}
    return {"updated_state": {}, "inference_cache": {}, "system_meta": {}}


def load_persona(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_persona(path, updated_state, positive, negative, instruction):
    payload = {
        "updated_state": updated_state,
        "inference_cache": {
            "positive_prompt": positive,
            "negative_prompt": negative,
        },
        "system_meta": {"last_instruction": instruction},
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)
