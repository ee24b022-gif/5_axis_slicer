import os
import sys
import traceback

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

def verify_c5():
    print("=== Checkpoint C5 Verification Suite ===")

    # 1. F-047: Machine Profile Contract Validation
    try:
        from machine_profile_model import MachineContract
        contract = MachineContract(
            calibration_revision=1,
            kinematic_convention="AC_TABLE",
            units="mm",
            axis_names=["X", "Y", "Z", "A", "C"],
            axis_directions={"X": 1, "Y": 1, "Z": 1, "A": 1, "C": 1},
            zero_positions={"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0, "C": 0.0},
            command_templates={"linear_move": "G1 X{x} Y{y} Z{z} F{feed_rate}"}
        )
        print("✅ F-047 Machine Profile Contract: MachineContract initialized and validated.")
    except Exception as e:
        print(f"❌ F-047 Machine Profile check failed: {e}")

    # 2. F-053 / F-054: Table-Table U/V Kinematics Adapter
    try:
        from uv_adapter import TableTableUVAdapter
        adapter = TableTableUVAdapter()
        ik_result = adapter.calculate_ik(0.0, 0.0, 0.0, 0.0, 0.7071, 0.7071)
        print(f"✅ F-053/F-054 Kinematics (U/V Adapter): IK calculated -> {ik_result}")
    except Exception as e:
        print(f"❌ F-053/F-054 Kinematics check failed: {e}")

    # 3. F-056 / F-057 / F-059: Dialect & 3-Axis G-code Generator
    try:
        from dialect_model import DialectSettings, FeedLimits, RetractionSettings
        from enums import GCodeDialect
        from toolpath_model import ToolpathJob, ToolpathLayer, ToolpathSegment, PathCategory
        from three_axis_gcode import ThreeAxisGCodeGenerator

        feed = FeedLimits(
            travel=3000.0,
            print=1200.0,
            retract=1800.0
        )
        retract = RetractionSettings(
            distance=1.0,
            feedrate=30.0
        )
        dialect_enum = getattr(GCodeDialect, 'REPRAP', list(GCodeDialect)[0] if list(GCodeDialect) else 'reprap')

        dialect = DialectSettings(
            dialect=dialect_enum,
            axis_mapping={"X": "X", "Y": "Y", "Z": "Z"},
            feed_limits=feed,
            retraction=retract
        )

        generator = ThreeAxisGCodeGenerator(dialect)

        segment = ToolpathSegment(
            path_id=1,
            category=PathCategory.PERIMETER,
            coords=[(0.0, 0.0), (10.0, 0.0)]
        )

        # Dynamically assign paths and segments based on schema model fields
        layer_kwargs = {"layer_id": 0, "z_height": 0.2}
        if "paths" in ToolpathLayer.model_fields:
            layer_kwargs["paths"] = [segment]
        if "segments" in ToolpathLayer.model_fields:
            layer_kwargs["segments"] = [segment]

        layer = ToolpathLayer(**layer_kwargs)

        job = ToolpathJob(
            job_id="job_001",
            layers=[layer]
        )

        gcode = generator.generate(job)
        print("✅ F-056/F-057/F-059 G-Code Generator: Generated G-code successfully.")
    except Exception as e:
        print(f"❌ F-056/F-057/F-059 G-code check failed: {e}")
        traceback.print_exc()

    # 4. F-060: Export Provenance Builder
    try:
        from provenance_model import ProvenanceBuilder
        print("✅ F-060 Provenance Builder: Class loaded successfully.")
    except Exception as e:
        print(f"❌ F-060 Provenance check failed: {e}")

    # 5. F-061: Export Gate Service
    try:
        from export_gate import ExportGateService
        print("✅ F-061 Export Gate Service: Class loaded successfully.")
    except Exception as e:
        print(f"❌ F-061 Export Gate check failed: {e}")

if __name__ == "__main__":
    verify_c5()