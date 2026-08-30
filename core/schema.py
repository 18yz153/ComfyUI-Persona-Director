"""Schema: turn a style-profile config into a state schema + tool definition.

The config is the single source of truth for the state keys. Changing a key
means editing the JSON config, not this file.
"""


class StateSchema:
    def __init__(self, fields):
        # fields: list of dicts with keys:
        #   key, label, required, render (default True),
        #   enum (optional), required_if_subject (optional)
        self.fields = fields
        self.by_key = {f["key"]: f for f in fields}

    @classmethod
    def from_config(cls, cfg):
        raw = cfg.get("state_schema", {}).get("fields")
        if not raw:
            # Legacy config format: json_state_structure = {key: label}
            legacy = cfg.get("json_state_structure", {})
            raw = [{"key": k, "label": v} for k, v in legacy.items()]
        fields = []
        for f in raw:
            fields.append({
                "key": f["key"],
                "label": f.get("label", f["key"]),
                "required": bool(f.get("required", False)),
                "render": bool(f.get("render", True)),
                "enum": f.get("enum"),
                "required_if_subject": f.get("required_if_subject"),
            })
        return cls(fields)

    @property
    def keys(self):
        return [f["key"] for f in self.fields]

    @property
    def renderable_keys(self):
        return [f["key"] for f in self.fields if f["render"]]

    def to_json_schema(self):
        """JSON Schema for the tool-call arguments. Fields are optional so the
        model can return only the fields it changed (no full-state echo).
        Exception: 'positive' is regenerated every call, so it is required."""
        properties = {}
        required = []
        for f in self.fields:
            if f["enum"]:
                properties[f["key"]] = {"type": "string", "enum": f["enum"]}
            else:
                properties[f["key"]] = {"type": "string"}
            if f["key"] == "positive":
                required.append(f["key"])
        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def to_state_structure_text(self):
        lines = []
        for f in self.fields:
            if f["key"] == "reasoning":
                lines.append('"reasoning": "Step-by-step logic."')
            else:
                lines.append('"%s": "%s"' % (f["key"], f["label"]))
        return "\n".join(lines)

    def missing_required(self, state):
        """Soft validation: return the keys that must be present but are empty."""
        missing = []
        for f in self.fields:
            if f["required"] and not str(state.get(f["key"], "") or "").strip():
                missing.append(f["key"])
            cond = f.get("required_if_subject")
            if cond:
                subj = state.get("subject_type", "")
                if subj in cond and not str(state.get(f["key"], "") or "").strip():
                    missing.append("%s (subject_type=%s)" % (f["key"], subj))
        return missing


def build_tool(schema):
    """Build the function-calling tool that updates the persona state."""
    return [{
        "type": "function",
        "function": {
            "name": "update_persona_state",
            "description": (
                "Update the image/persona state according to the user instruction. "
                "Include only the fields that change; omit unchanged fields."
            ),
            "parameters": schema.to_json_schema(),
        },
    }]
