from enum import StrEnum

class UserRole(StrEnum):
    USER = 'user'
    OPERATOR = 'operator'
    VALIDATOR = 'validator'
    ADMIN = 'admin'
    SERVICE = 'service'

class JobStatus(StrEnum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETE = 'complete'
    FAILED = 'failed'
    PARTIAL = 'partial'
    CANCELLED = 'cancelled'

class JobMode(StrEnum):
    THREE_AXIS = 'three_axis'
    INDEXED_MULTIDIRECTIONAL = 'indexed_multidirectional'

class MeshFormat(StrEnum):
    STL_BINARY = 'stl_binary'

class ChunkValidity(StrEnum):
    PENDING = 'pending'
    VALID = 'valid'
    INVALID = 'invalid'
    EMPTY = 'empty'
    PARTIAL = 'partial'

class DiagnosticSeverity(StrEnum):
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'

class DiagnosticStatus(StrEnum):
    PASS = 'pass'
    WARNING = 'warning'
    FAIL = 'fail'
    NOT_IMPLEMENTED = 'not_implemented'

class JobStage(StrEnum):
    MESH_VALIDATION = 'mesh_validation'
    CANONICAL_FRAME = 'canonical_frame'
    CHUNK_CONSTRUCTION = 'chunk_construction'
    SECTIONING = 'sectioning'
    POLYGON_PROCESSING = 'polygon_processing'
    PATH_ORDERING = 'path_ordering'
    VALIDATION = 'validation'
    POST_PROCESSING = 'post_processing'
    ARTIFACT_PERSISTENCE = 'artifact_persistence'

class ExportStatus(StrEnum):
    PENDING = 'pending'
    READY = 'ready'
    BLOCKED = 'blocked'
    FAILED = 'failed'
    REVOKED = 'revoked'

class TokenStatus(StrEnum):
    ACTIVE = 'active'
    REVOKED = 'revoked'
    EXPIRED = 'expired'

class AngleUnit(StrEnum):
    DEGREES = 'degrees'
    RADIANS = 'radians'

class RotationConvention(StrEnum):
    AC_TABLE = 'AC_TABLE'
    BC_TABLE = 'BC_TABLE'
    AB_HEAD = 'AB_HEAD'

class CoordinateMode(StrEnum):
    ABSOLUTE = 'absolute'
    RELATIVE = 'relative'

class GCodeDialect(StrEnum):
    MARLIN = 'marlin'
    KLIPPER = 'klipper'
    RRF = 'rrf'
    MACH3 = 'mach3'
    LINUXCNC = 'linuxcnc'
