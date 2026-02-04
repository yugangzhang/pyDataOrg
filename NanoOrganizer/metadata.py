#!/usr/bin/env python3
"""
Metadata classes for experimental runs.

Contains:
- ChemicalSpec: Chemical specifications
- ReactionParams: Reaction conditions
- RunMetadata: Complete run metadata
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Union
from datetime import datetime

TimeLike = Union[str, int, float, List[str], List[int], List[float]]


@dataclass
class ChemicalSpec:
    """Chemical specification for a reaction."""
    name: str
    concentration: float
    concentration_unit: str = "mM"
    volume_uL: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ChemicalSpec':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class ReactionParams:
    """Reaction parameters for nanoparticle synthesis."""
    chemicals: List[ChemicalSpec]
    temperature_C: float = 25.0
    stir_time_s: float = 0.0
    reaction_time_s: float = 0.0
    pH: Optional[float] = None
    solvent: str = "Water"
    conductor: str = "Unknown"
    description: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)
        data['chemicals'] = [c.to_dict() for c in self.chemicals]
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ReactionParams':
        """Create from dictionary."""
        chemicals = [ChemicalSpec.from_dict(c) for c in data.pop('chemicals')]
        return cls(chemicals=chemicals, **data)


@dataclass
class RunMetadata:
    """Metadata for a single experimental run."""
    project: str
    experiment: str  # Usually a date like "2024-10-20"
    run_id: str
    sample_id: str
    reaction: Optional[ReactionParams] = None
    filename: Optional[str] = None
    # ✅ Annotated + flexible types
    data_collection_time_string: Optional[TimeLike] = None
    data_collection_time_epoch: Optional[TimeLike] = None
    reaction_time: Optional[TimeLike] = None
    reaction_temperature: Optional[TimeLike] = None  
    
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)
        if data['reaction'] != None:
            data['reaction'] = self.reaction.to_dict()
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'RunMetadata':
        """Create from dictionary."""
        if data['reaction'] != None:
        #print( data ) 
            reaction = ReactionParams.from_dict(data.pop('reaction'))
            return cls(reaction=reaction, **data)
        else:             
            return cls( **data)




        