from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from models import Base, User, Job, Mesh, MachineProfile, Export
from enums import UserRole, JobMode, ExportStatus, MeshFormat

engine = create_engine('sqlite:///:memory:', echo=True)
Base.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

user = User(username="u", email="u", role=UserRole.USER, hashed_password="p")
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
    name="test",
    revision=1,
    author_id=user.id,
    dialect="marlin",
    contract={},
    limits={}
)
session.add(mp)
session.commit()

job = Job(
    creator_id=user.id,
    mesh_id=mesh.id,
    machine_profile_id=mp.id,
    mode=JobMode.THREE_AXIS,
    settings={},
    engine_revision="1",
    input_hash="h"
)
session.add(job)
session.commit()

print("TEST 1: Check Constraint")
try:
    export = Export(
        job_id=job.id,
        creator_id=user.id,
        dialect="marlin",
        status=ExportStatus.READY
    )
    session.add(export)
    session.commit()
    print("TEST 1 FAILED: Did not raise")
except IntegrityError as e:
    print("TEST 1 PASSED:", e)
    session.rollback()

print("TEST 2: Unique Constraint")
try:
    export1 = Export(
        job_id=job.id,
        creator_id=user.id,
        dialect="marlin",
        status=ExportStatus.PENDING
    )
    session.add(export1)
    session.commit()
    print("Export 1 added")
    
    export2 = Export(
        job_id=job.id,
        creator_id=user.id,
        dialect="marlin",
        status=ExportStatus.PENDING
    )
    session.add(export2)
    session.commit()
    print("TEST 2 FAILED: allowed duplicate")
except IntegrityError as e:
    print("TEST 2 PASSED PART 1:", e)
    session.rollback()

try:
    export1.status = ExportStatus.REVOKED
    session.add(export1)
    session.commit()
    print("Export 1 revoked")
    
    export3 = Export(
        job_id=job.id,
        creator_id=user.id,
        dialect="marlin",
        status=ExportStatus.PENDING
    )
    session.add(export3)
    session.commit()
    print("TEST 2 PASSED PART 2: allowed third export")
except IntegrityError as e:
    print("TEST 2 FAILED PART 2:", e)
