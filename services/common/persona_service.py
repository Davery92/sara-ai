import os
import yaml
from pathlib import Path
from typing import Dict, Optional, List, Any

# Default paths
PERSONALITY_DIR = os.getenv('PERSONALITY_DIR', str(Path(__file__).parent.parent.parent / 'configs' / 'personalities'))
DEFAULT_PERSONA = os.getenv('DEFAULT_PERSONA', 'sara_default')

class PersonaService:
    """
    Service for loading and managing persona configurations from markdown files.
    """
    
    def __init__(self, personality_dir: str = PERSONALITY_DIR):
        self.personality_dir = personality_dir
        self.personas: Dict[str, str] = {}
        self.load_personas()
    
    def load_personas(self) -> None:
        """Load all available personas from the personality directory."""
        personality_path = Path(self.personality_dir)
        if not personality_path.exists():
            raise FileNotFoundError(f"Personality directory not found: {self.personality_dir}")
        
        for file_path in personality_path.glob("*.md"):
            persona_name = file_path.stem
            with open(file_path, 'r') as f:
                self.personas[persona_name] = f.read()
    
    def get_persona_content(self, persona_name: str) -> Optional[str]:
        """Get the content of a specific persona."""
        if persona_name not in self.personas:
            return None
        return self.personas[persona_name]
    
    def get_available_personas(self) -> List[str]:
        """Get a list of all available persona names."""
        return list(self.personas.keys())
    
    def get_default_persona(self) -> str:
        """Get the default persona name."""
        return DEFAULT_PERSONA
    
    def get_persona_config(self, persona_name: str) -> Dict[str, Any]:
        """
        Get persona configuration as a structured dictionary.
        Returns basic metadata about the persona.
        """
        content = self.get_persona_content(persona_name)
        if not content:
            raise ValueError(f"Persona not found: {persona_name}")
        
        # Extract basic metadata from the content
        lines = content.split("\n")
        title = lines[0].replace("#", "").strip() if lines else persona_name
        
        return {
            "name": persona_name,
            "title": title,
            "version": "1.0",  # Hardcoded for now, could be extracted from content
            "content": content,
        }


# Singleton instance
_instance = None

def get_persona_service() -> PersonaService:
    """Get or create the singleton PersonaService instance."""
    global _instance
    if _instance is None:
        _instance = PersonaService()
    return _instance 