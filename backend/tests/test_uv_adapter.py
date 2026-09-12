import pytest
import math
from uv_adapter import TableTableUVAdapter

def test_valid_ik_transform():
    adapter = TableTableUVAdapter(bed_center_z=10.0)
    
    # Simple straight-up normal
    mx, my, mz, rotary = adapter.calculate_ik(x=5.0, y=5.0, z=0.0, nx=0.0, ny=0.0, nz=1.0)
    
    assert math.isclose(rotary['u'], 0.0, abs_tol=1e-5)
    assert math.isclose(rotary['v'], 0.0, abs_tol=1e-5)
    assert math.isclose(mx, 5.0, abs_tol=1e-5)
    assert math.isclose(my, 5.0, abs_tol=1e-5)
    assert math.isclose(mz, 0.0, abs_tol=1e-5)

    # Normal tilted 90 degrees around X (points along Y)
    # So nx=0, ny=1, nz=0
    # U should be 90 degrees.
    mx, my, mz, rotary = adapter.calculate_ik(x=0.0, y=10.0, z=0.0, nx=0.0, ny=1.0, nz=0.0)
    assert math.isclose(rotary['u'], 90.0, abs_tol=1e-5)
    
def test_non_unit_normal_fails():
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    
    with pytest.raises(ValueError, match="Invalid non-unit normal vector"):
        adapter.calculate_ik(x=0.0, y=0.0, z=0.0, nx=1.0, ny=1.0, nz=1.0)
