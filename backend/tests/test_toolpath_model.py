import pytest
from pydantic import ValidationError
from toolpath_model import ToolpathJob, ToolpathLayer, ToolpathSegment, PathCategory

def test_serialization_preserves_typing():
    # Construct a fully typed nested structure
    job = ToolpathJob(
        job_id="test_job_1",
        layers=[
            ToolpathLayer(
                layer_id=0,
                z_height=0.2,
                paths=[
                    ToolpathSegment(
                        path_id=0, 
                        category=PathCategory.PERIMETER, 
                        coords=[(0.0, 0.0), (10.0, 0.0)]
                    ),
                    ToolpathSegment(
                        path_id=1, 
                        category=PathCategory.TRAVEL, 
                        coords=[(10.0, 0.0), (15.0, 0.0)]
                    )
                ]
            )
        ]
    )
    
    # Dump to raw JSON (dictionary loss simulation)
    raw_json = job.model_dump_json()
    
    # Re-parse from raw JSON
    reconstructed = ToolpathJob.model_validate_json(raw_json)
    
    # Verify typing survived cleanly
    assert reconstructed.job_id == "test_job_1"
    assert len(reconstructed.layers) == 1
    assert reconstructed.layers[0].z_height == 0.2
    
    paths = reconstructed.layers[0].paths
    assert len(paths) == 2
    
    # Assert Enums stayed Enums, not random strings!
    assert isinstance(paths[0].category, PathCategory)
    assert paths[0].category == PathCategory.PERIMETER
    assert paths[0].coords == [(0.0, 0.0), (10.0, 0.0)]
    
    assert paths[1].category == PathCategory.TRAVEL

def test_invalid_category_rejection():
    # Attempting to assign an unsupported dictionary property should trigger Pydantic
    bad_data = {
        "job_id": "test_job_2",
        "layers": [
            {
                "layer_id": 0,
                "z_height": 0.2,
                "paths": [
                    {
                        "path_id": 0,
                        "category": "magic_infill",  # INVALID Enum
                        "coords": [(0,0)]
                    }
                ]
            }
        ]
    }
    
    with pytest.raises(ValidationError) as exc:
        ToolpathJob.model_validate(bad_data)
        
    err_str = str(exc.value)
    assert "category" in err_str
    assert "Input should be 'perimeter', 'solid_infill', 'internal_infill', 'brim' or 'travel'" in err_str
