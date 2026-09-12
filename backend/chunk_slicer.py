import numpy as np
import trimesh
from dataclasses import dataclass
from typing import List, Optional
from layer_schedule import generate_layer_schedule
from slice_intersection import slice_mesh_at_z

@dataclass
class SlicedLayerRecord:
    """
    Immutable mathematical record containing deterministic geometry
    and metadata mapping back to multi-axis orientations.
    """
    chunk_idx: int
    layer_idx: int
    z_height: float
    transform_matrix: List[float]  # Flat 16-element array
    segments: np.ndarray           # Shape: (N, 2, 2)


def slice_chunk(
    mesh: trimesh.Trimesh,
    chunk_idx: int,
    transform_matrix: List[float],
    z_min: float,
    z_max: float,
    layer_height: float,
    first_layer_height: Optional[float] = None,
    half_layer_offset: bool = True
) -> List[SlicedLayerRecord]:
    """
    Engine that slices an aligned mesh at mathematically deterministic layers 
    and packages them into highly strictly metadata-coupled layer records.
    """
    records = []
    
    # 1. Ask the scheduling engine for absolute deterministic Z heights
    schedule = generate_layer_schedule(
        z_min=z_min, 
        z_max=z_max, 
        layer_height=layer_height, 
        first_layer_height=first_layer_height, 
        half_layer_offset=half_layer_offset
    )
    
    # 2. Iterate and mathematically intersect at each scheduled layer
    for layer_idx, z in enumerate(schedule):
        segments = slice_mesh_at_z(mesh, z)
        
        # If no intersections exist, still emit a record but with empty geometry.
        # This prevents metadata desync, although downstream code may choose to prune.
        records.append(SlicedLayerRecord(
            chunk_idx=chunk_idx,
            layer_idx=layer_idx,
            z_height=z,
            transform_matrix=transform_matrix,
            segments=segments
        ))
        
    return records
