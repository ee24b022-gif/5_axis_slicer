from typing import Tuple
import trimesh
from enums import JobStage, DiagnosticSeverity, DiagnosticStatus
from validation_model import ValidationResult, ValidationDiagnostic
from mesh_validator import validate_mesh_envelope, MeshEnvelopeError
from stl_parser import parse_binary_stl
from mesh_structural_validator import validate_mesh_structure
from slice_plane_model import SlicePlane

class ValidationService:
    @staticmethod
    def validate_mesh_file(file_path: str) -> Tuple[ValidationResult, trimesh.Trimesh | None]:
        """
        Validates an uploaded STL file by running envelope bounds checking, parsing,
        and finally strict structural geometry validation.
        """
        diagnostics = []
        
        # 1. Envelope validation
        try:
            validate_mesh_envelope(file_path)
        except MeshEnvelopeError as e:
            diagnostics.append(ValidationDiagnostic(
                stage=JobStage.MESH_VALIDATION,
                severity=DiagnosticSeverity.ERROR,
                status=DiagnosticStatus.FAIL,
                code=e.code,
                message=e.message
            ))
            return ValidationResult(diagnostics=diagnostics), None
            
        # 2. Parse STL
        try:
            parsed_data = parse_binary_stl(file_path)
            vertices = parsed_data["vertices"]
            faces = parsed_data["faces"]
        except Exception as e:
            diagnostics.append(ValidationDiagnostic(
                stage=JobStage.MESH_VALIDATION,
                severity=DiagnosticSeverity.ERROR,
                status=DiagnosticStatus.FAIL,
                code="STL_PARSE_ERROR",
                message=str(e)
            ))
            return ValidationResult(diagnostics=diagnostics), None

        # 3. Structural validation
        mesh, struct_diags = validate_mesh_structure(vertices, faces)
        for d in struct_diags:
            severity = d['severity']
            status = DiagnosticStatus.FAIL if severity == DiagnosticSeverity.ERROR else DiagnosticStatus.WARNING
            diagnostics.append(ValidationDiagnostic(
                stage=JobStage.MESH_VALIDATION,
                severity=severity,
                status=status,
                code=d['code'],
                message=d['message']
            ))

        return ValidationResult(diagnostics=diagnostics), mesh

    @staticmethod
    def validate_slice_plane(plane_data: dict) -> Tuple[ValidationResult, SlicePlane | None]:
        """
        Safely attempts to instantiate a strict SlicePlane definition.
        Traps unhandled ValueErrors and converts them to diagnostic failures.
        """
        diagnostics = []
        
        try:
            plane = SlicePlane(**plane_data)
            return ValidationResult(diagnostics=diagnostics), plane
        except ValueError as e:
            diagnostics.append(ValidationDiagnostic(
                stage=JobStage.SECTIONING,
                severity=DiagnosticSeverity.ERROR,
                status=DiagnosticStatus.FAIL,
                code="INVALID_SLICE_PLANE",
                message=str(e)
            ))
            return ValidationResult(diagnostics=diagnostics), None

    @staticmethod
    def validate_slice_preflight(mesh: trimesh.Trimesh, plane: SlicePlane) -> ValidationResult:
        """
        Validates the geometric safety of a sectioning plane against the mesh.
        """
        from plane_preflight import preflight_slice_plane
        diagnostics = preflight_slice_plane(mesh, plane)
        return ValidationResult(diagnostics=diagnostics)

    @staticmethod
    def validate_machine_kinematics(plane: SlicePlane, profile_contract: dict, profile_limits: dict) -> ValidationResult:
        """
        Validates a requested slice plane against the physical limits of the machine.
        Emits explicit NOT_IMPLEMENTED for missing singularity/reachability algorithms.
        """
        diagnostics = []

        # 1. Singularity check
        diagnostics.append(ValidationDiagnostic(
            stage=JobStage.SECTIONING,
            severity=DiagnosticSeverity.ERROR,
            status=DiagnosticStatus.NOT_IMPLEMENTED,
            code="SINGULARITY_DETECTION_NOT_IMPLEMENTED",
            message="Kinematic singularity detection is not implemented.",
            details={}
        ))
        
        # 2. Reachability check
        diagnostics.append(ValidationDiagnostic(
            stage=JobStage.SECTIONING,
            severity=DiagnosticSeverity.ERROR,
            status=DiagnosticStatus.NOT_IMPLEMENTED,
            code="REACHABILITY_NOT_IMPLEMENTED",
            message="Full workspace reachability analysis is not implemented.",
            details={}
        ))

        # 3. Axis limits check
        # Let's map plane convention to axis pairs
        convention_axes = {
            "BC_TABLE": ["B", "C"],
            "AC_TABLE": ["A", "C"],
            "AB_HEAD": ["A", "B"]
        }
        
        plane_conv = plane.rotation_convention.value
        expected_axes = convention_axes.get(plane_conv)
        
        if expected_axes:
            limits = profile_limits.get("ranges", {})
            
            for i, ax in enumerate(expected_axes):
                if ax in limits:
                    min_val, max_val = limits[ax]
                    angle = plane.angle_pair[i]
                    if not (min_val <= angle <= max_val):
                        diagnostics.append(ValidationDiagnostic(
                            stage=JobStage.SECTIONING,
                            severity=DiagnosticSeverity.ERROR,
                            status=DiagnosticStatus.FAIL,
                            code="OUT_OF_RANGE",
                            message=f"Axis {ax} angle {angle} is out of machine range [{min_val}, {max_val}].",
                            details={"axis": ax, "angle": angle, "min": min_val, "max": max_val}
                        ))
                else:
                    diagnostics.append(ValidationDiagnostic(
                        stage=JobStage.SECTIONING,
                        severity=DiagnosticSeverity.ERROR,
                        status=DiagnosticStatus.FAIL,
                        code="UNMAPPED_POSE",
                        message=f"Axis {ax} is required by convention but unmapped in machine limits.",
                        details={"axis": ax}
                    ))
                
        return ValidationResult(diagnostics=diagnostics)

    @staticmethod
    def validate_endpoint_collision(engine, path) -> ValidationResult:
        """
        Runs the limited endpoint/heuristic collision behavior.
        Explicitly non-proof validation.
        """
        diagnostics = []
        reports = engine.sweep_check_path(path)
        for report in reports:
            diagnostics.append(ValidationDiagnostic(
                stage=JobStage.VALIDATION,
                severity=DiagnosticSeverity.ERROR,
                status=DiagnosticStatus.FAIL,
                code="ENDPOINT_COLLISION_DETECTED",
                message=f"Collision with {report.limiting_surface} detected at point {report.point_index}.",
                details={"path_id": report.path_id, "layer_idx": report.layer_idx, "limiting_surface": report.limiting_surface}
            ))
            
        return ValidationResult(diagnostics=diagnostics)

    @staticmethod
    def validate_swept_volume_collision(path) -> ValidationResult:
        """
        Future swept-volume collision detection interface.
        """
        diagnostics = [ValidationDiagnostic(
            stage=JobStage.VALIDATION,
            severity=DiagnosticSeverity.ERROR,
            status=DiagnosticStatus.NOT_IMPLEMENTED,
            code="SWEPT_VOLUME_NOT_IMPLEMENTED",
            message="Swept-volume continuous collision detection is not implemented. No continuous safety claim is made.",
            details={}
        )]
        return ValidationResult(diagnostics=diagnostics)
