import os
import hashlib
import tempfile
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from dependencies import get_db, get_current_actor, Actor
from models import User
from repositories import MeshRepository
from mesh_validator import validate_mesh_envelope, MeshEnvelopeError
from stl_parser import parse_binary_stl
from storage import get_storage_adapter
from schemas import MeshResponse

router = APIRouter(prefix="/meshes", tags=["meshes"])

@router.post("")
async def upload_mesh(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    # 1. Read and Hash
    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()
    
    mesh_repo = MeshRepository(db)
    
    # 2. Deduplicate
    existing_mesh = mesh_repo.get_by_hash(content_hash)
    if existing_mesh:
        return {"id": str(existing_mesh.id), "hash": existing_mesh.content_hash}
        
    # 3. Validate Envelope
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
        
    try:
        validate_mesh_envelope(tmp_path)
        
        # 4. Extract Metadata
        parsed = parse_binary_stl(tmp_path)
        vertices = parsed["vertices"]
        faces = parsed["faces"]
        
        bounds_min = vertices.min(axis=0)
        bounds_max = vertices.max(axis=0)
        triangle_count = len(faces)
        
    except MeshEnvelopeError as e:
        os.remove(tmp_path)
        return JSONResponse(
            status_code=400,
            content={"diagnostics": [{"code": e.code, "message": e.message}]}
        )
    except Exception as e:
        os.remove(tmp_path)
        return JSONResponse(
            status_code=400,
            content={"diagnostics": [{"code": "M-000", "message": f"Mesh parsing failed: {str(e)}"}]}
        )
        
    os.remove(tmp_path)
    
    # 5. Persist Storage
    storage = get_storage_adapter()
    storage_uri = storage.save_artifact("meshes", content, content_hash)
    
    # 6. Database Metadata
    new_mesh = mesh_repo.create({
        "uploader_id": current_actor.user_id,
        "content_hash": content_hash,
        "storage_uri": storage_uri,
        "size_bytes": len(content),
        "triangle_count": triangle_count,
        "bound_min_x": float(bounds_min[0]),
        "bound_min_y": float(bounds_min[1]),
        "bound_min_z": float(bounds_min[2]),
        "bound_max_x": float(bounds_max[0]),
        "bound_max_y": float(bounds_max[1]),
        "bound_max_z": float(bounds_max[2]),
    })
    
    db.commit()
    
    return {"id": str(new_mesh.id), "hash": new_mesh.content_hash}

@router.get("/{mesh_id}", response_model=MeshResponse)
def get_mesh_metadata(
    mesh_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    mesh_repo = MeshRepository(db)
    mesh = mesh_repo.get_by_id(mesh_id)
    if not mesh:
        raise HTTPException(status_code=404, detail="Mesh not found")
        
    from authorization import enforce_ownership
    enforce_ownership(mesh, "uploader_id", current_actor, "Mesh")
        
    return mesh
