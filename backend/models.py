"""
SQLAlchemy 2.0 ORM models for the USO Delivery & Acceptance Management
Platform.

Covers the three aggregate layers from the blueprint (Site / Work Item /
Acceptance), plus two things the blueprint's DDL didn't include but that
real multi-user enforcement requires:

  - `User` — roles come from the requirements transcript, not the PDF
    (Admin, Project Manager, DT Coordinator, Field Subcontractor,
    Regional Manager, Viewer — six, not four).
  - `PendingChange` — the physical table backing Rule 2 (CPM Change
    Review Center). High/critical severity CPM deltas land here instead
    of mutating live rows, until a PM/Admin accepts, ignores, or flags
    them.

Field-level "Single Source Ownership" (Rule 1) is enforced at the API
layer (see schemas.py) — the ORM layer stores the data, it doesn't know
who's writing to it.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from enums import (
    AcceptanceStatus,
    ChangeDecision,
    ChangeSeverity,
    DepreciationStatus,
    DriveTestStatus,
    DTProblematicCategory,
    DTProgressStatus,
    HealthCheckStatus,
    ImpedimentEntityType,
    ReviewDecision,
    UserRole,
    WorkItemStatus,
)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(30), nullable=False)
    # Scopes down Regional Manager visibility to one region. Matched by
    # NAME against Site.region_name (same plain-text values, e.g. "R9") —
    # not by region_id, since there's no formal Region table yet and an
    # opaque UUID would be unusable for an Admin creating this account.
    region_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    region_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin','project_manager','dt_coordinator',"
            "'field_subcontractor','regional_manager','viewer')",
            name="chk_user_role_vocab",
        ),
    )


# ---------------------------------------------------------------------------
# Geography — the province reference table that all scoping joins through
# ---------------------------------------------------------------------------

class Province(Base):
    """One row per province (31 total). The single backbone every geographic
    breakdown and scope check joins through, because the three groupings the
    business uses — operational Regional Manager, PSO Coordinator, and CRA
    Region — are three *independent* partitions of the same provinces, and
    only the province itself is common to all of them.

    The primary key is deliberately the SAME deterministic UUID the CPM
    importer already derives from the province name (uuid5 over
    "province::<name>"), so existing Site.province_id values point straight
    at these rows with no importer change.

    - cra_region: fixed regulatory geography (one of 9 CRA regions).
    - operational_region_name: the CPM «منطقه» value, kept for reference/display.
    - regional_manager_id / pso_coordinator_id: current owners, editable by
      an Admin (people change roles). Coordinator scope cuts ACROSS regional
      managers, which is exactly why scope can't be a region string and has
      to live here per-province.
    """
    __tablename__ = "province"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    cra_region: Mapped[str] = mapped_column(String(50), nullable=False)
    operational_region_name: Mapped[str | None] = mapped_column(String(100))
    regional_manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("app_user.id", ondelete="SET NULL"))
    pso_coordinator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("app_user.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# A. Site Layer
# ---------------------------------------------------------------------------

class Site(Base):
    __tablename__ = "site"

    id: Mapped[uuid.UUID] = _uuid_pk()
    site_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # Resolved identity used as the business key above: official Irancell ID
    # when it exists, otherwise the temporary code. Both raw values are kept
    # separately here so the source is never ambiguous.
    official_site_id: Mapped[str | None] = mapped_column(String(50))
    temp_site_code: Mapped[str | None] = mapped_column(String(50))
    province_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    region_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Plain-text names, populated by the CPM importer. The UUIDs above are
    # deterministic (same name -> same id) but not human-readable on their
    # own — these make the Sites table actually usable without a separate
    # Province/Region lookup table.
    province_name: Mapped[str | None] = mapped_column(String(100))
    region_name: Mapped[str | None] = mapped_column(String(100))
    on_air_date: Mapped[date | None] = mapped_column(Date)
    assignment_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    villages: Mapped[list["Village"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    work_items: Mapped[list["WorkItem"]] = relationship(back_populates="site")


class Village(Base):
    __tablename__ = "village"

    id: Mapped[uuid.UUID] = _uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("site.id", ondelete="RESTRICT"), nullable=False)
    village_id: Mapped[str] = mapped_column(String(50), nullable=False)
    village_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # True if any CPM row for this site+village reported an on-air status
    # (راه_اندازی_دائم permanent or راه_اندازی_موقت temporary launch).
    is_on_air: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    site: Mapped["Site"] = relationship(back_populates="villages")

    __table_args__ = (UniqueConstraint("site_id", "village_id", name="uq_site_village_composite"),)


# ---------------------------------------------------------------------------
# B. Work Item Layer
# ---------------------------------------------------------------------------

class WorkItem(Base):
    __tablename__ = "work_item"

    id: Mapped[uuid.UUID] = _uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("site.id", ondelete="RESTRICT"), nullable=False)
    site_type: Mapped[str] = mapped_column(String(100), nullable=False)
    assignment_date: Mapped[date | None] = mapped_column(Date)
    # Denormalized cache of the state machine (Rule 3). Never written
    # directly by API consumers — recomputed from timeline_event.
    status: Mapped[WorkItemStatus] = mapped_column(String(20), nullable=False, default=WorkItemStatus.NEW)
    # Raw CPM "last stage" text and a derived on-air flag, populated by the
    # CPM importer. This is Index 1 from the operational procedure: unique
    # Site ID + Site Type combinations, e.g. "T2120-New Site".
    cpm_raw_status: Mapped[str | None] = mapped_column(String(100))
    is_on_air: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Drive-test progress at the site grain (the DT dashboards read this).
    # NULL until known; seeded from the one-time CPM import, app-managed after.
    dt_status: Mapped[DTProgressStatus | None] = mapped_column(String(20))
    # Only meaningful when dt_status == PROBLEMATIC.
    dt_problematic_category: Mapped[DTProblematicCategory | None] = mapped_column(String(30))
    # Date the drive test was delivered/completed (CPM "DT Date"). Drives the
    # monthly/yearly DT-delivery charts on the Project Delivery dashboard.
    dt_date: Mapped[date | None] = mapped_column(Date)
    # Historical DT subcontractor name from CPM (free text). Going forward the
    # authoritative assignment lives in ContractorAssignment; this is the
    # legacy record of who ran the drive test before the app existed.
    dt_subcontractor_name: Mapped[str | None] = mapped_column(String(255))
    # Site-grain half of "keep both" depreciation tracking.
    depreciation_status: Mapped[DepreciationStatus | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    site: Mapped["Site"] = relationship(back_populates="work_items")
    technologies: Mapped[list["WorkItemTechnology"]] = relationship(back_populates="work_item", cascade="all, delete-orphan")
    assignments: Mapped[list["ContractorAssignment"]] = relationship(back_populates="work_item")
    health_checks: Mapped[list["HealthCheck"]] = relationship(back_populates="work_item")
    drive_tests: Mapped[list["DriveTest"]] = relationship(back_populates="work_item")

    __table_args__ = (UniqueConstraint("site_id", "site_type", name="uq_site_type_composite"),)


class WorkItemTechnology(Base):
    __tablename__ = "work_item_technology"

    id: Mapped[uuid.UUID] = _uuid_pk()
    work_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("work_item.id", ondelete="CASCADE"), nullable=False)
    technology: Mapped[str] = mapped_column(String(20), nullable=False)
    on_air_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    work_item: Mapped["WorkItem"] = relationship(back_populates="technologies")


class ContractorAssignment(Base):
    __tablename__ = "contractor_assignment"

    id: Mapped[uuid.UUID] = _uuid_pk()
    work_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("work_item.id", ondelete="RESTRICT"), nullable=False)
    contractor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"), nullable=False)
    assigned_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NULL = active
    remark: Mapped[str | None] = mapped_column(Text)

    work_item: Mapped["WorkItem"] = relationship(back_populates="assignments")

    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= assigned_at", name="chk_assignment_timeline_logic"),
    )


class HealthCheck(Base):
    __tablename__ = "health_check"

    id: Mapped[uuid.UUID] = _uuid_pk()
    work_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("work_item.id", ondelete="RESTRICT"), nullable=False)
    contractor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"), nullable=False)
    status: Mapped[HealthCheckStatus] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    work_item: Mapped["WorkItem"] = relationship(back_populates="health_checks")


class DriveTest(Base):
    __tablename__ = "drive_test"

    id: Mapped[uuid.UUID] = _uuid_pk()
    work_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("work_item.id", ondelete="RESTRICT"), nullable=False)
    contractor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    report_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DriveTestStatus] = mapped_column(String(20), nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    work_item: Mapped["WorkItem"] = relationship(back_populates="drive_tests")
    reviews: Mapped[list["DriveTestReview"]] = relationship(back_populates="drive_test", cascade="all, delete-orphan")


class DriveTestReview(Base):
    __tablename__ = "drive_test_review"

    id: Mapped[uuid.UUID] = _uuid_pk()
    drive_test_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("drive_test.id", ondelete="RESTRICT"), nullable=False)
    reviewer: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"), nullable=False)
    review_level: Mapped[str] = mapped_column(String(50), nullable=False)
    decision: Mapped[ReviewDecision] = mapped_column(String(20), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    review_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    drive_test: Mapped["DriveTest"] = relationship(back_populates="reviews")


# ---------------------------------------------------------------------------
# C. Acceptance Layer
# ---------------------------------------------------------------------------

class VillageAcceptance(Base):
    """One row per village (Site + Village), holding both ICT and CRA
    acceptance. Restructured from the earlier one-row-per-technology layout:
    the CPM file carries 2G/3G/4G statuses plus a single Final/Comment/letter
    set per village, so a wide per-village row maps 1:1 to the source and is
    far easier to read when debugging.

    Per-technology status columns (ict_2g/3g/4g, cra_2g/3g/4g):
      * NULL  = that technology was not requested for this village.
      * otherwise an AcceptanceStatus (not_submitted / submitted / approved /
        rejected).

    Final columns (ict_final, cra_final) are a stored, cached boolean —
    recomputed by recompute_finals() whenever a per-tech status changes.
    Final is True when at least one technology is requested AND every
    requested (non-NULL) technology is APPROVED. Stored (not purely derived)
    so dashboard queries can filter on it directly, mirroring the existing
    WorkItem.status denormalized-cache pattern.
    """
    __tablename__ = "village_acceptance"

    id: Mapped[uuid.UUID] = _uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("site.id", ondelete="RESTRICT"), nullable=False)
    village_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # --- ICT ---
    ict_2g: Mapped[AcceptanceStatus | None] = mapped_column(String(20))
    ict_3g: Mapped[AcceptanceStatus | None] = mapped_column(String(20))
    ict_4g: Mapped[AcceptanceStatus | None] = mapped_column(String(20))
    ict_final: Mapped[bool] = mapped_column(default=False, nullable=False)
    ict_comment: Mapped[str | None] = mapped_column(Text)
    ict_letter_number: Mapped[str | None] = mapped_column(String(100))
    ict_letter_date: Mapped[date | None] = mapped_column(Date)
    ict_approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("app_user.id", ondelete="SET NULL"))
    ict_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- CRA ---
    cra_2g: Mapped[AcceptanceStatus | None] = mapped_column(String(20))
    cra_3g: Mapped[AcceptanceStatus | None] = mapped_column(String(20))
    cra_4g: Mapped[AcceptanceStatus | None] = mapped_column(String(20))
    cra_final: Mapped[bool] = mapped_column(default=False, nullable=False)
    cra_comment: Mapped[str | None] = mapped_column(Text)
    cra_letter_number: Mapped[str | None] = mapped_column(String(100))
    cra_letter_date: Mapped[date | None] = mapped_column(Date)
    cra_approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("app_user.id", ondelete="SET NULL"))
    cra_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Village-grain half of "keep both" depreciation tracking.
    depreciation_status: Mapped[DepreciationStatus | None] = mapped_column(String(30))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    letter_links: Mapped[list["LetterVillageMapping"]] = relationship(back_populates="village_acceptance")

    __table_args__ = (
        UniqueConstraint("site_id", "village_id", name="uq_acceptance_site_village"),
    )

    def recompute_finals(self) -> None:
        """Refresh the cached ict_final / cra_final flags from the per-tech
        statuses, and apply the depreciation golden rule. Call after any
        per-tech status change (and the CPM import calls it after loading).

        Golden rule: the moment BOTH ict_final and cra_final become true
        (every requested technology approved on both sides), the village is
        ready for depreciation review — auto-set depreciation_status to
        WAITING. Never downgrades an already-DEPRECIATED record: that's a
        terminal, finance-closed state the app must not undo.
        """
        def _final(statuses: list[AcceptanceStatus | None]) -> bool:
            requested = [s for s in statuses if s is not None]
            return bool(requested) and all(s == AcceptanceStatus.APPROVED for s in requested)

        self.ict_final = _final([self.ict_2g, self.ict_3g, self.ict_4g])
        self.cra_final = _final([self.cra_2g, self.cra_3g, self.cra_4g])

        if self.ict_final and self.cra_final and self.depreciation_status != DepreciationStatus.DEPRECIATED.value:
            self.depreciation_status = DepreciationStatus.WAITING.value


class Letter(Base):
    __tablename__ = "letter"

    id: Mapped[uuid.UUID] = _uuid_pk()
    letter_number: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    letter_date: Mapped[date] = mapped_column(Date, nullable=False)
    organization: Mapped[str] = mapped_column(String(100), nullable=False)
    province_or_region_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    pdf_attachment_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    village_links: Mapped[list["LetterVillageMapping"]] = relationship(back_populates="letter", cascade="all, delete-orphan")


class LetterVillageMapping(Base):
    """Rule 5: one letter clears many villages at once. Uploading a letter
    fans out to every linked village_acceptance row in one transaction —
    that fan-out is application logic (see the acceptance service), this
    table just records the links."""
    __tablename__ = "letter_village_mapping"

    id: Mapped[uuid.UUID] = _uuid_pk()
    letter_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("letter.id", ondelete="CASCADE"), nullable=False)
    village_acceptance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("village_acceptance.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    letter: Mapped["Letter"] = relationship(back_populates="village_links")
    village_acceptance: Mapped["VillageAcceptance"] = relationship(back_populates="letter_links")

    __table_args__ = (
        UniqueConstraint("letter_id", "village_acceptance_id", name="uq_letter_target_mapping"),
    )


# ---------------------------------------------------------------------------
# Logging, Audit Ledger & Impediments
# ---------------------------------------------------------------------------

class ImpedimentLog(Base):
    __tablename__ = "impediment_log"

    id: Mapped[uuid.UUID] = _uuid_pk()
    entity_type: Mapped[ImpedimentEntityType] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    reported_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # length() works on both SQLite and PostgreSQL; char_length() (from
        # the original DDL) is Postgres-only and breaks local SQLite dev.
        CheckConstraint("length(comment) >= 15", name="chk_comment_length_limit"),
    )


class TimelineEvent(Base):
    """The append-only ledger that Rule 3's state machine is derived from.
    WorkItem.status is a cache; this table is the actual source of truth."""
    __tablename__ = "timeline_event"

    id: Mapped[uuid.UUID] = _uuid_pk()
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("work_item.id", ondelete="CASCADE"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("site.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Rule 2: CPM Change Review Center (staging table for high/critical deltas)
# ---------------------------------------------------------------------------

class PendingChange(Base):
    """Not in the original DDL, but required to actually implement Rule 2.
    Low/medium severity CPM deltas apply directly; high/critical severity
    deltas (dropped technology, removed site) get written here instead of
    mutating live rows, and sit until a PM/Admin resolves them."""
    __tablename__ = "pending_change"

    id: Mapped[uuid.UUID] = _uuid_pk()
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[ChangeSeverity] = mapped_column(String(20), nullable=False)
    decision: Mapped[ChangeDecision] = mapped_column(String(20), default=ChangeDecision.PENDING, nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("app_user.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Monthly snapshots — the baseline every "+/- vs last month" delta compares to
# ---------------------------------------------------------------------------

class MonthlyMetricSnapshot(Base):
    """A point-in-time count captured at the start of each month, so the
    dashboards can show '+N / -N vs last month' for state counts (pending
    DT/ICT/CRA, on-air, etc.). The delta shown = live count minus this
    month's opening snapshot.

    Starts accumulating the day it's switched on — there is no historical
    back-fill, so the first month's deltas grow from zero, exactly as
    specified. (Event-based figures like 'approvals this month per person'
    do NOT use this table; they come straight from approved_at dates and are
    always exact.)

    One row per (period, scope_type, scope_key, metric):
      * period      — 'YYYY-MM'
      * scope_type  — global | province | coordinator | regional_manager |
                      cra_region | contractor
      * scope_key   — the province name / user id / CRA region name / '' for
                      global
      * metric      — pending_dt | pending_ict | pending_cra | on_air |
                      dt_done | ict_approved | cra_approved | ...
    """
    __tablename__ = "monthly_metric_snapshot"

    id: Mapped[uuid.UUID] = _uuid_pk()
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    metric: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("period", "scope_type", "scope_key", "metric", name="uq_snapshot_period_scope_metric"),
    )
