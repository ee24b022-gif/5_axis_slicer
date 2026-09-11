from typing import TypeVar, Generic, Type, Any, Optional, List, Sequence
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, asc, desc

from models import Base, User, Mesh, MachineProfile, Job, Chunk, Diagnostic, Export
from enums import DiagnosticSeverity, ExportStatus

T = TypeVar("T", bound=Base)

class BaseRepository(Generic[T]):
    def __init__(self, model_cls: Type[T], session: Session):
        self.model_cls = model_cls
        self.session = session

    def get_by_id(self, id: UUID) -> Optional[T]:
        return self.session.get(self.model_cls, id)

    def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[T]:
        stmt = select(self.model_cls).offset(skip).limit(limit)
        return self.session.execute(stmt).scalars().all()

    def create(self, obj_in: dict[str, Any] | T) -> T:
        if isinstance(obj_in, dict):
            db_obj = self.model_cls(**obj_in)
        else:
            db_obj = obj_in
            
        self.session.add(db_obj)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            raise
        return db_obj

    def update(self, db_obj: T, update_data: dict[str, Any]) -> T:
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        self.session.add(db_obj)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            raise
        return db_obj

    def delete(self, id: UUID) -> bool:
        obj = self.get_by_id(id)
        if obj:
            self.session.delete(obj)
            try:
                self.session.flush()
                return True
            except IntegrityError:
                self.session.rollback()
                raise
        return False


class UserRepository(BaseRepository[User]):
    def __init__(self, session: Session):
        super().__init__(User, session)

    def get_by_username(self, username: str) -> Optional[User]:
        stmt = select(User).where(User.username == username, User.is_deleted == False)
        return self.session.execute(stmt).scalars().first()

    def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email, User.is_deleted == False)
        return self.session.execute(stmt).scalars().first()


class MeshRepository(BaseRepository[Mesh]):
    def __init__(self, session: Session):
        super().__init__(Mesh, session)

    def get_by_hash(self, content_hash: str) -> Optional[Mesh]:
        stmt = select(Mesh).where(Mesh.content_hash == content_hash)
        return self.session.execute(stmt).scalars().first()


class MachineProfileRepository(BaseRepository[MachineProfile]):
    def __init__(self, session: Session):
        super().__init__(MachineProfile, session)

    def get_active_profiles(self) -> Sequence[MachineProfile]:
        stmt = select(MachineProfile).where(MachineProfile.is_active == True)
        return self.session.execute(stmt).scalars().all()


class JobRepository(BaseRepository[Job]):
    def __init__(self, session: Session):
        super().__init__(Job, session)

    def get_recent_jobs(self, limit: int = 100) -> Sequence[Job]:
        stmt = select(Job).order_by(desc(Job.created_at)).limit(limit)
        return self.session.execute(stmt).scalars().all()


class ChunkRepository(BaseRepository[Chunk]):
    def __init__(self, session: Session):
        super().__init__(Chunk, session)

    def get_chunks_for_job(self, job_id: UUID) -> Sequence[Chunk]:
        stmt = select(Chunk).where(Chunk.job_id == job_id).order_by(asc(Chunk.chunk_idx))
        return self.session.execute(stmt).scalars().all()


class DiagnosticRepository(BaseRepository[Diagnostic]):
    def __init__(self, session: Session):
        super().__init__(Diagnostic, session)

    def get_by_job_and_severity(self, job_id: UUID, min_severity: DiagnosticSeverity) -> Sequence[Diagnostic]:
        stmt = select(Diagnostic).where(
            Diagnostic.job_id == job_id, 
            Diagnostic.severity >= min_severity
        ).order_by(desc(Diagnostic.created_at))
        return self.session.execute(stmt).scalars().all()


class ExportRepository(BaseRepository[Export]):
    def __init__(self, session: Session):
        super().__init__(Export, session)

    def get_active_export(self, job_id: UUID, dialect: str) -> Optional[Export]:
        stmt = select(Export).where(
            Export.job_id == job_id, 
            Export.dialect == dialect,
            Export.status != ExportStatus.REVOKED
        )
        return self.session.execute(stmt).scalars().first()
