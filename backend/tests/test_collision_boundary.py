import pytest
from validation_service import ValidationService
from enums import DiagnosticStatus
from models import CollisionReport

class MockCollisionEngine:
    def __init__(self, should_collide=False):
        self.should_collide = should_collide

    def sweep_check_path(self, path):
        if self.should_collide:
            return [CollisionReport(
                path_id=1,
                layer_idx=1,
                point_index=0,
                clearance=-1.0,
                limiting_surface="bed",
                suggested_remedy="remedy"
            )]
        return []

def test_endpoint_collision_failure():
    engine = MockCollisionEngine(should_collide=True)
    res = ValidationService.validate_endpoint_collision(engine, None)
    
    assert res.aggregate_status == DiagnosticStatus.FAIL
    assert res.is_blocking is True
    assert len(res.diagnostics) == 1
    assert res.diagnostics[0].code == "ENDPOINT_COLLISION_DETECTED"
    assert res.diagnostics[0].details["limiting_surface"] == "bed"

def test_endpoint_collision_pass():
    engine = MockCollisionEngine(should_collide=False)
    res = ValidationService.validate_endpoint_collision(engine, None)
    
    assert res.aggregate_status == DiagnosticStatus.PASS
    assert res.is_blocking is False
    assert len(res.diagnostics) == 0

def test_swept_volume_blocks():
    res = ValidationService.validate_swept_volume_collision(None)
    
    assert res.aggregate_status == DiagnosticStatus.NOT_IMPLEMENTED
    assert res.is_blocking is True
    assert len(res.diagnostics) == 1
    assert res.diagnostics[0].code == "SWEPT_VOLUME_NOT_IMPLEMENTED"
