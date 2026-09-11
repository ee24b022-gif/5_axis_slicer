import os
import struct

class MeshEnvelopeError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


# Limit maximum upload file size to 100MB by default
DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024
HEADER_SIZE = 80
COUNT_SIZE = 4
TRIANGLE_SIZE = 50

def validate_mesh_envelope(file_path: str, max_size_bytes: int = DEFAULT_MAX_FILE_SIZE) -> None:
    """
    Validates a file on disk strictly against binary STL envelope requirements
    without parsing the full mesh into memory.
    
    Raises MeshEnvelopeError with a specific diagnostic code if validation fails.
    """
    # 1. Size constraint check
    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        raise MeshEnvelopeError("FILE_NOT_FOUND", "The specified mesh file could not be read.")

    if file_size > max_size_bytes:
        raise MeshEnvelopeError(
            "FILE_OVERSIZED", 
            f"The file size ({file_size} bytes) exceeds the maximum allowed limit ({max_size_bytes} bytes)."
        )

    if file_size < HEADER_SIZE + COUNT_SIZE:
        raise MeshEnvelopeError(
            "FILE_TOO_SMALL", 
            "The file is too small to contain a valid binary STL header and triangle count."
        )

    # 2. Open file and read header
    with open(file_path, "rb") as f:
        header = f.read(HEADER_SIZE)
        
        # Binary STL files can start with anything, BUT many ASCII STLs start with "solid"
        # We enforce a strict rejection of "solid" at the start to block ASCII STLs.
        if header.lower().startswith(b"solid"):
            raise MeshEnvelopeError(
                "ASCII_STL_NOT_SUPPORTED",
                "ASCII STL format is not supported. Please upload a binary STL."
            )
            
        count_bytes = f.read(COUNT_SIZE)
        if len(count_bytes) < COUNT_SIZE:
            # Should be impossible due to file_size check, but safe to verify
            raise MeshEnvelopeError("TRUNCATED_HEADER", "File truncated during header read.")
            
        # 3. Read triangle count
        # STL count is a 32-bit unsigned little-endian integer
        triangle_count = struct.unpack("<I", count_bytes)[0]
        
    # 4. Enforce structural integrity (exact file size matching declared triangles)
    expected_size = HEADER_SIZE + COUNT_SIZE + (triangle_count * TRIANGLE_SIZE)
    
    if file_size < expected_size:
        raise MeshEnvelopeError(
            "FILE_TRUNCATED", 
            f"File appears truncated. Expected {expected_size} bytes based on {triangle_count} declared triangles, but got {file_size} bytes."
        )
        
    if file_size > expected_size:
        # Note: Some CAD software appends padding at the end of STL files. 
        # But for strict robust parsing, trailing garbage should be rejected or warned.
        # We will strictly reject here to prevent malicious payload hiding.
        raise MeshEnvelopeError(
            "FILE_PADDING_DETECTED",
            f"File contains trailing data. Expected {expected_size} bytes but got {file_size} bytes."
        )

    # 5. Passed all structural envelope checks
    return
