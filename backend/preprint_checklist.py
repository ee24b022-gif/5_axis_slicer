from pydantic import BaseModel, Field
from typing import List


class PreprintChecklist(BaseModel):
    """
    Physical dry-run checklist that an operator must complete before
    downloading G-code. Every item must be True for the release gate
    to authorize the export.
    """
    homing_verified: bool = Field(
        default=False,
        description="Machine homed on all axes before run"
    )
    center_position_confirmed: bool = Field(
        default=False,
        description="Workpiece centered and clamped"
    )
    ab_zero_convention_checked: bool = Field(
        default=False,
        description="A/B axis zero positions match profile conventions"
    )
    rotary_mapping_reviewed: bool = Field(
        default=False,
        description="Rotary axis mapping visually reviewed against model orientation"
    )
    table_clearance_checked: bool = Field(
        default=False,
        description="Table clearance verified for full rotation envelope"
    )
    travel_limits_validated: bool = Field(
        default=False,
        description="Travel limits verified against machine firmware limits"
    )
    firmware_behavior_acknowledged: bool = Field(
        default=False,
        description="Firmware behavior (stop-on-limit, soft-limits) documented and understood"
    )
    prototype_label_acknowledged: bool = Field(
        default=False,
        description="Operator acknowledges this is prototype software output"
    )

    @property
    def is_complete(self) -> bool:
        """Returns True only when every checklist item is acknowledged."""
        return all([
            self.homing_verified,
            self.center_position_confirmed,
            self.ab_zero_convention_checked,
            self.rotary_mapping_reviewed,
            self.table_clearance_checked,
            self.travel_limits_validated,
            self.firmware_behavior_acknowledged,
            self.prototype_label_acknowledged,
        ])

    @property
    def missing_items(self) -> List[str]:
        """Returns a list of field names that have not been acknowledged."""
        items = []
        for field_name in [
            "homing_verified",
            "center_position_confirmed",
            "ab_zero_convention_checked",
            "rotary_mapping_reviewed",
            "table_clearance_checked",
            "travel_limits_validated",
            "firmware_behavior_acknowledged",
            "prototype_label_acknowledged",
        ]:
            if not getattr(self, field_name):
                items.append(field_name)
        return items


class ReleaseGateResult(BaseModel):
    """
    Combined result of the export gate and the pre-print checklist evaluation.
    """
    authorized: bool = Field(
        description="True only if both the export gate passes and the checklist is complete"
    )
    safety_label: str = Field(
        description="Safety label from provenance (PROTOTYPE / PRODUCTION / BLOCKED)"
    )
    checklist_complete: bool = Field(
        description="Whether all checklist items are acknowledged"
    )
    missing_items: List[str] = Field(
        default_factory=list,
        description="Checklist items that have not been acknowledged"
    )
    export_gate_passed: bool = Field(
        description="Whether the underlying export gate passed"
    )
    export_gate_reason: str | None = Field(
        default=None,
        description="Reason the export gate blocked, if applicable"
    )
    release_notes: str = Field(
        description="Human-readable summary of the release gate evaluation"
    )
