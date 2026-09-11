import numpy as np

def generate_layer_schedule(z_min, z_max, layer_height, first_layer_height=None, half_layer_offset=True):
    if layer_height <= 0:
        raise ValueError("Layer height must be positive")
        
    first_lh = first_layer_height if first_layer_height is not None else layer_height
    if first_lh <= 0:
        raise ValueError("First layer height must be positive")
        
    if z_min >= z_max:
        return []
        
    heights = []
    current_z = z_min
    
    # First layer
    if half_layer_offset:
        slice_z = current_z + (first_lh / 2.0)
    else:
        slice_z = current_z + first_lh
        
    if slice_z > z_max:
        # If the object is thinner than the first layer
        if half_layer_offset and (current_z + first_lh >= z_max):
             # it might still get a slice if slice_z <= z_max. 
             # If slice_z > z_max, maybe no slice or just one slice?
             # Standard: only slice if slice_z <= z_max, OR slice at min(slice_z, z_max - epsilon)
             pass
             
    # Let's just generate standard heights
    current_top = z_min + first_lh
    if half_layer_offset:
        slice_z = z_min + first_lh / 2.0
    else:
        slice_z = current_top
        
    if slice_z <= z_max:
        heights.append(slice_z)
        
    while current_top < z_max:
        if half_layer_offset:
            slice_z = current_top + layer_height / 2.0
        else:
            slice_z = current_top + layer_height
            
        if slice_z <= z_max:
            heights.append(slice_z)
            
        current_top += layer_height
        
    return heights

print(generate_layer_schedule(0.0, 1.0, 0.2, 0.3, True))
print(generate_layer_schedule(0.0, 1.0, 0.2, 0.3, False))
