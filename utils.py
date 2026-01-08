import json
import re

def load_prompt(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    full_prompt = []
    full_prompt.append("\n".join(data['system_instructions']))
    
    full_prompt.append("\nJSON STATE STRUCTURE:")
    full_prompt.append(json.dumps(data['json_state_structure'], indent=2))
    
    full_prompt.append("\nLOGIC RULES:")
    full_prompt.append("\n".join(data['logic_rules']))
    
    full_prompt.append("\nOUTPUT FORMAT:")
    full_prompt.append("\n".join(data['output_format_instructions']))
    
    return "\n\n".join(full_prompt)

def robust_json_parse(raw_content):
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

def normalize_json(raw_data):
    if "updated_state" in raw_data and "inference_cache" in raw_data and "system_meta" in raw_data:
        return raw_data
    if "character" in raw_data:
        return {
            "updated_state": raw_data, # 把整个包都塞进 state
            "inference_cache": {},
            "system_meta": {}
        }
    return {"updated_state": {}, "inference_cache": {}, "system_meta": {}}