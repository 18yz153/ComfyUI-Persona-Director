import os

from .base import BaseDirectorNode, BASE_DIR


class PersonaDirectorTagsNode(BaseDirectorNode):
    """Danbooru/SDXL tag output. State values are keyword lists."""

    PERSONA_DIR = os.path.join(BASE_DIR, "personas")
    DEFAULT_CONFIG = "default.json"
