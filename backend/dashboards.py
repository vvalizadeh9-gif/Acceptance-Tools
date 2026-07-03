"""
Dashboard query logic, kept out of main.py so the aggregate SQL lives in one
readable place. Each build_*_dashboard(db) returns a plain dict the API hands
straight back as JSON.

Definitions (shared across roles):
  * On-Air / Drive-Test / Remained are counted at the Work Item grain
    (Site + Site Type = Index 1). "hadaf villages" sub-counts are Village
    rows (the importer only ever creates hadaf villages).
  * A village is "pending ICT" when it has at least one requested ICT
    technology and ict_final is not yet true; same for CRA.
  * "Final" is the stored cached flag (all requested techs approved).
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, and_, func, or_, select
from sqlalchemy.orm import Session

from models import (
    ContractorAssignment, MonthlyMetricSnapshot, Province, Site, User, Village,
    VillageAcceptance, WorkItem,
)

_ONGOING = "ongoing"
_PROBLEMATIC = "problematic"
_DONE = "done"


def _has_ict(model=VillageAcceptance):
    return or_(model.ict_2g.isnot(None), model.ict_3g.isnot(None), model.ict_4g.isnot(None))


def _has_cra(model=VillageAcceptance):
    return or_(model.cra_2g.isnot(None), model.cra_3g.isnot(None), model.cra_4g.isnot(None))


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _kpi_delta(db: Session, metric: str) -> int | None:
    """live count minus this month's opening snapshot (None if no baseline)."""
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    base = db.execute(
        select(MonthlyMetricSnapshot.value).where(
            MonthlyMetricSnapshot.period == period,
            MonthlyMetricSnapshot.scope_type == "global",
            MonthlyMetricSnapshot.scope_key == "",
            MonthlyMetricSnapshot.metric == metric,
        )
    ).scalar()
    return base  # caller subtracts; kept separate so we return None cleanly


def _villages_on_sites(db: Session, site_filter) -> int:
    """Count on-air villages whose site matches the given WorkItem filter."""
    site_ids = select(WorkItem.site_id).where(site_filter).distinct()
    return db.execute(
        select(func.count(Village.id)).where(
            Village.deleted_at.is_(None), Village.is_on_air.is_(True), Village.site_id.in_(site_ids)
        )
    ).scalar() or 0


def build_pm_dashboard(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    period = now.strftime("%Y-%m")
    month_start = _month_start()

    # --- KPI counts (Work Item grain) ---
    on_air_sites = db.execute(select(func.count(WorkItem.id)).where(WorkItem.is_on_air.is_(True))).scalar() or 0
    dt_done_sites = db.execute(select(func.count(WorkItem.id)).where(WorkItem.dt_status == _DONE)).scalar() or 0
    remained_sites = db.execute(
        select(func.count(WorkItem.id)).where(WorkItem.dt_status.in_([_ONGOING, _PROBLEMATIC]))
    ).scalar() or 0

    on_air_villages = db.execute(
        select(func.count(Village.id)).where(Village.deleted_at.is_(None), Village.is_on_air.is_(True))
    ).scalar() or 0
    dt_done_villages = _villages_on_sites(db, WorkItem.dt_status == _DONE)
    remained_villages = _villages_on_sites(db, WorkItem.dt_status.in_([_ONGOING, _PROBLEMATIC]))

    def delta(metric, live):
        base = _kpi_delta(db, metric)
        return None if base is None else live - base

    # --- Section 1: on-air vs DT gap ---
    ongoing = db.execute(select(func.count(WorkItem.id)).where(WorkItem.dt_status == _ONGOING)).scalar() or 0
    problematic = db.execute(select(func.count(WorkItem.id)).where(WorkItem.dt_status == _PROBLEMATIC)).scalar() or 0
    by_cat = db.execute(
        select(WorkItem.dt_problematic_category, func.count(WorkItem.id))
        .where(WorkItem.dt_status == _PROBLEMATIC, WorkItem.dt_problematic_category.isnot(None))
        .group_by(WorkItem.dt_problematic_category)
        .order_by(func.count(WorkItem.id).desc())
    ).all()

    # --- Section 2: assignable queue (on-air, DT not started, unassigned) ---
    assigned_wi = select(ContractorAssignment.work_item_id).where(ContractorAssignment.ended_at.is_(None))
    assignable_filter = and_(
        WorkItem.is_on_air.is_(True), WorkItem.dt_status.is_(None), WorkItem.id.notin_(assigned_wi)
    )
    assignable_total = db.execute(select(func.count(WorkItem.id)).where(assignable_filter)).scalar() or 0
    assignable_by_prov = db.execute(
        select(Site.province_name, func.count(WorkItem.id))
        .join(Site, Site.id == WorkItem.site_id)
        .where(assignable_filter)
        .group_by(Site.province_name)
        .order_by(func.count(WorkItem.id).desc())
    ).all()

    # --- Sections 3 & 4: pending ICT / CRA, total + per coordinator ---
    def pending(has_expr, final_col):
        cond = and_(has_expr, final_col.is_(False))
        total = db.execute(select(func.count(VillageAcceptance.id)).where(cond)).scalar() or 0
        per_coord = db.execute(
            select(func.coalesce(User.full_name, "Unassigned coordinator"), func.count(VillageAcceptance.id))
            .select_from(VillageAcceptance)
            .join(Site, Site.id == VillageAcceptance.site_id)
            .join(Province, Province.id == Site.province_id)
            .outerjoin(User, User.id == Province.pso_coordinator_id)
            .where(cond)
            .group_by(func.coalesce(User.full_name, "Unassigned coordinator"))
            .order_by(func.count(VillageAcceptance.id).desc())
        ).all()
        return total, [{"name": n, "count": c} for n, c in per_coord]

    pending_ict_total, pending_ict_by_coord = pending(_has_ict(), VillageAcceptance.ict_final)
    pending_cra_total, pending_cra_by_coord = pending(_has_cra(), VillageAcceptance.cra_final)

    # --- Sections 5 & 6: cross gaps ---
    ict_not_cra = db.execute(
        select(func.count(VillageAcceptance.id)).where(
            VillageAcceptance.ict_final.is_(True), VillageAcceptance.cra_final.is_(False), _has_cra())
    ).scalar() or 0
    cra_not_ict = db.execute(
        select(func.count(VillageAcceptance.id)).where(
            VillageAcceptance.cra_final.is_(True), VillageAcceptance.ict_final.is_(False), _has_ict())
    ).scalar() or 0

    # --- Section 7: this month's approvals per person ---
    def monthly_by_person(approved_by_col, approved_at_col):
        return dict(db.execute(
            select(approved_by_col, func.count(VillageAcceptance.id))
            .where(approved_at_col >= month_start, approved_by_col.isnot(None))
            .group_by(approved_by_col)
        ).all())

    ict_by_person = monthly_by_person(VillageAcceptance.ict_approved_by, VillageAcceptance.ict_approved_at)
    cra_by_person = monthly_by_person(VillageAcceptance.cra_approved_by, VillageAcceptance.cra_approved_at)
    people_ids = set(ict_by_person) | set(cra_by_person)
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(people_ids))).all()) if people_ids else {}
    monthly = sorted(
        [
            {"name": names.get(pid, "—"), "ict": ict_by_person.get(pid, 0),
             "cra": cra_by_person.get(pid, 0),
             "total": ict_by_person.get(pid, 0) + cra_by_person.get(pid, 0)}
            for pid in people_ids
        ],
        key=lambda r: r["total"], reverse=True,
    )

    last_import = db.execute(select(func.max(Site.created_at))).scalar()

    return {
        "generated_at": now.isoformat(),
        "last_cpm_import": last_import.isoformat() if last_import else None,
        "kpis": {
            "on_air": {"sites": on_air_sites, "villages": on_air_villages, "delta": delta("on_air", on_air_sites)},
            "drive_test": {"sites": dt_done_sites, "villages": dt_done_villages, "delta": delta("dt_done", dt_done_sites)},
            "remained": {"sites": remained_sites, "villages": remained_villages, "delta": delta("remained", remained_sites)},
        },
        "gap": {
            "total_remained": ongoing + problematic,
            "ongoing": ongoing,
            "problematic": problematic,
            "problematic_by_category": [{"category": cat, "count": c} for cat, c in by_cat],
        },
        "assignable": {
            "total": assignable_total,
            "by_province": [{"province": p, "count": c} for p, c in assignable_by_prov],
        },
        "pending_ict": {"total": pending_ict_total, "by_coordinator": pending_ict_by_coord},
        "pending_cra": {"total": pending_cra_total, "by_coordinator": pending_cra_by_coord},
        "ict_approved_cra_not": ict_not_cra,
        "cra_approved_ict_not": cra_not_ict,
        "monthly_approvals": monthly,
    }
