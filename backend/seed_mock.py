"""
Generate a realistic MOCK dataset so the dashboards can be built and demoed
before the real CPM file arrives. Deterministic (fixed random seed) so every
run produces the same numbers.

Run order:
    python seed_admin.py <email> <name> <password>   # first admin
    python seed_provinces.py                          # provinces + RM/coordinators
    python seed_mock.py                               # <-- this: sites/villages/etc.

Re-running is safe: it clears the mock operational tables first (sites,
villages, work items, acceptance, assignments, snapshots, and the mock
contractor accounts) and rebuilds them. It never touches the province table,
the RM/Coordinator accounts, or any Admin account.

Everything is tied to the REAL province -> CRA-region -> coordinator mapping
already seeded, so per-province / per-coordinator / per-CRA-region breakdowns
and role scoping are exercised against true relationships.
"""

import random
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete

from auth import hash_password
from database import SessionLocal, init_db
from enums import (
    AcceptanceStatus, DepreciationStatus, DTProblematicCategory, DTProgressStatus, UserRole,
)
from models import (
    ContractorAssignment, MonthlyMetricSnapshot, Province, Site, User, Village,
    VillageAcceptance, WorkItem,
)

RNG = random.Random(20260703)  # deterministic

N_SITES = 420
CONTRACTORS = ["Pouya Field Services", "Alborz Tower Co.", "Zagros NWG", "Kavir Rollout", "Peyk Telecom"]
SITE_TYPES = ["New Site", "Upgrade"]


def _pick(weighted):
    """weighted = [(value, weight), ...]"""
    r = RNG.random() * sum(w for _, w in weighted)
    upto = 0
    for value, w in weighted:
        upto += w
        if r <= upto:
            return value
    return weighted[-1][0]


def _requested_gens():
    """Which of 2g/3g/4g this village requested."""
    return _pick([(["2g", "3g", "4g"], 6), (["2g", "4g"], 3), (["2g"], 1), (["4g"], 1)])


def _accept_status():
    return _pick([
        (AcceptanceStatus.APPROVED, 50),
        (AcceptanceStatus.SUBMITTED, 18),
        (AcceptanceStatus.NOT_SUBMITTED, 26),
        (AcceptanceStatus.REJECTED, 6),
    ])


def _approval_date():
    """Spread approvals across this month, last month, and earlier."""
    today = date.today()
    bucket = _pick([("this", 40), ("last", 30), ("older", 30)])
    if bucket == "this":
        return today - timedelta(days=RNG.randint(0, max(today.day - 1, 0)))
    if bucket == "last":
        first_this = today.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        return last_month_end - timedelta(days=RNG.randint(0, 27))
    return today - timedelta(days=RNG.randint(70, 400))


def clear_mock(db):
    db.execute(delete(MonthlyMetricSnapshot))
    db.execute(delete(ContractorAssignment))
    db.execute(delete(VillageAcceptance))
    db.execute(delete(Village))
    db.execute(delete(WorkItem))
    db.execute(delete(Site))
    # mock contractor accounts only (leave RM/coordinator/admin intact)
    db.execute(delete(User).where(User.email.like("contractor-%@uso.ir")))
    db.commit()


def seed_mock():
    init_db()
    db = SessionLocal()
    try:
        provinces = db.query(Province).all()
        if not provinces:
            raise SystemExit("No provinces found — run seed_provinces.py first.")
        coordinators = {p.pso_coordinator_id for p in provinces if p.pso_coordinator_id}

        clear_mock(db)

        # --- Contractors ---
        contractor_ids = []
        for name in CONTRACTORS:
            slug = name.lower().replace(" ", "").replace(".", "")
            u = User(id=uuid.uuid4(), email=f"contractor-{slug}@uso.ir", full_name=name,
                     role=UserRole.FIELD_SUBCONTRACTOR.value, hashed_password=hash_password("MockPass123!"))
            db.add(u)
            contractor_ids.append(u.id)
        db.flush()

        admin = db.query(User).filter(User.role == UserRole.ADMIN.value).first()
        assigner_id = admin.id if admin else contractor_ids[0]

        sites = villages = work_items = acceptances = assignments = 0
        now = datetime.now(timezone.utc)

        for i in range(N_SITES):
            prov = RNG.choice(provinces)
            official = RNG.random() < 0.75
            if official:
                site_code = f"{RNG.choice(['CE', 'E'])}{RNG.randint(1000, 9999)}"
                official_id, temp_id = site_code, None
            else:
                site_code = f"AMUSONEW{RNG.randint(100, 999)}"
                official_id, temp_id = None, site_code

            site = Site(
                id=uuid.uuid4(), site_id=f"{site_code}-{i}", official_site_id=official_id,
                temp_site_code=temp_id, province_id=prov.id, region_id=uuid.uuid4(),
                province_name=prov.name, region_name=prov.operational_region_name or f"R-{prov.cra_region}",
                on_air_date=date.today() - timedelta(days=RNG.randint(1, 180)),
            )
            db.add(site)
            sites += 1

            on_air = RNG.random() < 0.85
            # DT status: null = not started (feeds the assignable queue)
            dt_status = _pick([
                (DTProgressStatus.DONE, 52), (DTProgressStatus.ONGOING, 14),
                (DTProgressStatus.PROBLEMATIC, 16), (None, 18),
            ]) if on_air else None

            for stype in (SITE_TYPES if RNG.random() < 0.3 else SITE_TYPES[:1]):
                wi = WorkItem(
                    id=uuid.uuid4(), site_id=site.id, site_type=stype,
                    cpm_raw_status="راه_اندازی_دائم" if on_air else None, is_on_air=on_air,
                    dt_status=dt_status.value if dt_status else None,
                    dt_problematic_category=(RNG.choice(list(DTProblematicCategory)).value
                                             if dt_status == DTProgressStatus.PROBLEMATIC else None),
                    dt_subcontractor_name=(RNG.choice(CONTRACTORS) if dt_status == DTProgressStatus.DONE else None),
                    depreciation_status=_pick([(DepreciationStatus.REMAIN.value, 6),
                                               (DepreciationStatus.WAITING.value, 3),
                                               (DepreciationStatus.DEPRECIATED.value, 2), (None, 4)]),
                )
                db.add(wi)
                work_items += 1

                # Assign some on-air work items (leave not-started ones mostly
                # unassigned so the Assignment Queue has content).
                if on_air and dt_status is not None and RNG.random() < 0.7:
                    db.add(ContractorAssignment(
                        id=uuid.uuid4(), work_item_id=wi.id, contractor_id=RNG.choice(contractor_ids),
                        assigned_by=assigner_id, assigned_at=now, remark="mock assignment",
                    ))
                    assignments += 1

            # Villages (hadaf) + acceptance
            for v in range(RNG.randint(1, 3)):
                vcode = f"V{RNG.randint(10000, 99999)}"
                db.add(Village(id=uuid.uuid4(), site_id=site.id, village_id=vcode,
                               village_name=f"Village {vcode}", is_on_air=on_air))
                villages += 1

                va = VillageAcceptance(id=uuid.uuid4(), site_id=site.id, village_id=vcode,
                                       depreciation_status=_pick([(DepreciationStatus.REMAIN.value, 6),
                                                                  (DepreciationStatus.DEPRECIATED.value, 2),
                                                                  (None, 4)]))
                gens = _requested_gens()
                for gen in gens:
                    setattr(va, f"ict_{gen}", _accept_status())
                    # CRA tends to lag ICT a little.
                    setattr(va, f"cra_{gen}", _pick([
                        (AcceptanceStatus.APPROVED, 40), (AcceptanceStatus.SUBMITTED, 20),
                        (AcceptanceStatus.NOT_SUBMITTED, 34), (AcceptanceStatus.REJECTED, 6),
                    ]))
                va.recompute_finals()
                coord_id = prov.pso_coordinator_id
                if va.ict_final:
                    va.ict_approved_by = coord_id
                    va.ict_approved_at = datetime.combine(_approval_date(), datetime.min.time(), tzinfo=timezone.utc)
                    va.ict_letter_number = f"ICT-{RNG.randint(1000, 9999)}"
                    va.ict_letter_date = va.ict_approved_at.date()
                if va.cra_final:
                    va.cra_approved_by = coord_id
                    va.cra_approved_at = datetime.combine(_approval_date(), datetime.min.time(), tzinfo=timezone.utc)
                    va.cra_letter_number = f"CRA-{RNG.randint(1000, 9999)}"
                    va.cra_letter_date = va.cra_approved_at.date()
                db.add(va)
                acceptances += 1

        db.commit()

        # --- Opening snapshots for the 3 headline KPIs, so "+/- vs last month"
        # shows realistic movement in the demo. Real deployments accumulate
        # these from a scheduled job; here we back-fill an opening baseline
        # slightly below live so the deltas read positive. ---
        period = date.today().strftime("%Y-%m")
        from sqlalchemy import func, select
        live_on_air = db.execute(select(func.count(WorkItem.id)).where(WorkItem.is_on_air.is_(True))).scalar()
        live_dt_done = db.execute(select(func.count(WorkItem.id)).where(WorkItem.dt_status == "done")).scalar()
        live_remained = db.execute(select(func.count(WorkItem.id)).where(WorkItem.dt_status.in_(["ongoing", "problematic"]))).scalar()
        for metric, live in [("on_air", live_on_air), ("dt_done", live_dt_done), ("remained", live_remained)]:
            db.add(MonthlyMetricSnapshot(id=uuid.uuid4(), period=period, scope_type="global",
                                         scope_key="", metric=metric, value=max(live - RNG.randint(8, 40), 0)))
        db.commit()

        print(f"Mock data built (deterministic):")
        print(f"  sites={sites}  work_items={work_items}  villages={villages}  "
              f"acceptance={acceptances}  assignments={assignments}")
        print(f"  contractors={len(contractor_ids)}  coordinators={len(coordinators)}  provinces={len(provinces)}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_mock()
