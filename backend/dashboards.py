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

from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, and_, extract, func, or_, select
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
        # Built ONCE and reused in both SELECT and GROUP BY: Postgres requires
        # the grouped expression to be the exact same construct as what's
        # selected, and two separate func.coalesce(...) calls compile to two
        # distinct parameterized expressions even though they look identical
        # in source (SQLite doesn't enforce this, which is how this shipped).
        coord_name = func.coalesce(User.full_name, "Unassigned coordinator")
        per_coord = db.execute(
            select(coord_name, func.count(VillageAcceptance.id))
            .select_from(VillageAcceptance)
            .join(Site, Site.id == VillageAcceptance.site_id)
            .join(Province, Province.id == Site.province_id)
            .outerjoin(User, User.id == Province.pso_coordinator_id)
            .where(cond)
            .group_by(coord_name)
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


# ===========================================================================
# Scoped dashboards (Coordinator / Contractor / Regional Manager)
#
# These share one engine: resolve the caller's scope to a set of site ids,
# pull the in-scope acceptance rows once, and summarize in Python. Row counts
# per scope are small (a few provinces / a contractor's assigned sites), so
# Python aggregation stays clear and correct without elaborate SQL.
# ===========================================================================

_REJECTED = "rejected"


def _as_utc(dt):
    """SQLite returns naive datetimes; treat naive as UTC so month comparisons
    work on both SQLite (dev) and Postgres (prod)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _province_scope_site_ids(db: Session, owner_col, user_id):
    """Site ids in provinces owned by this user (owner_col is
    Province.pso_coordinator_id or Province.regional_manager_id)."""
    prov_ids = select(Province.id).where(owner_col == user_id).scalar_subquery()
    return select(Site.id).where(Site.province_id.in_(prov_ids), Site.deleted_at.is_(None))


def _contractor_scope_site_ids(db: Session, user_id):
    """Site ids where this contractor holds an active assignment."""
    return (
        select(WorkItem.site_id)
        .join(ContractorAssignment, ContractorAssignment.work_item_id == WorkItem.id)
        .where(ContractorAssignment.contractor_id == user_id, ContractorAssignment.ended_at.is_(None))
        .distinct()
    )


def _pct(part, total):
    return round(part / total * 100, 1) if total else 0.0


def _acceptance_summary(db: Session, site_ids_sq):
    """Pull in-scope acceptance rows once and derive every acceptance block:
    pending ICT/CRA, full status per province (ICT) and per CRA region (CRA),
    the two cross-gaps, and month-to-date approvals."""
    rows = db.execute(
        select(
            Site.province_name, Province.cra_region,
            VillageAcceptance.ict_2g, VillageAcceptance.ict_3g, VillageAcceptance.ict_4g,
            VillageAcceptance.ict_final, VillageAcceptance.ict_approved_at,
            VillageAcceptance.cra_2g, VillageAcceptance.cra_3g, VillageAcceptance.cra_4g,
            VillageAcceptance.cra_final, VillageAcceptance.cra_approved_at,
        )
        .select_from(VillageAcceptance)
        .join(Site, Site.id == VillageAcceptance.site_id)
        .join(Province, Province.id == Site.province_id)
        .where(VillageAcceptance.site_id.in_(site_ids_sq))
    ).all()

    month_start = _month_start()

    def blank():
        return {"total": 0, "approved": 0, "rejected": 0, "pending": 0}

    ict_by_prov, cra_by_region = {}, {}
    pending_ict = pending_cra = 0
    ict_not_cra = cra_not_ict = 0
    ict_month = cra_month = 0
    has_ict_total = has_cra_total = 0

    for r in rows:
        ict_techs = [r.ict_2g, r.ict_3g, r.ict_4g]
        cra_techs = [r.cra_2g, r.cra_3g, r.cra_4g]
        has_ict = any(t is not None for t in ict_techs)
        has_cra = any(t is not None for t in cra_techs)

        if has_ict:
            has_ict_total += 1
            bucket = ict_by_prov.setdefault(r.province_name, blank())
            bucket["total"] += 1
            if r.ict_final:
                bucket["approved"] += 1
            elif _REJECTED in ict_techs:
                bucket["rejected"] += 1
                pending_ict += 1
            else:
                bucket["pending"] += 1
                pending_ict += 1
        if has_cra:
            has_cra_total += 1
            bucket = cra_by_region.setdefault(r.cra_region, blank())
            bucket["total"] += 1
            if r.cra_final:
                bucket["approved"] += 1
            elif _REJECTED in cra_techs:
                bucket["rejected"] += 1
                pending_cra += 1
            else:
                bucket["pending"] += 1
                pending_cra += 1

        if r.ict_final and not r.cra_final and has_cra:
            ict_not_cra += 1
        if r.cra_final and not r.ict_final and has_ict:
            cra_not_ict += 1
        if r.ict_approved_at and _as_utc(r.ict_approved_at) >= month_start:
            ict_month += 1
        if r.cra_approved_at and _as_utc(r.cra_approved_at) >= month_start:
            cra_month += 1

    def rows_out(d, key_name):
        out = []
        for name, b in sorted(d.items(), key=lambda kv: kv[1]["total"], reverse=True):
            out.append({
                key_name: name, **b,
                "approved_pct": _pct(b["approved"], b["total"]),
                "rejected_pct": _pct(b["rejected"], b["total"]),
                "pending_pct": _pct(b["pending"], b["total"]),
            })
        return out

    return {
        "pending_ict": {"total": pending_ict, "pct_of_scope": _pct(pending_ict, has_ict_total)},
        "pending_cra": {"total": pending_cra, "pct_of_scope": _pct(pending_cra, has_cra_total)},
        "ict_status_by_province": rows_out(ict_by_prov, "province"),
        "cra_status_by_region": rows_out(cra_by_region, "cra_region"),
        "ict_approved_cra_not": ict_not_cra,
        "cra_approved_ict_not": cra_not_ict,
        "monthly_approvals": {"ict": ict_month, "cra": cra_month, "total": ict_month + cra_month},
    }


def build_coordinator_dashboard(db: Session, user: User) -> dict:
    site_ids = _province_scope_site_ids(db, Province.pso_coordinator_id, user.id).scalar_subquery()
    provinces = db.execute(
        select(Province.name).where(Province.pso_coordinator_id == user.id).order_by(Province.name)
    ).scalars().all()
    summary = _acceptance_summary(db, site_ids)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"role": "DT Coordinator", "who": user.full_name, "provinces": provinces},
        "sites": db.execute(select(func.count()).select_from(site_ids.element.subquery())).scalar() or 0,
        "villages": db.execute(
            select(func.count(Village.id)).where(Village.site_id.in_(site_ids), Village.deleted_at.is_(None))
        ).scalar() or 0,
        **summary,
    }


def build_regional_dashboard(db: Session, user: User) -> dict:
    site_ids = _province_scope_site_ids(db, Province.regional_manager_id, user.id).scalar_subquery()
    provinces = db.execute(
        select(Province.name).where(Province.regional_manager_id == user.id).order_by(Province.name)
    ).scalars().all()
    summary = _acceptance_summary(db, site_ids)
    on_air = db.execute(
        select(func.count(WorkItem.id)).where(WorkItem.is_on_air.is_(True), WorkItem.site_id.in_(site_ids))
    ).scalar() or 0
    dt_done = db.execute(
        select(func.count(WorkItem.id)).where(WorkItem.dt_status == _DONE, WorkItem.site_id.in_(site_ids))
    ).scalar() or 0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"role": "Regional Manager", "who": user.full_name, "provinces": provinces},
        "totals": {
            "on_air": on_air, "dt_done": dt_done,
            "ict_approved": sum(p["approved"] for p in summary["ict_status_by_province"]),
            "cra_approved": sum(r["approved"] for r in summary["cra_status_by_region"]),
        },
        **summary,
    }


def build_contractor_dashboard(db: Session, user: User) -> dict:
    site_ids = _contractor_scope_site_ids(db, user.id).scalar_subquery()
    summary = _acceptance_summary(db, site_ids)

    assigned_sites = db.execute(select(func.count()).select_from(site_ids.element.subquery())).scalar() or 0
    assigned_villages = db.execute(
        select(func.count(Village.id)).where(Village.site_id.in_(site_ids), Village.deleted_at.is_(None))
    ).scalar() or 0
    dt_done_sites = db.execute(
        select(func.count(func.distinct(WorkItem.site_id)))
        .where(WorkItem.dt_status == _DONE, WorkItem.site_id.in_(site_ids))
    ).scalar() or 0
    dt_done_villages = _villages_on_sites(db, and_(WorkItem.dt_status == _DONE, WorkItem.site_id.in_(site_ids)))
    remain_sites = db.execute(
        select(func.count(func.distinct(WorkItem.site_id)))
        .where(or_(WorkItem.dt_status.in_([_ONGOING, _PROBLEMATIC]), WorkItem.dt_status.is_(None)),
               WorkItem.site_id.in_(site_ids))
    ).scalar() or 0
    remain_villages = _villages_on_sites(
        db, and_(or_(WorkItem.dt_status.in_([_ONGOING, _PROBLEMATIC]), WorkItem.dt_status.is_(None)),
                 WorkItem.site_id.in_(site_ids)))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"role": "Contractor (DT SC)", "who": user.full_name},
        "assignment": {"sites": assigned_sites, "villages": assigned_villages},
        "dt_done": {"sites": dt_done_sites, "villages": dt_done_villages},
        "dt_remain": {"sites": remain_sites, "villages": remain_villages},
        **summary,
    }


# ===========================================================================
# Project Delivery Tab (PM/Admin) — site-grain delivery progress: KPIs with
# %/trend, ongoing/problematic breakdowns, and DT-delivery charts.
#
# IMPORTANT data-quality note: dt_date (the CPM "DT Date" column) is only
# populated for a fraction of completed drive tests in the real export
# (~37% of "Done" work items in the sample file) — it's sparse historical
# data, not guaranteed on every row. So:
#   * KPI counts (on-air / DT done / remained) use dt_status, which IS
#     reliable on every row — these are exact.
#   * The yearly/monthly delivery CHARTS can only bucket work items that
#     happen to have a dt_date, so their bars necessarily sum to less than
#     the "Total Drive Test" KPI. This is a real data gap, not a bug — it's
#     surfaced via `dt_delivery_dated_count` so the UI can caption it.
#   * The per-subcontractor TOTAL (no date needed) uses dt_status == done
#     directly, so it IS the full, accurate count.
# ===========================================================================

def build_project_delivery_dashboard(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    today = now.date()

    # Same grain as the KPI counts themselves (Work Item = Site+SiteType,
    # "Index 1") — using distinct Site count here would mismatch grain for
    # any site with 2+ site types and could push a percentage over 100%.
    total_work_items = db.execute(select(func.count(WorkItem.id))).scalar() or 0
    on_air_sites = db.execute(select(func.count(WorkItem.id)).where(WorkItem.is_on_air.is_(True))).scalar() or 0
    dt_done_sites = db.execute(select(func.count(WorkItem.id)).where(WorkItem.dt_status == _DONE)).scalar() or 0
    remained_sites = db.execute(
        select(func.count(WorkItem.id)).where(WorkItem.dt_status.in_([_ONGOING, _PROBLEMATIC]))
    ).scalar() or 0

    def delta(metric, live):
        base = _kpi_delta(db, metric)
        return None if base is None else live - base

    # --- Ongoing sites per subcontractor, each with a per-province breakdown ---
    # Built once, reused in SELECT + GROUP BY — see the identical note in
    # build_pm_dashboard's `pending()` for why this matters on Postgres.
    sc_name = func.coalesce(WorkItem.dt_subcontractor_name, "Unassigned")
    ongoing_rows = db.execute(
        select(sc_name, Site.province_name, func.count(WorkItem.id))
        .join(Site, Site.id == WorkItem.site_id)
        .where(WorkItem.dt_status == _ONGOING)
        .group_by(sc_name, Site.province_name)
    ).all()
    by_sc: dict[str, dict] = {}
    for sc, prov, cnt in ongoing_rows:
        entry = by_sc.setdefault(sc, {"subcontractor": sc, "count": 0, "by_province": []})
        entry["count"] += cnt
        entry["by_province"].append({"province": prov, "count": cnt})
    ongoing_by_subcontractor = sorted(by_sc.values(), key=lambda r: r["count"], reverse=True)
    for entry in ongoing_by_subcontractor:
        entry["by_province"].sort(key=lambda r: r["count"], reverse=True)

    # --- Problematic sites per category, each with a per-province breakdown ---
    prob_rows = db.execute(
        select(WorkItem.dt_problematic_category, Site.province_name, func.count(WorkItem.id))
        .join(Site, Site.id == WorkItem.site_id)
        .where(WorkItem.dt_status == _PROBLEMATIC, WorkItem.dt_problematic_category.isnot(None))
        .group_by(WorkItem.dt_problematic_category, Site.province_name)
    ).all()
    by_cat: dict[str, dict] = {}
    for cat, prov, cnt in prob_rows:
        entry = by_cat.setdefault(cat, {"category": cat, "count": 0, "by_province": []})
        entry["count"] += cnt
        entry["by_province"].append({"province": prov, "count": cnt})
    problematic_by_category = sorted(by_cat.values(), key=lambda r: r["count"], reverse=True)
    for entry in problematic_by_category:
        entry["by_province"].sort(key=lambda r: r["count"], reverse=True)

    # --- Yearly delivery chart (only work items with a recorded dt_date) ---
    dated_total = db.execute(select(func.count(WorkItem.id)).where(WorkItem.dt_date.isnot(None))).scalar() or 0
    yearly = db.execute(
        select(extract("year", WorkItem.dt_date).label("y"), func.count(WorkItem.id))
        .where(WorkItem.dt_date.isnot(None))
        .group_by("y").order_by("y")
    ).all()
    yearly_delivery = [{"year": int(y), "count": c} for y, c in yearly]

    # --- Monthly delivery, current calendar year (12 months, zero-filled) ---
    monthly = dict(db.execute(
        select(extract("month", WorkItem.dt_date).label("m"), func.count(WorkItem.id))
        .where(WorkItem.dt_date.isnot(None), extract("year", WorkItem.dt_date) == today.year)
        .group_by("m")
    ).all())
    monthly_this_year = [{"month": m, "count": int(monthly.get(m) or monthly.get(float(m), 0))} for m in range(1, 13)]

    # --- Current month KPI + vs last month (both derived directly from
    # dt_date, no snapshot table needed — these are dated historical events). ---
    this_month_count = db.execute(
        select(func.count(WorkItem.id)).where(
            WorkItem.dt_date.isnot(None),
            extract("year", WorkItem.dt_date) == today.year,
            extract("month", WorkItem.dt_date) == today.month,
        )
    ).scalar() or 0
    last_month_date = today.replace(day=1) - timedelta(days=1)
    last_month_count = db.execute(
        select(func.count(WorkItem.id)).where(
            WorkItem.dt_date.isnot(None),
            extract("year", WorkItem.dt_date) == last_month_date.year,
            extract("month", WorkItem.dt_date) == last_month_date.month,
        )
    ).scalar() or 0

    # --- Per-subcontractor total delivered (no date needed -> exact) ---
    by_sc_total = db.execute(
        select(sc_name, func.count(WorkItem.id))
        .where(WorkItem.dt_status == _DONE)
        .group_by(sc_name)
        .order_by(func.count(WorkItem.id).desc())
    ).all()

    return {
        "generated_at": now.isoformat(),
        "kpis": {
            "on_air": {"count": on_air_sites, "pct_of_total": _pct(on_air_sites, total_work_items),
                       "delta": delta("on_air", on_air_sites)},
            "drive_test": {"count": dt_done_sites, "pct_of_on_air": _pct(dt_done_sites, on_air_sites),
                           "delta": delta("dt_done", dt_done_sites)},
            "remained": {"count": remained_sites, "pct_of_on_air": _pct(remained_sites, on_air_sites),
                         "delta": delta("remained", remained_sites)},
        },
        "ongoing_by_subcontractor": ongoing_by_subcontractor,
        "problematic_by_category": problematic_by_category,
        "dt_delivery_dated_count": dated_total,
        "yearly_delivery": yearly_delivery,
        "monthly_this_year": monthly_this_year,
        "current_month": {"year": today.year, "month": today.month, "count": this_month_count,
                          "delta": this_month_count - last_month_count},
        "by_subcontractor_total": [{"subcontractor": sc, "count": c} for sc, c in by_sc_total],
    }
