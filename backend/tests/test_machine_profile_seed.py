import pytest
from fastapi.testclient import TestClient
from main import app
from database import engine, Base, SessionLocal
from models import User, MachineProfile
from enums import UserRole
from machine_profile_seed import seed_fractal_profile

client = TestClient(app)

PROFILE_NAME = "fractal_5_pro_provisional"


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    db = SessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()


@pytest.fixture
def db_session():
    db = SessionLocal()
    yield db
    db.rollback()
    db.close()


def test_machine_profiles_route_on_canonical_app():
    """The /machine-profiles router is registered on main.app (canonical app)."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/machine-profiles" in response.json()["paths"]


def test_seeded_profile_is_active(db_session):
    seed_fractal_profile()

    profile = (
        db_session.query(MachineProfile)
        .filter_by(name=PROFILE_NAME)
        .first()
    )
    assert profile is not None
    assert profile.is_active is True


def test_seed_is_idempotent(db_session):
    seed_fractal_profile()
    seed_fractal_profile()

    count = (
        db_session.query(MachineProfile)
        .filter_by(name=PROFILE_NAME)
        .count()
    )
    assert count == 1, "seed must not create duplicate profiles"


def test_seed_reactivates_inactive_profile_preserving_values(db_session):
    seed_fractal_profile()

    db = SessionLocal()
    profile = db.query(MachineProfile).filter_by(name=PROFILE_NAME).first()
    assert profile is not None
    original_id = profile.id
    original_contract = dict(profile.contract)
    original_limits = dict(profile.limits)
    original_dialect = profile.dialect

    profile.is_active = False
    db.commit()
    db.close()

    # Re-seed: must reactivate and preserve the provisioned hardware values.
    seed_fractal_profile()

    db = SessionLocal()
    try:
        reactivated = (
            db.query(MachineProfile).filter_by(name=PROFILE_NAME).first()
        )
        assert reactivated is not None
        assert reactivated.is_active is True
        assert reactivated.id == original_id
        assert reactivated.dialect == original_dialect
        assert reactivated.contract == original_contract
        assert reactivated.limits == original_limits
        assert (
            db.query(MachineProfile).filter_by(name=PROFILE_NAME).count() == 1
        )
    finally:
        db.close()


def test_list_machine_profiles_filters_inactive(db_session):
    seed_fractal_profile()

    # Add an inactive profile directly and confirm the API filters it out.
    author = db_session.query(User).first()
    if not author:
        author = User(
            username="filter_author",
            email="filter@example.com",
            role=UserRole.ADMIN,
            hashed_password="pw",
        )
        db_session.add(author)
        db_session.commit()
        db_session.refresh(author)

    contract = {
        "calibration_revision": 1,
        "kinematic_convention": "BC_TABLE",
        "units": "mm",
        "axis_names": ["X", "Y", "Z", "B", "C"],
        "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1},
        "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0},
        "command_templates": {"linear_move": "G1"},
    }
    inactive = MachineProfile(
        name="Inactive Profile",
        revision=1,
        dialect="MARLIN",
        contract=contract,
        limits={"ranges": {"X": [0, 300]}},
        is_active=False,
        author_id=author.id,
    )
    db_session.add(inactive)
    db_session.commit()

    response = client.get("/machine-profiles")
    assert response.status_code == 200
    profiles = response.json()
    assert isinstance(profiles, list)
    assert any(p["name"] == PROFILE_NAME and p["is_active"] for p in profiles)
    assert not any(p["name"] == "Inactive Profile" for p in profiles)
