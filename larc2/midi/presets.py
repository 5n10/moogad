"""M300 preset models and utilities."""
from dataclasses import dataclass, field
from typing import Dict, List, Any

@dataclass
class EffectPresetV3:
    """Represents an M300 Effect preset (V3 format)."""
    name: str = "Untitled"
    algorithm: str = "Random Hall"
    parameters: Dict[str, int] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "name": self.name,
            "algorithm": self.algorithm,
            "parameters": self.parameters,
            "tags": self.tags
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EffectPresetV3':
        """Create from dictionary data."""
        return cls(
            name=data.get("name", "Untitled"),
            algorithm=data.get("algorithm", "Random Hall"),
            parameters=data.get("parameters", {}),
            tags=data.get("tags", [])
        )

@dataclass
class SetupPresetV3:
    """Represents an M300 Setup preset (V3 format)."""
    name: str = "Untitled"
    machine_config: int = 0
    effect_a_num: int = 0
    effect_b_num: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "name": self.name,
            "machine_config": self.machine_config,
            "effect_a_num": self.effect_a_num,
            "effect_b_num": self.effect_b_num
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SetupPresetV3':
        """Create from dictionary data."""
        return cls(
            name=data.get("name", "Untitled"),
            machine_config=data.get("machine_config", 0),
            effect_a_num=data.get("effect_a_num", 0),
            effect_b_num=data.get("effect_b_num", 0)
        )
