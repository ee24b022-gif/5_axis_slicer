import math

cz = 38.0
calc_segment_tilt = 45.0
c, s = math.cos(calc_segment_tilt * math.pi / 180.0), math.sin(calc_segment_tilt * math.pi / 180.0)

def rotate_pt(px, py, pz): return (px, py * c - (pz - cz) * s, py * s + (pz - cz) * c + cz)
def inverse_rotate_pt(px, py, pz): return (px, py * c + (pz - cz) * s, -py * s + (pz - cz) * c + cz)

# Original point on mesh
orig = (0.0, 0.0, 40.0)
print("Original:", orig)

# Rotate
rot = rotate_pt(*orig)
print("Rotated:", rot)

# Slice horizontally
z_base = rot[2]
sliced_pt = (rot[0], rot[1])

# Inverse rotate
inv = inverse_rotate_pt(sliced_pt[0], sliced_pt[1], z_base)
print("Inversed:", inv)
