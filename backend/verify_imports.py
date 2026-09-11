import sys

def check_imports():
    modules = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "sqlalchemy",
        "alembic",
        "numpy",
        "trimesh",
        "rtree",
        "scipy",
        "shapely",
        "celery",
        "redis",
        "pytest",
        "httpx"
    ]
    missing = []
    for mod in modules:
        try:
            __import__(mod)
        except ImportError as e:
            missing.append(f"{mod} ({e})")
            
    if missing:
        print("FAILED: Missing modules:")
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)
    else:
        print("SUCCESS: All modules imported successfully.")
        sys.exit(0)

if __name__ == "__main__":
    check_imports()
