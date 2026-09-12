import math
import trimesh
from typing import List
from slice_plane_model import SlicePlane
from enums import AngleUnit, RotationConvention

class AutoSegmenter:
    @staticmethod
    def compute_segmentation(mesh: trimesh.Trimesh, enable_auto_segment: bool = True) -> List[SlicePlane]:
        """
        Analyzes a mesh for downward-facing overhangs that cannot be printed horizontally.
        If found and auto_segment is enabled, it returns two SlicePlanes:
        1. A base horizontal plane (cut horizontally below the overhang).
        2. A 45-degree tilted plane pointing towards the overhang's center of mass.
        
        If no overhangs or disabled, returns a single horizontal base plane.
        """
        # Default horizontal base plane
        base_plane = SlicePlane(
            plane_origin=(0.0, 0.0, 0.0),
            unit_normal=(0.0, 0.0, 1.0),
            angle_pair=(0.0, 0.0),
            angle_units=AngleUnit.DEGREES,
            rotation_convention=RotationConvention.BC_TABLE,
            local_x=(1.0, 0.0, 0.0),
            local_y=(0.0, 1.0, 0.0),
            source_frame="canonical"
        )
        
        if not enable_auto_segment:
            return [base_plane]
            
        bounds = mesh.bounds
        min_z = float(bounds[0][2])
        
        # 1. Detect overhangs
        # Downward facing normal (nz < -0.5) and above the base plate (Z > min_z + 2.0)
        overhang_faces = []
        for i, face in enumerate(mesh.faces):
            normal = mesh.face_normals[i]
            if normal[2] < -0.5:
                # Find the minimum Z of this face's vertices
                face_vertices = mesh.vertices[face]
                fz_min = float(face_vertices[:, 2].min())
                if fz_min > min_z + 2.0:
                    overhang_faces.append(i)
                    
        if not overhang_faces:
            return [base_plane]
            
        # 2. Compute cutoff and direction
        # Find the absolute lowest point of any overhang face
        lowest_z = min(float(mesh.vertices[mesh.faces[f]][:, 2].min()) for f in overhang_faces)
        calc_z_cutoff = max(min_z + 2.0, lowest_z - 2.0)
        
        # Find the center of mass of the overhang faces
        o_min_x = min(float(mesh.vertices[mesh.faces[f]][:, 0].min()) for f in overhang_faces)
        o_max_x = max(float(mesh.vertices[mesh.faces[f]][:, 0].max()) for f in overhang_faces)
        o_min_y = min(float(mesh.vertices[mesh.faces[f]][:, 1].min()) for f in overhang_faces)
        o_max_y = max(float(mesh.vertices[mesh.faces[f]][:, 1].max()) for f in overhang_faces)
        
        o_cx = (o_min_x + o_max_x) / 2.0
        o_cy = (o_min_y + o_max_y) / 2.0
        
        base_cx = float(mesh.centroid[0]) if hasattr(mesh, 'centroid') and mesh.centroid is not None else (bounds[0][0] + bounds[1][0]) / 2.0
        base_cy = float(mesh.centroid[1]) if hasattr(mesh, 'centroid') and mesh.centroid is not None else (bounds[0][1] + bounds[1][1]) / 2.0
        
        dx = o_cx - base_cx
        dy = o_cy - base_cy
        length = math.hypot(dx, dy)
        
        if length > 1e-4:
            tilt_dir_x = dx / length
            tilt_dir_y = dy / length
        else:
            tilt_dir_x = 1.0
            tilt_dir_y = 0.0
            
        # 3. Create tilted plane configuration
        tilt_angle_deg = 45.0
        tilt_angle_rad = math.radians(tilt_angle_deg)
        
        # The plane is tilted 45 degrees along the (tilt_dir_x, tilt_dir_y) vector.
        # Its normal is the Z-vector rotated by -45 degrees around the perpendicular cross product vector.
        # However, mathematically simpler:
        # Tilt direction is T = (tilt_dir_x, tilt_dir_y, 0).
        # We tilt the Z axis towards T.
        # Normal will be: (-tilt_dir_x * sin(45), -tilt_dir_y * sin(45), cos(45))
        sin45 = math.sin(tilt_angle_rad)
        cos45 = math.cos(tilt_angle_rad)
        nx = -tilt_dir_x * sin45
        ny = -tilt_dir_y * sin45
        nz = cos45
        
        # Determine local axes to satisfy orthogonality
        # Project world X/Y onto the plane or define explicitly using cross products
        # A simple valid frame:
        # Cross normal with Z to get a local axis (if normal isn't Z)
        # Vector perpendicular to tilt direction is V = (-tilt_dir_y, tilt_dir_x, 0)
        # This V remains flat in XY plane and orthogonal to normal.
        local_x = (-tilt_dir_y, tilt_dir_x, 0.0)
        
        # Cross normal with local_x to get local_y
        # local_y = normal x local_x
        ly_x = ny * local_x[2] - nz * local_x[1]
        ly_y = nz * local_x[0] - nx * local_x[2]
        ly_z = nx * local_x[1] - ny * local_x[0]
        local_y = (ly_x, ly_y, ly_z)
        
        tilted_plane = SlicePlane(
            plane_origin=(0.0, 0.0, calc_z_cutoff),
            unit_normal=(nx, ny, nz),
            angle_pair=(tilt_angle_deg, 0.0), # Assuming abstract machine angles for now
            angle_units=AngleUnit.DEGREES,
            rotation_convention=RotationConvention.BC_TABLE,
            local_x=local_x,
            local_y=local_y,
            source_frame="canonical"
        )
        
        return [base_plane, tilted_plane]
