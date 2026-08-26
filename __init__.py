from .nodes import PersonaDirectorTagsNode, PersonaDirectorNLNode

NODE_CLASS_MAPPINGS = {
    "PersonaDirector": PersonaDirectorTagsNode,   # legacy id, kept for saved workflows
    "PersonaDirectorNL": PersonaDirectorNLNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PersonaDirector": "AI Director (Tags)",
    "PersonaDirectorNL": "AI Director (NL / DiT)",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
