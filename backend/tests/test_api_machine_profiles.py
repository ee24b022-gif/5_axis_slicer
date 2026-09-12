import pytest
from fastapi.testclient import TestClient
from main import app
from database import engine, Base, SessionLocal
from models import User, MachineProfile
from enums import UserRole

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    db = SessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()

@pytest.fixture(scope="module")
def default_user():
    db = SessionLocal()
    user = db.query(User).filter_by(username="profile_user").first()
    if not user:
        user = User(
            username="profile_user",
            email="profile@example.com",
            role=UserRole.USER,
            hashed_password="pw"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user

@pytest.fixture(scope="module")
def setup_profiles(default_user):
    db = SessionLocal()
    
    valid_contract = {
        "calibration_revision": 1,
        "kinematic_convention": "BC_TABLE",
        "units": "mm",
        "axis_names": ["X", "Y", "Z", "B", "C"],
        "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1},
        "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0},
        "command_templates": {"linear_move": "G1"}
    }
    
    active_profile = MachineProfile(
        name="Active Profile",
        revision=1,
        dialect="MARLIN",
        contract=valid_contract,
        limits={"ranges": {"X": [0, 300]}},
        is_active=True,
        author_id=default_user.id
    )
    db.add(active_profile)
    
    retired_profile = MachineProfile(
        name="Retired Profile",
        revision=1,
        dialect="MARLIN",
        contract=valid_contract,
        limits={"ranges": {"X": [0, 300]}},
        is_active=False,
        author_id=default_user.id
    )
    db.add(retired_profile)
    
    db.commit()
    db.refresh(active_profile)
    db.refresh(retired_profile)
    db.close()
    
    return active_profile, retired_profile

def test_list_machine_profiles(setup_profiles):
    active_profile, retired_profile = setup_profiles
    response = client.get("/machine-profiles")
    assert response.status_code == 200
    
    profiles = response.json()
    assert isinstance(profiles, list)
    
    # Check that the active profile is returned
    assert any(p["id"] == str(active_profile.id) for p in profiles)
    
    # Check that the retired profile is NOT returned
    assert not any(p["id"] == str(retired_profile.id) for p in profiles)

def test_get_machine_profile_active(setup_profiles):
    active_profile, _ = setup_profiles
    response = client.get(f"/machine-profiles/{active_profile.id}")
    assert response.status_code == 200
    profile = response.json()
    assert profile["id"] == str(active_profile.id)
    assert profile["is_active"] == True

def test_get_machine_profile_retired(setup_profiles):
    _, retired_profile = setup_profiles
    response = client.get(f"/machine-profiles/{retired_profile.id}")
    assert response.status_code == 200
    profile = response.json()
    assert profile["id"] == str(retired_profile.id)
    assert profile["is_active"] == False

def test_get_machine_profile_not_found():
    import uuid
    random_id = uuid.uuid4()
    response = client.get(f"/machine-profiles/{random_id}")
    assert response.status_code == 404
