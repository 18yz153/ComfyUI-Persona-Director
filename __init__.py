from .persona_node import PersonaDirectorNode

NODE_CLASS_MAPPINGS = {
    "PersonaDirector": PersonaDirectorNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PersonaDirector": "AI Director (Persona)"
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]