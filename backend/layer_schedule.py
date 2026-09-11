import numpy as np
from typing import List, Optional

def generate_layer_schedule(
    z_min: float,
    z_max: float,
    layer_height: float,
    first_layer_height: Optional[float] = None,
    half_layer_offset: bool = True
) -> List[float]:
    """
    Computes a deterministic physical Z-height slicing schedule for a 3D geometry.
    
    Args:
        z_min (float): The absolute bottom bound of the geometry.
        z_max (float): The absolute top bound of the geometry.
        layer_height (float): Standard vertical thickness for consecutive slices.
        first_layer_height (Optional[float]): Independent height explicitly applied to the first layer.
        half_layer_offset (bool): If True, positions slicing planes directly through the vertical 
                                  volumetric center of each layer. If False, slices at the exact top.
                                  
    Returns:
        List[float]: Series of ascending absolute Z coordinates rounded to 5 decimal places.
    """
    if layer_height <= 0:
        raise ValueError(f"layer_height must be strictly positive. Got {layer_height}")
        
    first_lh = first_layer_height if first_layer_height is not None else layer_height
    if first_lh <= 0:
        raise ValueError(f"first_layer_height must be strictly positive. Got {first_lh}")
        
    if z_min >= z_max:
        return []
        
    heights = []
    
    # Define absolute slice offset per layer mode
    offset_first = first_lh / 2.0 if half_layer_offset else first_lh
    offset_standard = layer_height / 2.0 if half_layer_offset else layer_height
    
    # Process First Layer
    slice_z = round(z_min + offset_first, 5)
    if slice_z <= round(z_max, 5):
        heights.append(slice_z)
        
    # Standard Layer Traversal
    current_layer_bottom = z_min + first_lh
    layer_index = 0
    
    while round(current_layer_bottom, 5) < round(z_max, 5):
        # Use iterative index multiplication to absolutely prevent floating point sum accumulation drift
        slice_z = round(z_min + first_lh + (layer_index * layer_height) + offset_standard, 5)
        
        if slice_z <= round(z_max, 5):
            heights.append(slice_z)
        
        # Advance state
        layer_index += 1
        current_layer_bottom = z_min + first_lh + (layer_index * layer_height)
        
    return heights
