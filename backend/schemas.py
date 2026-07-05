"""
Pydantic v2 schemas.

The key architectural point here is Rule 1 (Single Source Ownership): CPM
owns baseline fields (province, on_air_date, requested technologies) and
the web app owns operational fields (assignments, health checks, drive
test files, correspondence). That split is enforced by giving CPM-import
and operator-facing writes *separate* schemas — there is no single
"SiteUpdate" model that accepts both, so a coordinator's PATCH request
can never carry an on_air_date change, and the CPM importer can never be
used to set an assignment. Enforce the actual role check (is this caller
really the CPM import job?) in the route/dependency layer — these schemas
only guarantee the field can't even parse if it's misdirected.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from enums import (
    AcceptanceStatus,
    BlockCategory,
    DriveTestStatus,
    HealthCheckStatus,
    ImpedimentEntityType,
    LetterOrganization,
    ReviewDecision,
    Technology,
    UserRole,
    WorkItemStatus,
)


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    """Only an Admin can call the route that uses this schema."""
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    role: UserRole
    region_name: Optional[str] = Field(default=None, max_length=100)
    password: str = Field(min_length=8)

    @model_validator(mode="after")
    def region_required_for_scoped_roles(self):
        # field_validator would silently skip this check when region_name is
        # left at its default (None) since Pydantic v2 doesn't validate
        # unset defaults — a model-level check is what actually fires.
        if self.role == UserRole.REGIONAL_MANAGER and not self.region_name:
            raise ValueError("region_name is required for Regional Manager accounts")
        return self


class UserRead(ORMBase):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    region_name: Optional[str]
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    """Admin edits an existing account. All fields optional — only what's
    sent gets changed. Email is intentionally NOT editable (it's the login
    identity); to change it, deactivate and make a new account."""
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    role: Optional[UserRole] = None
    region_name: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8)


# ---------------------------------------------------------------------------
# Site — CPM-owned vs platform-owned, kept as separate schemas (Rule 1)
# ---------------------------------------------------------------------------

class SiteCPMImport(BaseModel):
    """Used ONLY by the CPM synchronization job (see Rule 2 — even this
    doesn't write straight to the site table above medium severity; it
    writes to PendingChange for high/critical deltas)."""
    site_id: str = Field(max_length=50)
    province_id: uuid.UUID
    region_id: uuid.UUID
    on_air_date: Optional[date] = None
    requested_technologies: list[Technology] = Field(default_factory=list)


class SiteRead(ORMBase):
    id: uuid.UUID
    site_id: str
    official_site_id: Optional[str] = None
    temp_site_code: Optional[str] = None
    province_id: uuid.UUID
    region_id: uuid.UUID
    on_air_date: Optional[date]
    assignment_date: Optional[date]
    created_at: datetime
    updated_at: datetime


class SiteOperationalUpdate(BaseModel):
    """What a PM/Coordinator is allowed to touch on a site. Notably absent:
    on_air_date, province_id, region_id — those are CPM-owned and any
    attempt to set them here should 403 at the route level even though
    they aren't in this model at all."""
    assignment_date: Optional[date] = None


class SiteListItem(BaseModel):
    """One row in the Sites & Villages table."""
    id: uuid.UUID
    site_id: str
    official_site_id: Optional[str]
    temp_site_code: Optional[str]
    province_name: Optional[str]
    region_name: Optional[str]
    village_count: int
    work_item_count: int
    on_air_work_item_count: int
    is_on_air: bool
    assigned_contractor: Optional[str] = None


class SiteListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[SiteListItem]


class SiteFilterOptions(BaseModel):
    provinces: list[str]
    regions: list[str]
    site_types: list[str]


class AssignSiteRequest(BaseModel):
    """Assigns ALL work items under a site to one contractor in one action —
    matches the real operational pattern (a whole site is handed to a
    contractor by email), not per-work-item assignment."""
    contractor_id: uuid.UUID
    remark: Optional[str] = Field(default=None, max_length=1000)


class AssignmentRead(BaseModel):
    work_item_id: uuid.UUID
    site_type: str
    contractor_id: uuid.UUID
    contractor_name: str
    assigned_at: datetime
    remark: Optional[str]


# ---------------------------------------------------------------------------
# Work Item
# ---------------------------------------------------------------------------

class WorkItemCreate(BaseModel):
    site_id: uuid.UUID
    site_type: str = Field(max_length=100)
    assignment_date: date


class WorkItemRead(ORMBase):
    id: uuid.UUID
    site_id: uuid.UUID
    site_type: str
    assignment_date: date
    status: WorkItemStatus
    created_at: datetime
    updated_at: datetime


class ContractorAssignmentCreate(BaseModel):
    work_item_id: uuid.UUID
    contractor_id: uuid.UUID
    remark: Optional[str] = None


class HealthCheckCreate(BaseModel):
    """Written by the Field Subcontractor role only, scoped to their own
    assigned work items — enforce the ownership check in the route, not
    here."""
    work_item_id: uuid.UUID
    status: HealthCheckStatus
    comment: Optional[str] = Field(default=None, max_length=2000)


class DriveTestCreate(BaseModel):
    work_item_id: uuid.UUID
    delivery_date: date
    report_url: str
    status: DriveTestStatus = DriveTestStatus.SUBMITTED


class DriveTestReviewCreate(BaseModel):
    drive_test_id: uuid.UUID
    review_level: str = Field(max_length=50)
    decision: ReviewDecision
    comment: str = Field(min_length=15, max_length=2000)


# ---------------------------------------------------------------------------
# Acceptance Layer
# ---------------------------------------------------------------------------

class VillageAcceptanceRead(ORMBase):
    """One acceptance row per (site, village), wide per-technology layout —
    mirrors the restructured VillageAcceptance model. A per-tech field is
    None when that technology was not requested for the village."""
    id: uuid.UUID
    site_id: uuid.UUID
    village_id: str

    ict_2g: Optional[AcceptanceStatus] = None
    ict_3g: Optional[AcceptanceStatus] = None
    ict_4g: Optional[AcceptanceStatus] = None
    ict_final: bool
    ict_comment: Optional[str] = None
    ict_letter_number: Optional[str] = None
    ict_letter_date: Optional[date] = None
    ict_approved_by: Optional[uuid.UUID] = None
    ict_approved_at: Optional[datetime] = None

    cra_2g: Optional[AcceptanceStatus] = None
    cra_3g: Optional[AcceptanceStatus] = None
    cra_4g: Optional[AcceptanceStatus] = None
    cra_final: bool
    cra_comment: Optional[str] = None
    cra_letter_number: Optional[str] = None
    cra_letter_date: Optional[date] = None
    cra_approved_by: Optional[uuid.UUID] = None
    cra_approved_at: Optional[datetime] = None

    depreciation_status: Optional[str] = None
    updated_at: datetime


class AcceptanceSideUpdate(BaseModel):
    """A coordinator's edit to ONE side (ICT or CRA) of one village. Only
    requested technologies may carry a status — passing g2/g3/g4 for a
    technology that wasn't requested for this village is a 422 (enforced in
    the route). A None field means 'leave unchanged'. Any successful update
    stamps that side's approved_by (Single Source Ownership)."""
    g2: Optional[AcceptanceStatus] = None
    g3: Optional[AcceptanceStatus] = None
    g4: Optional[AcceptanceStatus] = None
    comment: Optional[str] = Field(default=None, max_length=2000)
    letter_number: Optional[str] = Field(default=None, max_length=100)
    letter_date: Optional[date] = None


class LetterCreate(BaseModel):
    """Rule 5: one letter, many villages. `village_acceptance_ids` fans
    out to LetterVillageMapping rows in a single transaction, approving
    every requested technology on the letter's side (ICT or CRA, from the
    organization) across every linked village — see acceptance_service."""
    letter_number: str = Field(max_length=100)
    letter_date: date
    organization: LetterOrganization
    province_or_region_id: uuid.UUID
    comment: Optional[str] = None
    pdf_attachment_url: Optional[str] = None
    village_acceptance_ids: list[uuid.UUID] = Field(min_length=1)


class LetterRead(ORMBase):
    id: uuid.UUID
    letter_number: str
    letter_date: date
    organization: str
    province_or_region_id: uuid.UUID
    comment: Optional[str] = None
    pdf_attachment_url: Optional[str] = None
    created_at: datetime
    village_count: int = 0


class AcceptanceListItem(BaseModel):
    """One row in the Acceptance table — the village plus a compact summary
    of both independent sides (ICT and CRA stay separate, per the spec)."""
    id: uuid.UUID
    site_id: uuid.UUID
    site_business_id: Optional[str] = None
    province_name: Optional[str] = None
    village_id: str
    village_name: Optional[str] = None
    ict_2g: Optional[AcceptanceStatus] = None
    ict_3g: Optional[AcceptanceStatus] = None
    ict_4g: Optional[AcceptanceStatus] = None
    ict_final: bool
    cra_2g: Optional[AcceptanceStatus] = None
    cra_3g: Optional[AcceptanceStatus] = None
    cra_4g: Optional[AcceptanceStatus] = None
    cra_final: bool
    depreciation_status: Optional[str] = None


class AcceptanceListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AcceptanceListItem]


# ---------------------------------------------------------------------------
# Impediments — Rule 4: registry integrity + 15-char compliance hook
# ---------------------------------------------------------------------------

class ImpedimentCreate(BaseModel):
    entity_type: ImpedimentEntityType
    entity_id: uuid.UUID
    category: BlockCategory
    comment: str = Field(min_length=15, max_length=2000)


class ImpedimentRead(ORMBase):
    id: uuid.UUID
    entity_type: ImpedimentEntityType
    entity_id: uuid.UUID
    category: str
    comment: str
    reported_by: uuid.UUID
    resolved_at: Optional[datetime]
    created_at: datetime


# ---------------------------------------------------------------------------
# Rule 2: Pending Change resolution (PM/Admin only)
# ---------------------------------------------------------------------------

class PendingChangeResolve(BaseModel):
    decision: str = Field(pattern="^(accepted|ignored|flagged)$")


# ---------------------------------------------------------------------------
# Province — geographic backbone; Admin assigns Regional Manager / PSO
# Coordinator ownership per province here (User Management).
# ---------------------------------------------------------------------------

class ProvinceRead(BaseModel):
    id: uuid.UUID
    name: str
    cra_region: str
    regional_manager_id: Optional[uuid.UUID] = None
    regional_manager_name: Optional[str] = None
    pso_coordinator_id: Optional[uuid.UUID] = None
    pso_coordinator_name: Optional[str] = None


class ProvinceUpdate(BaseModel):
    """Full-replace semantics: the caller always sends both fields (the
    Province Assignments table always has the complete current state loaded
    client-side), so there's no ambiguity between 'omitted' and 'cleared'."""
    regional_manager_id: Optional[uuid.UUID] = None
    pso_coordinator_id: Optional[uuid.UUID] = None
