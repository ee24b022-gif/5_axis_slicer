import sys
import os
import uuid
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import MachineProfile, User, UserRole

def seed_fractal_profile():
    db = SessionLocal()
    try:
        author = db.query(User).first()
        if not author:
            author = User(username='admin_seed', email='admin_seed@example.com', role=UserRole.ADMIN, hashed_password='dummy')
            db.add(author)
            db.commit()
            db.refresh(author)
            
        existing = db.query(MachineProfile).filter(MachineProfile.name == "fractal_5_pro_provisional").first()
        
        contract = {
            "calibration_revision": 1,
            "kinematic_convention": "AC_TABLE", 
            "units": "mm",
            "axis_names": ["X", "Y", "Z", "A", "B"],
            "axis_directions": {"X": 1, "Y": 1, "Z": 1, "A": 1, "B": 1},
            "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0, "B": 0.0},
            "table_centers": {"A": 0.0, "B": 0.0},
            "command_templates": {
                "linear_move": "G1 X{x} Y{y} Z{z}",
                "rotary_move": "MANUAL_STEPPER STEPPER=stepper_{axis} POS={pos}"
            }
        }
        
        limits = {
            "ranges": {
                "X": [-100.0, 100.0],
                "Y": [-100.0, 100.0],
                "Z": [0.0, 200.0],
                "A": [-120.0, 120.0],
                "B": [-360.0, 360.0]
            }
        }
        
        if existing:
            existing.dialect = "klipper_manual_stepper_ab"
            existing.contract = contract
            existing.limits = limits
            print(f"Updated existing profile: {existing.id}")
        else:
            profile = MachineProfile(
                name="fractal_5_pro_provisional",
                revision=1,
                dialect="klipper_manual_stepper_ab",
                contract=contract,
                limits=limits,
                author_id=author.id,
                is_active=True
            )
            db.add(profile)
            print("Created new profile")
            
        db.commit()
        print("Done.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_fractal_profile()
