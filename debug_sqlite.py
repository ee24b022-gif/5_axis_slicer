import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models import Base
from backend.enums import ExportStatus

engine = create_engine('sqlite:///:memory:', echo=True)
Base.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

db.execute("INSERT INTO users (id, username, email, role, hashed_password, is_active, created_at, updated_at, is_deleted) VALUES ('1', 'u', 'u', 'USER', 'p', 1, '2020-01-01', '2020-01-01', 0)")
db.execute("INSERT INTO meshes (id, uploader_id, storage_uri, format, size_bytes, content_hash, triangle_count, bound_min_x, bound_min_y, bound_min_z, bound_max_x, bound_max_y, bound_max_z, created_at, updated_at) VALUES ('1', '1', 's', 'stl_binary', 1, 'h', 1, 0,0,0,1,1,1, '2020', '2020')")
db.execute("INSERT INTO machine_profiles (id, name, revision, author_id, dialect, contract, limits, is_active, created_at, updated_at) VALUES ('1', 'n', 1, '1', 'marlin', '{}', '{}', 1, '2020', '2020')")
db.execute("INSERT INTO jobs (id, creator_id, mesh_id, machine_profile_id, mode, settings, engine_revision, input_hash, status, progress, created_at, updated_at) VALUES ('1', '1', '1', '1', 'three_axis', '{}', '1', 'h', 'PENDING', 0, '2020', '2020')")

try:
    db.execute("INSERT INTO exports (id, job_id, creator_id, dialect, status, storage_uri, created_at, updated_at) VALUES ('1', '1', '1', 'marlin', 'ready', NULL, '2020', '2020')")
except Exception as e:
    print("CHECK CONSTRAINT ERROR:", e)

try:
    db.execute("INSERT INTO exports (id, job_id, creator_id, dialect, status, storage_uri, created_at, updated_at) VALUES ('2', '1', '1', 'marlin', 'revoked', NULL, '2020', '2020')")
    db.execute("INSERT INTO exports (id, job_id, creator_id, dialect, status, storage_uri, created_at, updated_at) VALUES ('3', '1', '1', 'marlin', 'pending', NULL, '2020', '2020')")
except Exception as e:
    print("UNIQUE CONSTRAINT ERROR:", e)
