import pytest
from layer_schedule import generate_layer_schedule

def test_deterministic_schedule():
    # Slicing from 0.0 to 1.0 with layer_height=0.2 (default half_layer_offset=True)
    heights = generate_layer_schedule(
        z_min=0.0, z_max=1.0, layer_height=0.2, half_layer_offset=True
    )
    # Expected slices exactly at: 0.1, 0.3, 0.5, 0.7, 0.9
    assert len(heights) == 5
    assert heights == [0.1, 0.3, 0.5, 0.7, 0.9]

def test_first_layer_override():
    # Slicing from 0.0 to 1.0 with first_layer_height=0.3, layer_height=0.2
    heights = generate_layer_schedule(
        z_min=0.0, z_max=1.0, layer_height=0.2, first_layer_height=0.3, half_layer_offset=True
    )
    # Expected slices: 0.15 (first), 0.4 (second), 0.6 (third), 0.8 (fourth)
    # The next top would be 0.3 + (4 * 0.2) = 1.1, slice would be at 1.0, wait...
    # Layer 0: [0.0, 0.3], slice=0.15
    # Layer 1: [0.3, 0.5], slice=0.4
    # Layer 2: [0.5, 0.7], slice=0.6
    # Layer 3: [0.7, 0.9], slice=0.8
    # Layer 4: [0.9, 1.1], slice=1.0. Does 1.0 <= z_max(1.0)? Yes. So 1.0 is included.
    assert len(heights) == 5
    assert heights == [0.15, 0.4, 0.6, 0.8, 1.0]

def test_no_half_layer():
    # Slicing from 0.0 to 1.0 with layer_height=0.2, first_layer=0.3, offset=False
    heights = generate_layer_schedule(
        z_min=0.0, z_max=1.0, layer_height=0.2, first_layer_height=0.3, half_layer_offset=False
    )
    # Expected slices: 0.3 (first), 0.5, 0.7, 0.9
    assert len(heights) == 4
    assert heights == [0.3, 0.5, 0.7, 0.9]

def test_invalid_heights():
    with pytest.raises(ValueError, match="layer_height must be strictly positive"):
        generate_layer_schedule(0.0, 1.0, layer_height=-0.1)
        
    with pytest.raises(ValueError, match="layer_height must be strictly positive"):
        generate_layer_schedule(0.0, 1.0, layer_height=0.0)
        
    with pytest.raises(ValueError, match="first_layer_height must be strictly positive"):
        generate_layer_schedule(0.0, 1.0, layer_height=0.2, first_layer_height=0.0)

def test_inverted_bounds():
    # z_min >= z_max should return empty schedule
    heights = generate_layer_schedule(1.0, 0.0, layer_height=0.2)
    assert heights == []
