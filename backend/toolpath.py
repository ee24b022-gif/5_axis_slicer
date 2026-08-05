import numpy as np

def generate_spiral_toolpath_on_hemisphere(radius, line_width, center=(0, 0, 0)):
    """
    Generates a continuous spiral toolpath on a hemisphere.
    Returns a list of (x, y, z, nx, ny, nz).
    """
    path = []
    # Arc length between spiral arms = line_width
    # We want a spiral that covers the hemisphere from pole down to the equator.
    # r(t) = R * sin(phi)
    # z(t) = R * cos(phi)
    
    # We parameterize by the arc length along the surface to maintain constant line_width
    num_turns = (np.pi * radius / 2) / line_width
    max_theta = num_turns * 2 * np.pi
    
    # Generate points
    # d(theta) should vary so that the arc length on the surface is constant (~ resolution)
    resolution = 0.5  # mm distance between points
    
    theta = 0.0
    while theta <= max_theta:
        # phi is the angle from the top pole (0 to pi/2)
        phi = (theta / max_theta) * (np.pi / 2)
        
        # Current radius from z-axis
        r_current = radius * np.sin(phi)
        
        x = center[0] + r_current * np.cos(theta)
        y = center[1] + r_current * np.sin(theta)
        z = center[2] + radius * np.cos(phi)
        
        # Normal for a sphere is just the normalized position vector relative to center
        nx = x - center[0]
        ny = y - center[1]
        nz = z - center[2]
        
        # Normalize the normal vector
        norm = np.sqrt(nx**2 + ny**2 + nz**2)
        nx /= norm
        ny /= norm
        nz /= norm
        
        path.append((x, y, z, nx, ny, nz))
        
        # Advance theta by an amount that gives a surface arc length of `resolution`
        # arc length ds ~= radius * d_gamma
        # at phi, moving by d_theta covers horizontal distance r_current * d_theta
        # moving down covers R * d_phi
        # Since this is a simple approximation, we just advance theta such that the horizontal step is ~resolution
        # except near the pole where r_current is small.
        step = resolution / max(r_current, 0.1)
        theta += step
        
    return path
