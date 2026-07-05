"""
Action Center — the per-user "what needs me" inbox.

Not a table and not a notification queue: it's derived live from the same
operational data the dashboards read, filtered to the current user's role
and scope, so it can never drift out of sync with reality. Each role sees
only the items it can actually act on:

  * Project Manager / Admin — drive tests awaiting PM approval, and CPM
    conflicts awaiting a review decision.
  * DT Coordinator — drive tests awaiting stage-1 validation, and villages
    still waiting on ICT / CRA, all scoped to the provinces they coordinate.
  * Field Subcontractor — work items with a returned (rejected) drive test
    to resubmit, and freshly-assigned work items with no drive test yet.
  * Regional Manager — informational counts of ICT / CRA still open in their
    region (they can't act, so these are view-only).
  * Finance / Viewer — nothing actionable.

Every card carries a full `count` plus a bounded `items` sample (so a user
with thousands of open villages still gets a fast, small response).
"""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from enums import DriveTestStatus
from models import (
    ContractorAssignment, DriveTest, PendingChange, Province, Site,
    User, VillageAcceptance, WorkItem,
)

_SAMPLE = 25


def _card(key: str, title: str, count: int, items: list) -> dict:
    return {"key": key, "title": title, "count": count, "items": items}


def _province_site_ids(owner_col, user_id):
    prov_ids = select(Province.id).where(owner_col == user_id).scalar_subquery()
    return select(Site.id).where(Site.province_id.in_(prov_ids), Site.deleted_at.is_(None))


# --- individual card builders ------------------------------------------------

def _dt_awaiting(db: Session, status: str, site_scope=None) -> tuple[int, list]:
    q = (
        select(DriveTest.id, DriveTest.work_item_id, DriveTest.delivery_date,
               DriveTest.revision_no, Site.site_id, WorkItem.site_type)
        .join(WorkItem, WorkItem.id == DriveTest.work_item_id)
        .join(Site, Site.id == WorkItem.site_id)
        .where(DriveTest.status == status)
    )
    if site_scope is not None:
        q = q.where(WorkItem.site_id.in_(site_scope))
    count = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    rows = db.execute(q.order_by(DriveTest.created_at).limit(_SAMPLE)).all()
    items = [
        {"drive_test_id": str(r[0]), "work_item_id": str(r[1]),
         "delivery_date": r[2].isoformat() if r[2] else None,
         "revision_no": r[3], "site_business_id": r[4], "site_type": r[5]}
        for r in rows
    ]
    return count, items


def _villages_waiting(db: Session, side: str, site_scope=None) -> tuple[int, list]:
    """Villages where this side isn't Final yet but at least one of its
    technologies was requested (so it's genuinely awaiting action)."""
    final_col = getattr(VillageAcceptance, f"{side}_final")
    g2 = getattr(VillageAcceptance, f"{side}_2g")
    g3 = getattr(VillageAcceptance, f"{side}_3g")
    g4 = getattr(VillageAcceptance, f"{side}_4g")
    q = (
        select(VillageAcceptance.id, Site.site_id, Site.province_name, VillageAcceptance.village_id)
        .join(Site, Site.id == VillageAcceptance.site_id)
        .where(final_col.is_(False), or_(g2.isnot(None), g3.isnot(None), g4.isnot(None)))
    )
    if site_scope is not None:
        q = q.where(VillageAcceptance.site_id.in_(site_scope))
    count = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    rows = db.execute(q.order_by(Site.site_id, VillageAcceptance.village_id).limit(_SAMPLE)).all()
    items = [
        {"acceptance_id": str(r[0]), "site_business_id": r[1],
         "province_name": r[2], "village_id": r[3]}
        for r in rows
    ]
    return count, items


def _cpm_conflicts(db: Session) -> tuple[int, list]:
    q = (
        select(PendingChange.id, PendingChange.field_name, PendingChange.old_value,
               PendingChange.new_value, Site.site_id, VillageAcceptance.village_id)
        .outerjoin(VillageAcceptance, VillageAcceptance.id == PendingChange.entity_id)
        .outerjoin(Site, Site.id == VillageAcceptance.site_id)
        .where(PendingChange.decision == "pending")
    )
    count = db.execute(select(func.count()).select_from(
        select(PendingChange.id).where(PendingChange.decision == "pending").subquery()
    )).scalar()
    rows = db.execute(q.order_by(PendingChange.created_at.desc()).limit(_SAMPLE)).all()
    items = [
        {"pending_change_id": str(r[0]), "field_name": r[1],
         "old_value": r[2], "new_value": r[3],
         "site_business_id": r[4], "village_id": r[5]}
        for r in rows
    ]
    return count, items


def _subcontractor_dt_cards(db: Session, user_id: uuid.UUID) -> list[dict]:
    """'Returned' (latest DT rejected -> resubmit) and 'awaiting submission'
    (assigned, never drive-tested) — disjoint, computed from the small set of
    a contractor's assigned work items."""
    assigned = db.execute(
        select(WorkItem.id, Site.site_id, WorkItem.site_type)
        .join(ContractorAssignment, ContractorAssignment.work_item_id == WorkItem.id)
        .join(Site, Site.id == WorkItem.site_id)
        .where(ContractorAssignment.contractor_id == user_id, ContractorAssignment.ended_at.is_(None))
    ).all()
    if not assigned:
        return [_card("returned_dt", "Returned drive tests to resubmit", 0, []),
                _card("awaiting_dt", "New assignments needing a drive test", 0, [])]

    wi_meta = {r[0]: (r[1], r[2]) for r in assigned}
    # latest DT status per assigned work item
    dt_rows = db.execute(
        select(DriveTest.work_item_id, DriveTest.status, DriveTest.revision_no)
        .where(DriveTest.work_item_id.in_(list(wi_meta)))
    ).all()
    latest: dict[uuid.UUID, tuple] = {}
    for wid, status, rev in dt_rows:
        if wid not in latest or rev > latest[wid][1]:
            latest[wid] = (status, rev)

    returned, awaiting = [], []
    for wid, (sid, stype) in wi_meta.items():
        entry = {"work_item_id": str(wid), "site_business_id": sid, "site_type": stype}
        if wid not in latest:
            awaiting.append(entry)
        elif latest[wid][0] == DriveTestStatus.REJECTED.value:
            returned.append(entry)
        # active (submitted/under_review) or approved -> no action needed
    return [
        _card("returned_dt", "Returned drive tests to resubmit", len(returned), returned[:_SAMPLE]),
        _card("awaiting_dt", "New assignments needing a drive test", len(awaiting), awaiting[:_SAMPLE]),
    ]


# --- entry point -------------------------------------------------------------

def build_action_center(db: Session, user: User) -> dict:
    role = user.role
    cards: list[dict] = []

    if role in ("admin", "project_manager"):
        n, items = _dt_awaiting(db, DriveTestStatus.UNDER_REVIEW.value)
        cards.append(_card("dt_pm_approval", "Drive tests awaiting your approval", n, items))
        n, items = _cpm_conflicts(db)
        cards.append(_card("cpm_conflicts", "CPM conflicts to review", n, items))

    elif role == "dt_coordinator":
        scope = _province_site_ids(Province.pso_coordinator_id, user.id).scalar_subquery()
        n, items = _dt_awaiting(db, DriveTestStatus.SUBMITTED.value, scope)
        cards.append(_card("dt_validation", "Drive tests to validate", n, items))
        n, items = _villages_waiting(db, "ict", scope)
        cards.append(_card("waiting_ict", "Villages waiting on ICT", n, items))
        n, items = _villages_waiting(db, "cra", scope)
        cards.append(_card("waiting_cra", "Villages waiting on CRA", n, items))

    elif role == "field_subcontractor":
        cards.extend(_subcontractor_dt_cards(db, user.id))

    elif role == "regional_manager":
        scope = _province_site_ids(Province.regional_manager_id, user.id).scalar_subquery()
        n, items = _villages_waiting(db, "ict", scope)
        cards.append(_card("waiting_ict", "Villages waiting on ICT (region)", n, items))
        n, items = _villages_waiting(db, "cra", scope)
        cards.append(_card("waiting_cra", "Villages waiting on CRA (region)", n, items))

    # finance / viewer: nothing actionable
    total = sum(c["count"] for c in cards)
    return {"role": role, "total": total, "cards": cards}
