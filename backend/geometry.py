import numpy as np
import trimesh

class ConformalGeometry:
    def __init__(self, mesh_path):
        """
        Initialize with a substrate mesh.
        """
        self.mesh = trimesh.load(mesh_path)
        if not self.mesh.is_watertight:
            print("Warning: Mesh is not watertight. Normals might be inconsistent.")
            
    def get_surface_point_and_normal(self, point):
        """
        Finds the closest point on the mesh surface and its corresponding unit normal.
        """
        closest_point, distance, triangle_id = self.mesh.nearest.on_surface([point])
        normal = self.mesh.face_normals[triangle_id[0]]
        return closest_point[0], normal

    def generate_conformal_layer(self, height):
        """
        Generates an offset surface representing a conformal layer.
        For a simple implementation, we can just offset the vertices along their normals.
        """
        # For a robust slicer, we'd need more complex offsetting (e.g. Minkowski sum),
        # but vertex offsetting works for simple, smooth substrates.
        offset_vertices = self.mesh.vertices + self.mesh.vertex_normals * height
        offset_mesh = trimesh.Trimesh(vertices=offset_vertices, faces=self.mesh.faces)
        return offset_mesh
