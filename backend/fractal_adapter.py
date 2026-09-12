from pose_model import LogicalPose
from enums import RotationConvention

class FractalABAdapter:
    """
    Adapter for Fractal 5-axis Klipper profiles.
    Strictly maps the LogicalPose directly into stepper_a (A) and stepper_b (B).
    It rejects any implicit translation from U/V coordinates, enforcing a
    direct mathematical mapping from the LogicalPose.
    """
    def __init__(self, contract: dict):
        self.contract = contract
        
        required_axes = {"X", "Y", "Z", "A", "B"}
        provided_axes = set(self.contract.get("axis_names", []))
        
        if not required_axes.issubset(provided_axes):
            raise ValueError(f"Fractal adapter requires explicit A and B axes. Contract provided: {provided_axes}")

    def adapt_pose(self, pose: LogicalPose) -> dict:
        """
        Takes a LogicalPose and returns the explicit G-Code arguments
        for stepper_a and stepper_b.
        Rejects poses that do not explicitly map to A/B axes.
        """
        if pose.convention == RotationConvention.AB_HEAD:
            a_val = pose.angles[0]
            b_val = pose.angles[1]
        elif pose.convention == RotationConvention.BC_TABLE:
            raise ValueError("Fractal adapter cannot safely map BC_TABLE to A/B axes.")
        elif pose.convention == RotationConvention.AC_TABLE:
            raise ValueError("Fractal adapter cannot safely map AC_TABLE to A/B axes.")
        else:
            raise ValueError(f"Unsupported convention for Fractal adapter: {pose.convention}")

        return {
            "A": a_val,
            "B": b_val
        }
