import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import User, Mesh, MachineProfile, Job
from enums import UserRole, JobMode, JobStatus

engine = create_engine('sqlite:///:memory:', echo=True)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

user = User(username="u1", email="e1", role=UserRole.USER, hashed_password="pwd")
db.add(user)
db.commit()

mesh = Mesh(uploader_id=user.id, content_hash="h1", storage_uri="s1", size_bytes=1, triangle_count=1, bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0, bound_max_x=1.0, bound_max_y=1.0, bound_max_z=1.0)
profile = MachineProfile(name="N1", revision=1, dialect="d", contract={}, limits={}, author_id=user.id)
db.add_all([mesh, profile])
db.commit()

job = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=profile.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1", input_hash="h1", status=JobStatus.COMPLETE, completed_at=None)
db.add(job)
try:
    db.commit()
    print("COMMIT SUCCESS! Job status saved as:", db.execute(job.__table__.select()).first())
except Exception as e:
    print("COMMIT FAILED:", e)
