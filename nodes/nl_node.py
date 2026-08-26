import os

from .base import BaseDirectorNode, BASE_DIR


class PersonaDirectorNLNode(BaseDirectorNode):
    """Natural-language output for DiT models (FLUX, SD3.5). State values are prose."""

    PERSONA_DIR = os.path.join(BASE_DIR, "personas_nl")
    DEFAULT_CONFIG = "nl.json"
