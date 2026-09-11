import numpy as np
from typing import List, Optional
from models import SlicerMachineProfile, MachinePose, CollisionReport, FeaturePath
from bvh import MeshBVH

class CollisionEngine:
    def __init__(self, profile: SlicerMachineProfile, part_bvh: MeshBVH, bed_center_z: float = 0.0):
        self.profile = profile
        self.part_bvh = part_bvh
        self.bed_center_z = bed_center_z
        
        # Bed plane is at Z = -bed_center_z in the part coordinate system
        self.bed_z = -bed_center_z

    def check_bed_collision(self, x: float, y: float, z: float, nx: float, ny: float, nz: float) -> bool:
        """
        Check if the tool (nozzle + holder) intersects the flat print bed.
        The nozzle tip is at (x, y, z). It extends backwards along (nx, ny, nz) 
        for a distance of nozzle_length.
        """
        tip_z = z
        tail_z = z + nz * self.profile.nozzle_length
        
        if tip_z < self.bed_z or tail_z < self.bed_z:
            return True
            
        # Check the holder radius at the tail against the bed
        # The lowest point of the holder disk:
        # We find a vector perpendicular to N that points most downwards
        if abs(nz) < 0.9999:
            # Vector in XY plane pointing opposite to N's XY projection gives lowest Z when tilted?
            # Actually, the worst-case drop in Z for a disk of radius R tilted by angle theta is R * sin(theta)
            # sin(theta) = sqrt(nx^2 + ny^2)
            sin_theta = np.sqrt(nx**2 + ny**2)
            lowest_holder_z = tail_z - self.profile.nozzle_holder_radius * sin_theta
            if lowest_holder_z < self.bed_z:
                return True
                
        return False

    def validate_pose(self, x: float, y: float, z: float, nx: float, ny: float, nz: float) -> Optional[str]:
        """
        Returns a string describing the collision, or None if safe.
        """
        if self.check_bed_collision(x, y, z, nx, ny, nz):
            return "bed"
            
        # Part collision check using the BVH
        p_start = np.array([x, y, z]) + np.array([nx, ny, nz]) * 1.0
        p_end = p_start + np.array([nx, ny, nz]) * self.profile.nozzle_length
        
        # We use nozzle_holder_radius as a conservative envelope for the whole nozzle length
        # Only check the top of the nozzle (the holder) against the mesh.
        # The nozzle tip is meant to be touching the mesh, so a full capsule test fails immediately.
        # We check if the holder itself (at p_end) is within its radius of the mesh.
        dist = self.part_bvh.query_distance(np.array([p_end]))[0]
        if dist < self.profile.nozzle_holder_radius:
            return "part"
            
        return None

    def sweep_check_path(self, path: FeaturePath) -> List[CollisionReport]:
        """
        Validates an entire FeaturePath. Returns a list of collisions (empty if safe).
        """
        reports = []
        for i, pt in enumerate(path.points):
            x, y, z = pt
            nx, ny, nz = path.normals[i]
            
            collision = self.validate_pose(x, y, z, nx, ny, nz)
            if collision:
                reports.append(CollisionReport(
                    path_id=path.path_id,
                    layer_idx=path.layer_idx,
                    point_index=i,
                    clearance=-1.0, # Not explicitly calculated in simple boolean test
                    limiting_surface=collision,
                    suggested_remedy="Change orientation or limit amplitude."
                ))
                break # Only report the first collision per path to avoid spam
                
        return reports
