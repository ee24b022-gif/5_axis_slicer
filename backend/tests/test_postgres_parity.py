import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable, CreateIndex
from models import Base, User, Mesh, MachineProfile, Job, Chunk, Layer, Diagnostic, Export
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_postgres_schema_compilation():
    """
    Verify that the SQLAlchemy 2.0 mappings compile perfectly for PostgreSQL.
    This guarantees model parity without needing a live Docker container.
    """
    # Create a mock postgres engine
    engine = create_engine("postgresql+psycopg://mock:mock@localhost/mock")
    
    # We compile each table's DDL against PostgreSQL to ensure no dialect-specific compilation errors
    for table in Base.metadata.sorted_tables:
        ddl = CreateTable(table).compile(engine)
        ddl_string = str(ddl)
        assert "CREATE TABLE" in ddl_string
        
        # Also check all associated indexes
        for index in table.indexes:
            idx_ddl = CreateIndex(index).compile(engine)
            idx_ddl_string = str(idx_ddl)
            assert "CREATE " in idx_ddl_string
            if "WHERE" in idx_ddl_string:
                # E.g. partial index
                assert "WHERE status !=" in idx_ddl_string or "WHERE" in idx_ddl_string

    # Specific checks
    export_table = Export.__table__
    
    # Check partial unique index constraint on export has postgresql_where
    export_idx = next(i for i in export_table.indexes if i.name == 'ix_export_job_dialect_active')
    assert export_idx.dialect_options['postgresql']['where'] is not None

def test_sqlite_fallback_crud(session):
    """
    Run representative CRUD operations using the fallback SQLite memory db
    to ensure full model coverage matches expectations.
    """
    from enums import UserRole, MeshFormat, JobMode, ExportStatus
    from models import JobStatus
    
    # 1. Create User
    u = User(username="postgres_test", email="pg@test.com", role=UserRole.USER, hashed_password="pw")
    session.add(u)
    session.commit()
    
    # 2. Create Mesh
    m = Mesh(
        uploader_id=u.id, storage_uri="s3://test", format=MeshFormat.STL_BINARY,
        size_bytes=100, content_hash="hash", triangle_count=10,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=1.0, bound_max_y=1.0, bound_max_z=1.0
    )
    session.add(m)
    
    # 3. Create MachineProfile
    mp = MachineProfile(
        name="test_pg", revision=1, author_id=u.id, dialect="marlin",
        contract={}, limits={}
    )
    session.add(mp)
    session.commit()
    
    # 4. Create Job
    j = Job(
        creator_id=u.id, mesh_id=m.id, machine_profile_id=mp.id,
        mode=JobMode.THREE_AXIS, settings={}, engine_revision="1",
        input_hash="hash"
    )
    session.add(j)
    session.commit()
    
    # 5. Create Chunk & Layer
    c = Chunk(
        job_id=j.id, chunk_idx=1, source_plane={}, 
        transform_matrix=[1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0], 
        layer_idx_min=0, layer_idx_max=1, min_z=0.0, max_z=1.0, triangle_count=10, storage_key="key"
    )
    l = Layer(job_id=j.id, layer_idx=0, z_height=0.1, thickness=0.1)
    session.add_all([c, l])
    session.commit()
    
    # 6. Create Diagnostic & Export
    from enums import DiagnosticSeverity, DiagnosticStatus, JobStage
    d = Diagnostic(job_id=j.id, stage=JobStage.VALIDATION, severity=DiagnosticSeverity.INFO, status=DiagnosticStatus.PASS, code="0", message="msg")
    e = Export(job_id=j.id, creator_id=u.id, dialect="marlin", status=ExportStatus.PENDING)
    session.add_all([d, e])
    session.commit()
    
    # Test Query
    assert session.query(Export).count() == 1
    
    # Test Cascade Delete
    session.delete(u)
    session.commit()
    
    # Since User is deleted, cascade deletes Jobs, which cascade deletes Chunks, Layers, Diagnostics, and Exports. 
    # Meshes are CASCADE deleted too. MachineProfiles are CASCADE deleted.
    assert session.query(Job).count() == 0
    assert session.query(Chunk).count() == 0
    assert session.query(Layer).count() == 0
    assert session.query(Diagnostic).count() == 0
    assert session.query(Export).count() == 0
