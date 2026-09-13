from models import Job, Export
from export_gate import ExportGateService
from preprint_checklist import PreprintChecklist, ReleaseGateResult


class ReleaseGateService:
    """
    Composes the ExportGateService with the physical pre-print checklist.
    Both gates must pass for an export to be authorized.
    No unattended-print authorization pathway exists.
    """

    @staticmethod
    def evaluate(job: Job, export: Export, checklist: PreprintChecklist) -> ReleaseGateResult:
        # --- Stage 1: Software export gate ---
        export_allowed, export_details = ExportGateService.evaluate(job, export)
        safety_label = export_details.get("safety_label", "UNKNOWN")
        export_reason = export_details.get("reason")

        if not export_allowed:
            return ReleaseGateResult(
                authorized=False,
                safety_label=safety_label,
                checklist_complete=checklist.is_complete,
                missing_items=checklist.missing_items,
                export_gate_passed=False,
                export_gate_reason=export_reason,
                release_notes=(
                    f"Export gate BLOCKED: {export_reason}. "
                    "Resolve export-level issues before completing the pre-print checklist."
                ),
            )

        # --- Stage 2: Physical pre-print checklist ---
        if not checklist.is_complete:
            missing = checklist.missing_items
            return ReleaseGateResult(
                authorized=False,
                safety_label=safety_label,
                checklist_complete=False,
                missing_items=missing,
                export_gate_passed=True,
                export_gate_reason=None,
                release_notes=(
                    f"Pre-print checklist incomplete. "
                    f"Missing items: {', '.join(missing)}. "
                    "Complete all physical safety checks before downloading G-code."
                ),
            )

        # --- Both gates passed ---
        return ReleaseGateResult(
            authorized=True,
            safety_label=safety_label,
            checklist_complete=True,
            missing_items=[],
            export_gate_passed=True,
            export_gate_reason=None,
            release_notes=(
                f"Release AUTHORIZED. Safety label: {safety_label}. "
                "All export checks passed and operator has completed the physical dry-run checklist. "
                "Proceed to download via GET /jobs/{{job_id}}/export."
            ),
        )
