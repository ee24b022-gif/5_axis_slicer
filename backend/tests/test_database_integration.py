import os
import pytest
import socket
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from alembic.config import Config
from alembic import command
from enums import UserRole, MeshFormat, JobMode, ExportStatus
from models import User, Mesh, MachineProfile, Job, Chunk, Export, JobStatus

TEST_DB_URL = os.environ.get("DATABASE_TEST_URL", "postgresql+psycopg://slicer_test:slicer_password@localhost:5432/slicer_test_db")

def check_postgres_connection(url: str) -> bool:
    """Attempt to connect to the PostgreSQL port to check availability."""
    try:
        # Extract host and port from simple postgres URL
        # Format: postgresql+psycopg://user:pass@host:port/dbname
        parts = url.split("@")
        if len(parts) > 1:
            host_port = parts[1].split("/")[0]
            if ":" in host_port:
                host, port = host_port.split(":")
                port = int(port)
            else:
                host = host_port
                port = 5432
            
            s = socket.create_connection((host, port), timeout=1)
            s.close()
            return True
    except Exception:
        pass
    return False

pg_available = check_postgres_connection(TEST_DB_URL)
pytestmark = pytest.mark.skipif(not pg_available, reason="PostgreSQL test database unavailable on port 5432")

@pytest.fixture(scope="module")
def postgres_engine():
    engine = create_engine(TEST_DB_URL, isolation_level="AUTOCOMMIT")
    # To run migrations cleanly, we should ideally drop all tables first
    if pg_available:
        with engine.connect() as conn:
            # Drop schema cascade to clear previous runs
            conn.execute(text("DROP SCHEMA public CASCADE;"))
            conn.execute(text("CREATE SCHEMA public;"))
            # In postgres image public is usually granted
            
    yield engine
    engine.dispose()

@pytest.fixture(scope="module")
def alembic_runner(postgres_engine):
    ini_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
    alembic_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic")
    
    cfg = Config(ini_path)
    cfg.set_main_option("script_location", alembic_dir)
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    
    return cfg

@pytest.fixture
def db_session(postgres_engine, alembic_runner):
    # Make sure we are at head
    command.upgrade(alembic_runner, "head")
    
    SessionLocal = sessionmaker(bind=postgres_engine)
    session = SessionLocal()
    
    yield session
    
    session.rollback()
    session.close()
    
    # Clean up all tables for next test
    with postgres_engine.connect() as conn:
        for table_name in inspect(postgres_engine).get_table_names():
            if table_name != "alembic_version":
                conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))

def test_alembic_upgrade_head_clean_slate(alembic_runner, postgres_engine):
    # Already upgraded in fixture, but we can downgrade and upgrade
    command.downgrade(alembic_runner, "base")
    inspector = inspect(postgres_engine)
    assert "users" not in inspector.get_table_names()
    
    command.upgrade(alembic_runner, "head")
    inspector = inspect(postgres_engine)
    assert "users" in inspector.get_table_names()
    assert "jobs" in inspector.get_table_names()

def _create_mock_job(session):
    u = User(username="pg_integration", email="pg@test.com", role=UserRole.USER, hashed_password="pw")
    session.add(u)
    session.flush()
    
    m = Mesh(
        uploader_id=u.id, storage_uri="s3://test", format=MeshFormat.STL_BINARY,
        size_bytes=100, content_hash="hash", triangle_count=10,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=1.0, bound_max_y=1.0, bound_max_z=1.0
    )
    session.add(m)
    session.flush()
    
    mp = MachineProfile(
        name="test_pg", revision=1, author_id=u.id, dialect="marlin",
        contract={"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X"], "axis_directions": {"X": 1}, "zero_positions": {"X": 0.0}, "command_templates": {"linear_move": "G1"}}, limits={"ranges": {"X": (0, 300)}}
    )
    session.add(mp)
    session.flush()
    
    j = Job(
        creator_id=u.id, mesh_id=m.id, machine_profile_id=mp.id,
        mode=JobMode.THREE_AXIS, settings={}, engine_revision="1",
        input_hash="hash", status=JobStatus.PENDING
    )
    session.add(j)
    session.commit()
    return j, u

def test_partial_unique_index_export_job_dialect_active(db_session):
    job, user = _create_mock_job(db_session)
    
    e1 = Export(job_id=job.id, creator_id=user.id, dialect="marlin", status=ExportStatus.PENDING)
    db_session.add(e1)
    db_session.commit()
    
    # Adding another active export for same job and dialect should fail due to unique partial index
    e2 = Export(job_id=job.id, creator_id=user.id, dialect="marlin", status=ExportStatus.PENDING)
    db_session.add(e2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    
    # However, if one is revoked, we can add a new one
    e1.status = ExportStatus.REVOKED
    db_session.add(e1)
    db_session.commit()
    
    e3 = Export(job_id=job.id, creator_id=user.id, dialect="marlin", status=ExportStatus.PENDING)
    db_session.add(e3)
    db_session.commit() # Should succeed

def test_foreign_key_chunk_job_cascade_behavior(db_session):
    job, user = _create_mock_job(db_session)
    
    c = Chunk(
        job_id=job.id, chunk_idx=1, source_plane={}, 
        transform_matrix=[1.0]*16, 
        layer_idx_min=0, layer_idx_max=1, min_z=0.0, max_z=1.0, triangle_count=10, storage_key="key"
    )
    db_session.add(c)
    db_session.commit()
    
    assert db_session.query(Chunk).count() == 1
    
    # Delete job and ensure chunk is deleted (ON DELETE CASCADE)
    db_session.delete(job)
    db_session.commit()
    
    assert db_session.query(Chunk).count() == 0

from job_lifecycle import JobLifecycle, InvalidTransitionError

def test_invalid_job_terminal_status_transition(db_session):
    job, user = _create_mock_job(db_session)
    
    # 1. Properly sequence the job to a terminal state
    JobLifecycle.start_job(db_session, job)
    JobLifecycle.complete_job(db_session, job)
    db_session.commit()
    
    # 2. Test that COMPLETE -> RUNNING fails
    with pytest.raises(InvalidTransitionError, match="Cannot transition"):
        JobLifecycle.start_job(db_session, job)
        
    # 3. Test that COMPLETE -> CANCELLED fails (Replaces the 2nd ValueError block)
    with pytest.raises(InvalidTransitionError, match="Cannot transition"):
        JobLifecycle.cancel_job(db_session, job)
        
    db_session.rollback()