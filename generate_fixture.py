import json
import math
import os

layers = []
num_layers = 20

for i in range(num_layers):
    z = (i + 1) * 0.2
    layer_data = {
        "layer_idx": i,
        "z_height": z,
        "paths": []
    }
    
    radius = 20.0
    
    # Brim (only on layer 0)
    if i == 0:
        brim_points = []
        for j in range(65):
            angle = (j / 64) * 2 * math.pi
            brim_points.extend([math.cos(angle) * (radius + 2.0), math.sin(angle) * (radius + 2.0), z])
        layer_data["paths"].append({"type": "brim", "points": brim_points})

    # Shell
    shell_points = []
    for j in range(65):
        angle = (j / 64) * 2 * math.pi
        shell_points.extend([math.cos(angle) * radius, math.sin(angle) * radius, z])
    layer_data["paths"].append({"type": "shell", "points": shell_points})
    
    # Internal infill (grid pattern)
    infill_points = []
    if i % 2 == 0:
        # horizontal lines
        for y in range(-15, 16, 5):
            x = math.sqrt(radius**2 - y**2)
            infill_points.extend([-x, y, z, x, y, z])
    else:
        # vertical lines
        for x in range(-15, 16, 5):
            y = math.sqrt(radius**2 - x**2)
            infill_points.extend([x, -y, z, x, y, z])
            
    layer_data["paths"].append({"type": "internal_infill", "points": infill_points})
    
    # Solid infill (top/bottom layers)
    if i < 2 or i > num_layers - 3:
        solid_points = []
        for r in range(5, 18, 2):
            for j in range(33):
                angle = (j / 32) * 2 * math.pi
                solid_points.extend([math.cos(angle) * r, math.sin(angle) * r, z])
        layer_data["paths"].append({"type": "solid_infill", "points": solid_points})
        
    # Travel
    layer_data["paths"].append({"type": "travel", "points": [radius, 0, z, radius+5, 0, z+0.5]})
    
    layers.append(layer_data)

data = {
    "bounds": {"min": [-25, -25, 0], "max": [25, 25, 20 * 0.2]},
    "layers": layers,
    "chunk_boundaries": [
        {"idx": 0, "z_min": 0.0, "z_max": 2.0},
        {"idx": 1, "z_min": 2.0, "z_max": 4.0}
    ]
}

os.makedirs('frontend/public', exist_ok=True)
with open('frontend/public/preview_fixture.json', 'w') as f:
    json.dump(data, f)
    
print("Generated frontend/public/preview_fixture.json")
