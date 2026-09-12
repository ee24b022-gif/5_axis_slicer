import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, MachineProfile
from uuid import uuid4

def test_machine_profile_orm_validation():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Valid profile
    valid_contract = {
        "calibration_revision": 1,
        "kinematic_convention": "BC_TABLE",
        "units": "mm",
        "axis_names": ["X", "Y", "Z", "B", "C"],
        "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1},
        "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0},
        "command_templates": {"linear_move": "G1"}
    }
    valid_limits = {
        "ranges": {"X": (0, 300)}
    }

    from models import User
    user = User(username="test_author", email="test@test.com", hashed_password="hash")
    session.add(user)
    session.commit()

    profile = MachineProfile(
        name="Valid Profile",
        revision=1,
        dialect="Marlin",
        contract=valid_contract,
        limits=valid_limits,
        author_id=user.id
    )
    session.add(profile)
    session.commit()

    # Invalid contract
    invalid_contract = valid_contract.copy()
    invalid_contract["axis_directions"] = {"X": 2} # Invalid

    with pytest.raises(ValueError, match="Invalid machine contract"):
        MachineProfile(
            name="Invalid Profile 1",
            revision=1,
            dialect="Marlin",
            contract=invalid_contract,
            limits=valid_limits,
            author_id=user.id
        )

    # Invalid limits
    invalid_limits = {
        "ranges": {"X": (300, 0)} # min > max
    }

    with pytest.raises(ValueError, match="Invalid machine limits"):
        MachineProfile(
            name="Invalid Profile 2",
            revision=1,
            dialect="Marlin",
            contract=valid_contract,
            limits=invalid_limits,
            author_id=user.id
        )
