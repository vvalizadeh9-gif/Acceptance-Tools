"""
Shared enumerations for the USO Delivery & Acceptance Management Platform.

Kept as Python enums (rather than free-text strings) so both the ORM layer
and the API layer validate against the same fixed vocab. Rule 3 in the
blueprint explicitly forbids "hardcoded status strings" scattered through
the app — enums + the timeline_event ledger are how we satisfy that.
"""

import enum


class UserRole(str, enum.Enum):
    """Seven roles. Six come from the original requirements session (the
    architecture PDF had flattened Admin into Project Manager and dropped
    Viewer); Finance was added later, tied to the financial-depreciation /
    budget scope and the تاریخ ابلاغ (official MTN assignment date) that
    feeds it. Finance sees financial data only.

    Admin:            full control, user management, final approvals.
    Project Manager:  dashboard/KPI/bottleneck visibility only — no writes.
    DT Coordinator:   registers Acceptance data, ICT/CRA letters, approvals.
    Field Subcontractor: sees only assigned sites; logs DT dates/progress.
    Regional Manager: read-only, scoped to their own region.
    Finance:          financial/depreciation data only (budget module scope).
    Viewer:           read-only, sees only Admin-approved data.
    """
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    DT_COORDINATOR = "dt_coordinator"
    FIELD_SUBCONTRACTOR = "field_subcontractor"
    REGIONAL_MANAGER = "regional_manager"
    FINANCE = "finance"
    VIEWER = "viewer"


class Technology(str, enum.Enum):
    GSM = "GSM"
    UMTS = "UMTS"
    LTE = "LTE"
    NR = "NR"


class WorkItemStatus(str, enum.Enum):
    """Derived/cached status. The source of truth is timeline_event; this
    column is a denormalized read-optimization, never written directly by
    API consumers (see WorkItemRead vs. WorkItemInternalUpdate)."""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    READY_FOR_DT = "ready_for_dt"
    BLOCKED = "blocked"
    ACCEPTED = "accepted"


class HealthCheckStatus(str, enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"


class DriveTestStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


class AcceptanceStatus(str, enum.Enum):
    NOT_SUBMITTED = "not_submitted"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class BlockCategory(str, enum.Enum):
    """Rule 4: Registry Integrity — block reason must map to exactly one
    of these values. Nothing else is accepted at the API boundary."""
    POWER_TEMPORARY = "Power (Temporary)"
    POWER_PERMANENT_DEFICIT = "Power (Permanent Deficit)"
    TRANSMISSION_GAP = "Transmission Gap"
    HARDWARE_MISSING = "Hardware Missing"
    ACCESS_RESTRICTIONS = "Access Restrictions"
    CRA_DELAY = "CRA Delay"
    ICT_DELAY = "ICT Delay"


class ImpedimentEntityType(str, enum.Enum):
    """Rule 4: Operational Layer Separation — DT-level blockers are field
    infrastructure issues owned by subcontractors; Acceptance-level
    blockers are administrative issues owned by internal coordinators."""
    WORK_ITEM_DT = "work_item_dt"
    VILLAGE_ACCEPTANCE = "village_acceptance"


class LetterOrganization(str, enum.Enum):
    ICT_PROVINCE = "ICT Province"
    ICT_HQ = "ICT HQ"
    CRA_REGION = "CRA Region"
    CRA_HQ = "CRA HQ"


class ChangeSeverity(str, enum.Enum):
    """Rule 2: CPM Change Review Center severity classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChangeDecision(str, enum.Enum):
    ACCEPTED = "accepted"
    IGNORED = "ignored"
    FLAGGED = "flagged"
    PENDING = "pending"


class DTProgressStatus(str, enum.Enum):
    """Current drive-test progress for a Work Item (Site + Site Type). This
    is the site-grain status the DT dashboards read — distinct from the
    detailed DriveTest submission/review workflow, which stays in its own
    table. Seeded historically from the one-time CPM import, app-managed
    afterwards."""
    DONE = "done"
    ONGOING = "ongoing"
    PROBLEMATIC = "problematic"


class DTProblematicCategory(str, enum.Enum):
    """Why a Work Item's drive test is problematic. Only meaningful when
    dt_status == PROBLEMATIC. Five categories (MS = Managed Service);
    PROJECT_RESPONSIBILITY is the exact label used in the real CPM export
    (originally specified as "On-Site Issue" before the real file arrived)."""
    PROJECT_RESPONSIBILITY = "project_responsibility"
    TEMP_POWER = "temp_power"
    MS_RESPONSIBILITY = "ms_responsibility"
    NWG_RESPONSIBILITY = "nwg_responsibility"
    OTHER = "other"


class DepreciationStatus(str, enum.Enum):
    """Depreciation state, tracked at BOTH grains (Site+SiteType on the Work
    Item, and Site+Village on the acceptance row) per the requirement to
    'keep both'."""
    DEPRECIATED = "depreciated"
    WAITING = "waiting_for_depreciation"
    REMAIN = "remain"
