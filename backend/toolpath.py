import numpy as np

def generate_zig_zag_toolpath_on_mesh(mesh, line_width, y_step=1.0):
    """
    Projects a 2D zig-zag grid downwards onto the 3D mesh to generate a conformal toolpath.
    Returns a list of (x, y, z, nx, ny, nz).
    """
    min_b, max_b = mesh.bounds
    z_start = max_b[2] + 10.0 # Start rays 10mm above the highest point
    
    # Generate 2D zig-zag points in XY plane
    x_coords = np.arange(min_b[0], max_b[0], line_width)
    y_coords = np.arange(min_b[1], max_b[1], y_step) # Configurable resolution
    
    ray_origins = []
    for i, x in enumerate(x_coords):
        # Alternate direction for zig-zag
        y_pts = y_coords if i % 2 == 0 else y_coords[::-1]
        for y in y_pts:
            ray_origins.append([x, y, z_start])
            
    if not ray_origins:
        return []
        
    ray_origins = np.array(ray_origins)
    ray_directions = np.tile([0, 0, -1], (len(ray_origins), 1))
    
    # Raycast down onto the mesh
    locations, index_ray, index_tri = mesh.ray.intersects_location(
        ray_origins=ray_origins,
        ray_directions=ray_directions
    )
    
    if len(locations) == 0:
        return []
        
    normals = mesh.face_normals[index_tri]
    
    # If a ray intersects multiple times (e.g. hollow object), we take the top-most intersection (max Z)
    best_points = {}
    for loc, ray_idx, norm in zip(locations, index_ray, normals):
        if ray_idx not in best_points or loc[2] > best_points[ray_idx]['z']:
            best_points[ray_idx] = {
                'x': float(loc[0]), 'y': float(loc[1]), 'z': float(loc[2]),
                'nx': float(norm[0]), 'ny': float(norm[1]), 'nz': float(norm[2])
            }
            
    # Reassemble path in the zig-zag order
    path = []
    for i in range(len(ray_origins)):
        if i in best_points:
            pt = best_points[i]
            path.append((pt['x'], pt['y'], pt['z'], pt['nx'], pt['ny'], pt['nz']))
            
    return path
