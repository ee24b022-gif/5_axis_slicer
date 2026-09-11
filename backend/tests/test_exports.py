import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from database import Base
from models import User, Mesh, MachineProfile, Job, Export, JobMode
from enums import UserRole, MeshFormat, ExportStatus

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def setup_entities(session):
    user = User(username="export_user", email="export@test.com", role=UserRole.USER, hashed_password="pw")
    session.add(user)
    session.commit()
    
    mesh = Mesh(
        uploader_id=user.id,
        storage_uri="s3://mesh",
        format=MeshFormat.STL_BINARY,
        size_bytes=1024,
        content_hash="hash1",
        triangle_count=100,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    session.add(mesh)
    
    mp = MachineProfile(
        name="test_machine",
        revision=1,
        author_id=user.id,
        dialect="marlin",
        contract={},
        limits={}
    )
    session.add(mp)
    session.commit()
    return user, mesh, mp


def test_export_creation(session):
    """Verify export can be created and bound to job."""
    user, mesh, mp = setup_entities(session)
    
    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=mp.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1.0",
        input_hash="hash"
    )
    session.add(job)
    session.commit()
    
    export = Export(
        job_id=job.id,
        creator_id=user.id,
        dialect="marlin",
        status=ExportStatus.PENDING
    )
    session.add(export)
    session.commit()
    
    assert export.id is not None
    assert export.job_id == job.id
    assert export.creator_id == user.id
    assert export.status == ExportStatus.PENDING
    assert export in job.exports
    assert export in user.exports


def test_export_ready_storage_uri_constraint(session):
    """Test that a ready export requires a storage_uri."""
    user, mesh, mp = setup_entities(session)
    
    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=mp.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1.0",
        input_hash="hash"
    )
    session.add(job)
    session.commit()
    
    export = Export(
        job_id=job.id,
        creator_id=user.id,
        dialect="marlin",
        status=ExportStatus.READY
        # storage_uri is None
    )
    session.add(export)
    
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_export_duplicate_dialect_constraint(session):
    """Test that partial unique index prevents multiple active exports for same job+dialect."""
    user, mesh, mp = setup_entities(session)
    
    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=mp.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1.0",
        input_hash="hash"
    )
    session.add(job)
    session.commit()
    
    # First export (active)
    export1 = Export(
        job_id=job.id,
        creator_id=user.id,
        dialect="marlin",
        status=ExportStatus.PENDING
    )
    session.add(export1)
    session.commit()
    
    # Second active export for same job/dialect should fail
    export2 = Export(
        job_id=job.id,
        creator_id=user.id,
        dialect="marlin",
        status=ExportStatus.PENDING
    )
    session.add(export2)
    
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    
    # But a revoked export and an active export should be fine
    export1.status = ExportStatus.REVOKED
    session.add(export1)
    session.commit()
    
    export3 = Export(
        job_id=job.id,
        creator_id=user.id,
        dialect="marlin",
        status=ExportStatus.PENDING
    )
    session.add(export3)
    session.commit() # Should succeed
    
    assert export3.id is not None
