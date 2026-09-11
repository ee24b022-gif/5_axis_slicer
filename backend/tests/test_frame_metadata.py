import pytest
import uuid
import numpy as np
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from schemas import FrameMetadata
from models import Base, Job, Export, User, Mesh, MachineProfile
from enums import JobMode, ExportStatus, UserRole, MeshFormat

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

@pytest.fixture
def frame_metadata_fixture():
    # A dummy 4x4 matrix
    matrix = (
        (1.0, 0.0, 0.0, 5.0),
        (0.0, 1.0, 0.0, 5.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0)
    )
    return FrameMetadata(
        input_hash="dummy_hash_123",
        transform_matrix=matrix,
        scale=1.0,
        rot_x_deg=0.0,
        rot_y_deg=0.0,
        rot_z_deg=0.0,
        trans_x=5.0,
        trans_y=5.0
    )

def create_dependencies(session: Session):
    user = User(
        username=f"test_{uuid.uuid4()}", 
        email=f"test_{uuid.uuid4()}@test.com", 
        hashed_password="pw", 
        role=UserRole.USER
    )
    session.add(user)
    session.flush()
    
    mesh = Mesh(
        uploader_id=user.id,
        content_hash=f"hash_{uuid.uuid4()}",
        storage_uri="s3://dummy/mesh.stl",
        format=MeshFormat.STL_BINARY,
        size_bytes=1000,
        triangle_count=10,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    session.add(mesh)
    session.flush()
    
    profile = MachineProfile(
        name=f"Profile {uuid.uuid4()}",
        revision=1,
        dialect="Marlin",
        contract={},
        limits={},
        author_id=user.id
    )
    session.add(profile)
    session.flush()
    return user, mesh, profile

def test_frame_metadata_job_persistence(session: Session, frame_metadata_fixture):
    user, mesh, profile = create_dependencies(session)
    # Setup job
    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=profile.id,
        mode=JobMode.THREE_AXIS,
        engine_revision="v1.0.0",
        input_hash="dummy_hash_123",
        # Serialize Pydantic to dict for SQLAlchemy JSON
        settings={"frame": frame_metadata_fixture.model_dump()}
    )
    session.add(job)
    session.commit()
    
    # Reload and validate
    session.refresh(job)
    
    raw_frame_dict = job.settings.get("frame")
    assert raw_frame_dict is not None
    
    # Deserialize back to Pydantic
    loaded_metadata = FrameMetadata.model_validate(raw_frame_dict)
    
    assert loaded_metadata.input_hash == "dummy_hash_123"
    assert loaded_metadata.trans_x == 5.0
    
    # Verify matrix structure matches exactly
    original_mat = np.array(frame_metadata_fixture.transform_matrix)
    loaded_mat = np.array(loaded_metadata.transform_matrix)
    np.testing.assert_almost_equal(original_mat, loaded_mat)


def test_frame_metadata_export_persistence(session: Session, frame_metadata_fixture):
    user, mesh, profile = create_dependencies(session)
    # Setup job to bind the export
    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=profile.id,
        mode=JobMode.THREE_AXIS,
        engine_revision="v1.0.0",
        input_hash="dummy_hash_123",
        settings={}
    )
    session.add(job)
    session.flush() # get job.id
    
    # Setup export
    export = Export(
        job_id=job.id,
        creator_id=user.id,
        dialect="GCODE_GENERIC",
        status=ExportStatus.PENDING,
        export_metadata={"frame": frame_metadata_fixture.model_dump()}
    )
    session.add(export)
    session.commit()
    
    session.refresh(export)
    
    raw_frame_dict = export.export_metadata.get("frame")
    assert raw_frame_dict is not None
    
    loaded_metadata = FrameMetadata.model_validate(raw_frame_dict)
    assert loaded_metadata.input_hash == "dummy_hash_123"
