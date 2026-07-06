"""
BRIEF: this is the actual "waiter." It exposes a fixed menu of URLs
(routes) that the frontend — or a browser directly, for testing — can
call. Every route either needs no login (/health) or requires a valid
badge (JWT) and, for some, a specific role.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session, aliased

from auth import create_access_token, hash_password, verify_password
from captcha import generate_captcha, verify_captcha
from dashboards import (
    build_coordinator_dashboard, build_contractor_dashboard, build_pm_dashboard,
    build_project_delivery_dashboard, build_regional_dashboard,
)
from database import get_db
from deps import get_current_user, require_role
from import_cpm import import_cpm_bytes
from acceptance_service import register_letter, update_acceptance_side, village_name_map
from acceptance_dashboard import build_acceptance_dashboard
from action_center import build_action_center
from drive_test_service import (
    WorkflowError, coordinator_validate, pm_decide, submit_drive_test,
)
from models import (
    ContractorAssignment, DriveTest, DriveTestReview, Letter, LetterVillageMapping,
    PendingChange, Province, Site, User, Village, VillageAcceptance, WorkItem,
)
from schemas import (
    AcceptanceListItem, AcceptanceListResponse, AcceptanceSideUpdate, AssignmentRead,
    AssignSiteRequest, DriveTestApprove, DriveTestReject, DriveTestReviewItem,
    DriveTestSubmit, DriveTestRead, DriveTestValidate, LetterCreate, LetterRead,
    PendingChangeRead, PendingChangeResolve, ProvinceRead, ProvinceUpdate,
    SiteFilterOptions, SiteListItem, SiteListResponse, SiteRead, UserCreate, UserRead,
    UserUpdate, VillageAcceptanceRead,
)

app = FastAPI(title="USO Delivery & Acceptance Platform API")

# Allows the React frontend (running on a different address during
# development) to actually call this API from a browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your real domain once live
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """No login needed — just proves the server is alive and responding."""
    return {"status": "ok"}


@app.get("/auth/captcha")
def get_captcha():
    """Issue a fresh login security code: a noisy SVG image plus a short-lived
    signed token. No login required (this is what you call BEFORE logging in).
    The plaintext code lives only in the image; the token carries a salted
    hash of it, so it round-trips safely."""
    return generate_captcha()


@app.post("/auth/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    captcha_token: str = Form(...),
    captcha_code: str = Form(...),
    db: Session = Depends(get_db),
):
    """Verify the security code first, then the credentials. Ordering the
    captcha check first blunts credential-stuffing: an automated password
    guess can't even reach the password comparison without solving a fresh
    image each time."""
    if not verify_captcha(captcha_token, captcha_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect or expired security code")
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    token = create_access_token(subject=str(user.id), role=user.role)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/users/me", response_model=UserRead)
def read_own_profile(current_user: User = Depends(get_current_user)):
    """Any logged-in user, any role, can see their own profile."""
    return current_user


@app.get("/sites", response_model=SiteListResponse)
def list_sites(
    page: int = 1,
    page_size: int = 50,
    search: str = "",
    province: str = "",
    region: str = "",
    on_air: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Searchable, filterable, paginated site list.

    Per-role scoping (the gap flagged earlier as the biggest open risk):
      * Field Subcontractor: only sites where they hold an ACTIVE assignment
        (ContractorAssignment.ended_at IS NULL) on at least one work item.
      * Regional Manager: only sites in their own region.
      * Everyone else (Admin, PM, Coordinator, Viewer): unrestricted for now.
    """
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)

    villages_count = (
        select(Village.site_id, func.count(Village.id).label("vc"))
        .where(Village.deleted_at.is_(None))
        .group_by(Village.site_id)
        .subquery()
    )
    wi_count = (
        select(
            WorkItem.site_id,
            func.count(WorkItem.id).label("wc"),
            func.sum(func.cast(WorkItem.is_on_air, Integer)).label("on_air_wc"),
        )
        .group_by(WorkItem.site_id)
        .subquery()
    )
    # One active-assignment contractor name per site (if multiple work items
    # under a site have different contractors — rare, since our assign
    # action assigns the whole site at once — this just picks one via MIN,
    # which is fine as a summary indicator for the list view).
    assignment_by_site = (
        select(
            WorkItem.site_id,
            func.min(User.full_name).label("contractor_name"),
        )
        .join(ContractorAssignment, ContractorAssignment.work_item_id == WorkItem.id)
        .join(User, User.id == ContractorAssignment.contractor_id)
        .where(ContractorAssignment.ended_at.is_(None))
        .group_by(WorkItem.site_id)
        .subquery()
    )

    q = (
        select(
            Site,
            func.coalesce(villages_count.c.vc, 0).label("village_count"),
            func.coalesce(wi_count.c.wc, 0).label("work_item_count"),
            func.coalesce(wi_count.c.on_air_wc, 0).label("on_air_work_item_count"),
            assignment_by_site.c.contractor_name,
        )
        .outerjoin(villages_count, villages_count.c.site_id == Site.id)
        .outerjoin(wi_count, wi_count.c.site_id == Site.id)
        .outerjoin(assignment_by_site, assignment_by_site.c.site_id == Site.id)
        .where(Site.deleted_at.is_(None))
    )

    # --- Per-role scoping: the fix for the biggest documented gap ---
    if current_user.role == "field_subcontractor":
        assigned_site_ids = select(WorkItem.site_id).join(
            ContractorAssignment, ContractorAssignment.work_item_id == WorkItem.id
        ).where(
            ContractorAssignment.contractor_id == current_user.id,
            ContractorAssignment.ended_at.is_(None),
        )
        q = q.where(Site.id.in_(assigned_site_ids))
    elif current_user.role == "regional_manager":
        if not current_user.region_name:
            # Shouldn't happen (region is required at account creation), but
            # fail safe to "sees nothing" rather than "sees everything".
            q = q.where(False)
        else:
            q = q.where(Site.region_name == current_user.region_name)

    if search:
        like = f"%{search.strip()}%"
        q = q.where(
            (Site.site_id.ilike(like))
            | (Site.official_site_id.ilike(like))
            | (Site.temp_site_code.ilike(like))
        )
    if province:
        q = q.where(Site.province_name == province)
    if region:
        q = q.where(Site.region_name == region)
    if on_air is not None:
        if on_air:
            q = q.where(func.coalesce(wi_count.c.on_air_wc, 0) > 0)
        else:
            q = q.where(func.coalesce(wi_count.c.on_air_wc, 0) == 0)

    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()

    q = q.order_by(Site.site_id).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(q).all()

    items = [
        SiteListItem(
            id=r.Site.id,
            site_id=r.Site.site_id,
            official_site_id=r.Site.official_site_id,
            temp_site_code=r.Site.temp_site_code,
            province_name=r.Site.province_name,
            region_name=r.Site.region_name,
            village_count=r.village_count,
            work_item_count=r.work_item_count,
            on_air_work_item_count=r.on_air_work_item_count,
            is_on_air=r.on_air_work_item_count > 0,
            assigned_contractor=r.contractor_name,
        )
        for r in rows
    ]
    return SiteListResponse(total=total, page=page, page_size=page_size, items=items)


@app.get("/contractors", response_model=list[UserRead])
def list_contractors(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "project_manager")),
):
    """Lightweight contractor list for the site-assignment picker. Separate
    from /users (Admin-only full user management) so a PM can assign sites
    without needing access to create/edit/disable accounts."""
    return db.query(User).filter(User.role == "field_subcontractor", User.is_active.is_(True)).order_by(User.full_name).all()


@app.get("/sites/filter-options", response_model=SiteFilterOptions)
def site_filter_options(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Distinct values to populate the Sites table's filter dropdowns."""
    provinces = [r[0] for r in db.execute(
        select(Site.province_name).where(Site.province_name.isnot(None)).distinct().order_by(Site.province_name)
    ).all()]
    regions = [r[0] for r in db.execute(
        select(Site.region_name).where(Site.region_name.isnot(None)).distinct().order_by(Site.region_name)
    ).all()]
    site_types = [r[0] for r in db.execute(
        select(WorkItem.site_type).distinct().order_by(WorkItem.site_type)
    ).all()]
    return SiteFilterOptions(provinces=provinces, regions=regions, site_types=site_types)


@app.get("/sites/{site_id}/assignments", response_model=list[AssignmentRead])
def get_site_assignments(
    site_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Current ACTIVE assignment (if any) per work item under this site."""
    rows = db.execute(
        select(ContractorAssignment, WorkItem.site_type, User.full_name)
        .join(WorkItem, WorkItem.id == ContractorAssignment.work_item_id)
        .join(User, User.id == ContractorAssignment.contractor_id)
        .where(WorkItem.site_id == site_id, ContractorAssignment.ended_at.is_(None))
    ).all()
    return [
        AssignmentRead(
            work_item_id=a.work_item_id, site_type=stype, contractor_id=a.contractor_id,
            contractor_name=cname, assigned_at=a.assigned_at, remark=a.remark,
        )
        for a, stype, cname in rows
    ]


@app.post("/sites/{site_id}/assign", response_model=list[AssignmentRead])
def assign_site(
    site_id: uuid.UUID,
    payload: AssignSiteRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin", "project_manager")),
):
    """Assigns every work item under this site to one contractor — matches
    the real operational pattern (a site is handed to a contractor as a
    whole, by email). Ends any existing active assignment on each work item
    first, so a site is never double-assigned."""
    contractor = db.get(User, payload.contractor_id)
    if contractor is None or contractor.role != "field_subcontractor":
        raise HTTPException(status_code=400, detail="contractor_id must be an active Field Subcontractor account")
    if not contractor.is_active:
        raise HTTPException(status_code=400, detail="That contractor's account is disabled")

    work_items = db.query(WorkItem).filter(WorkItem.site_id == site_id).all()
    if not work_items:
        raise HTTPException(status_code=404, detail="This site has no work items to assign")

    now = datetime.now(timezone.utc)
    for wi in work_items:
        active = db.query(ContractorAssignment).filter(
            ContractorAssignment.work_item_id == wi.id, ContractorAssignment.ended_at.is_(None)
        ).first()
        if active is not None:
            if active.contractor_id == contractor.id:
                continue  # already assigned to this contractor, nothing to do
            active.ended_at = now
        db.add(ContractorAssignment(
            id=uuid.uuid4(), work_item_id=wi.id, contractor_id=contractor.id,
            assigned_by=admin.id, remark=payload.remark,
        ))
    db.commit()
    return get_site_assignments(site_id, db, admin)


@app.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Admin-only: list every account, newest first."""
    return db.query(User).order_by(User.created_at.desc()).all()


@app.post("/users", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Admin-only: create an account for any of the 6 roles."""
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="That email is already registered")
    first = payload.first_name.strip()
    last = (payload.last_name or "").strip()
    user = User(
        id=uuid.uuid4(),
        email=payload.email,
        first_name=first,
        last_name=last,
        full_name=(first + " " + last).strip(),
        phone=(payload.phone or "").strip() or None,
        role=payload.role,
        region_name=payload.region_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Admin-only: edit name, role, region, active status, or reset password."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Guard: an admin can't lock themselves out by deactivating their own account.
    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You can't deactivate your own account")

    # Name is edited as first/last; recompose full_name from whichever parts
    # changed, falling back to the current stored values for the untouched one.
    if payload.first_name is not None or payload.last_name is not None:
        if payload.first_name is not None:
            user.first_name = payload.first_name.strip()
        if payload.last_name is not None:
            user.last_name = payload.last_name.strip()
        user.full_name = ((user.first_name or "") + " " + (user.last_name or "")).strip()
    if payload.phone is not None:
        user.phone = payload.phone.strip() or None
    if payload.role is not None:
        user.role = payload.role
    if payload.region_name is not None:
        user.region_name = payload.region_name
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)

    db.commit()
    db.refresh(user)
    return user


@app.post("/import/cpm")
async def import_cpm(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Admin-only: upload a CPM Excel file to populate sites/villages/acceptance."""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx file")
    data = await file.read()
    try:
        result = import_cpm_bytes(data, db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read the file: {e}")
    return {"imported": result}


@app.post("/import/reset")
def reset_imported_data(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Admin-only: delete all imported Site/Village/Acceptance data so a fresh
    CPM import starts from a clean baseline. Does NOT touch user accounts.
    Order matters: children before parents to respect foreign keys."""
    from models import LetterVillageMapping, WorkItemTechnology, WorkItem, ContractorAssignment, HealthCheck, DriveTest, DriveTestReview, TimelineEvent

    deleted = {}
    # Acceptance + letter links
    deleted["letter_village_mapping"] = db.query(LetterVillageMapping).delete()
    deleted["village_acceptance"] = db.query(VillageAcceptance).delete()
    # Work-item side (if any seeded later)
    db.query(DriveTestReview).delete()
    db.query(DriveTest).delete()
    db.query(HealthCheck).delete()
    db.query(ContractorAssignment).delete()
    db.query(WorkItemTechnology).delete()
    db.query(WorkItem).delete()
    db.query(TimelineEvent).delete()
    # Core geography
    deleted["village"] = db.query(Village).delete()
    deleted["site"] = db.query(Site).delete()
    db.commit()
    return {"reset": deleted}


@app.get("/summary")
def summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Top-line counts for the dashboard.

    total_on_air: Index 1 (Site + Site Type unique combinations) that have
      reached an on-air status (permanent or temporary launch).
    total_villages: Index 2 (Site + Village ID) that have reached on-air,
      restricted to Target (هدف) villages only — CPM import already
      enforces the Target filter when creating Village rows.
    """
    total_sites = db.query(func.count(Site.id)).filter(Site.deleted_at.is_(None)).scalar()
    total_on_air = db.query(func.count(WorkItem.id)).filter(WorkItem.is_on_air.is_(True)).scalar()
    total_villages = db.query(func.count(Village.id)).filter(
        Village.deleted_at.is_(None), Village.is_on_air.is_(True)
    ).scalar()
    return {
        "sites": total_sites,
        "total_on_air": total_on_air,
        "total_villages": total_villages,
    }


@app.get("/action-center")
def action_center(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The current user's personal 'what needs me' inbox — live-derived and
    role-scoped. Every role can call it; each gets only its own actionable
    cards (Finance/Viewer get none)."""
    return build_action_center(db, current_user)


@app.get("/dashboard/acceptance")
def acceptance_dashboard(
    technology: str = "all",
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Acceptance (ICT & CRA) analytics: per-side summary partition, per-
    province sortable tables, site-level rollups, and exact current-Jalali-
    month approval progress. Any logged-in role may read it."""
    return build_acceptance_dashboard(db, technology)


@app.get("/dashboard/pm")
def pm_dashboard(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "project_manager")),
):
    """Project Manager action center: the seven gaps, KPIs, and month-to-date
    approval trends. Admin + PM only (PM is read-only across the project)."""
    return build_pm_dashboard(db)


@app.get("/dashboard/delivery")
def project_delivery_dashboard(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "project_manager")),
):
    """Project Delivery tab: on-air/DT/remained KPIs with %/trend, ongoing
    and problematic breakdowns (per subcontractor / per category, each with
    a per-province drill-down), and yearly/monthly/per-subcontractor DT
    delivery charts. Admin + PM only."""
    return build_project_delivery_dashboard(db)


@app.get("/dashboard/coordinator")
def coordinator_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("dt_coordinator")),
):
    """DT Coordinator's own action center — scoped to the provinces where
    they're the assigned PSO coordinator (Province.pso_coordinator_id)."""
    return build_coordinator_dashboard(db, user)


@app.get("/dashboard/contractor")
def contractor_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("field_subcontractor")),
):
    """Field Subcontractor's own work view — scoped to sites where they
    hold an active ContractorAssignment."""
    return build_contractor_dashboard(db, user)


@app.get("/dashboard/regional")
def regional_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("regional_manager")),
):
    """Regional Manager's own view — scoped to the provinces where they're
    the assigned Regional Manager (Province.regional_manager_id)."""
    return build_regional_dashboard(db, user)


@app.get("/provinces", response_model=list[ProvinceRead])
def list_provinces(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Admin-only: every province with its current CRA region, Regional
    Manager, and PSO Coordinator — backs the Province Assignments table in
    User Management."""
    rm = aliased(User)
    coord = aliased(User)
    rows = db.execute(
        select(Province, rm.full_name, coord.full_name)
        .outerjoin(rm, rm.id == Province.regional_manager_id)
        .outerjoin(coord, coord.id == Province.pso_coordinator_id)
        .order_by(Province.name)
    ).all()
    return [
        ProvinceRead(
            id=p.id, name=p.name, cra_region=p.cra_region,
            regional_manager_id=p.regional_manager_id, regional_manager_name=rm_name,
            pso_coordinator_id=p.pso_coordinator_id, pso_coordinator_name=coord_name,
        )
        for p, rm_name, coord_name in rows
    ]


@app.patch("/provinces/{province_id}", response_model=ProvinceRead)
def update_province(
    province_id: uuid.UUID,
    payload: ProvinceUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Admin-only: reassign a province's Regional Manager and/or PSO
    Coordinator. Full-replace — both fields are always set from what the
    client sent (see ProvinceUpdate)."""
    prov = db.get(Province, province_id)
    if prov is None:
        raise HTTPException(status_code=404, detail="Province not found")

    rm_name = coord_name = None
    if payload.regional_manager_id is not None:
        rm = db.get(User, payload.regional_manager_id)
        if rm is None or rm.role != "regional_manager":
            raise HTTPException(status_code=400, detail="regional_manager_id must be a Regional Manager account")
        rm_name = rm.full_name
    if payload.pso_coordinator_id is not None:
        coord = db.get(User, payload.pso_coordinator_id)
        if coord is None or coord.role != "dt_coordinator":
            raise HTTPException(status_code=400, detail="pso_coordinator_id must be a DT Coordinator account")
        coord_name = coord.full_name

    prov.regional_manager_id = payload.regional_manager_id
    prov.pso_coordinator_id = payload.pso_coordinator_id
    db.commit()
    return ProvinceRead(
        id=prov.id, name=prov.name, cra_region=prov.cra_region,
        regional_manager_id=prov.regional_manager_id, regional_manager_name=rm_name,
        pso_coordinator_id=prov.pso_coordinator_id, pso_coordinator_name=coord_name,
    )


# ===========================================================================
# Acceptance (ICT / CRA) — in-app write surface. ICT and CRA are two
# independent processes (kept separate everywhere, per the spec). Any write
# stamps that side's approved_by, which locks the CPM importer out of that
# side from then on (Single Source Ownership).
# ===========================================================================

def _acceptance_visible_site_ids(db: Session, user: User):
    """Scalar subquery of site ids this user may SEE acceptance for, or None
    for 'all sites'. Mirrors the /sites and dashboard scoping."""
    if user.role in ("admin", "project_manager", "viewer", "finance"):
        return None
    if user.role == "dt_coordinator":
        return select(Site.id).where(
            Site.province_id.in_(select(Province.id).where(Province.pso_coordinator_id == user.id))
        )
    if user.role == "regional_manager":
        return select(Site.id).where(
            Site.province_id.in_(select(Province.id).where(Province.regional_manager_id == user.id))
        )
    if user.role == "field_subcontractor":
        return (
            select(WorkItem.site_id)
            .join(ContractorAssignment, ContractorAssignment.work_item_id == WorkItem.id)
            .where(ContractorAssignment.contractor_id == user.id, ContractorAssignment.ended_at.is_(None))
        )
    return select(Site.id).where(False)  # fail closed


def _coordinator_owns_site(db: Session, user: User, site_id: uuid.UUID) -> bool:
    prov_id = db.execute(select(Site.province_id).where(Site.id == site_id)).scalar()
    if prov_id is None:
        return False
    owner = db.execute(select(Province.pso_coordinator_id).where(Province.id == prov_id)).scalar()
    return owner == user.id


@app.get("/acceptance", response_model=AcceptanceListResponse)
def list_acceptance(
    page: int = 1,
    page_size: int = 50,
    search: str = "",
    province: str = "",
    ict_final: Optional[bool] = None,
    cra_final: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Village-grain acceptance list, role-scoped (coordinator -> their
    provinces, regional manager -> their region, contractor -> assigned
    sites, everyone else -> all)."""
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)

    q = (
        select(VillageAcceptance, Site.site_id, Site.province_id, Site.province_name, Village.village_name)
        .join(Site, Site.id == VillageAcceptance.site_id)
        .outerjoin(
            Village,
            (Village.site_id == VillageAcceptance.site_id)
            & (Village.village_id == VillageAcceptance.village_id),
        )
    )
    visible = _acceptance_visible_site_ids(db, current_user)
    if visible is not None:
        q = q.where(VillageAcceptance.site_id.in_(visible))
    if province:
        q = q.where(Site.province_name == province)
    if search:
        like = f"%{search.strip()}%"
        q = q.where((VillageAcceptance.village_id.ilike(like)) | (Village.village_name.ilike(like)))
    if ict_final is not None:
        q = q.where(VillageAcceptance.ict_final.is_(ict_final))
    if cra_final is not None:
        q = q.where(VillageAcceptance.cra_final.is_(cra_final))

    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    q = q.order_by(Site.site_id, VillageAcceptance.village_id).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(q).all()

    items = [
        AcceptanceListItem(
            id=va.id, site_id=va.site_id, site_business_id=sid,
            province_id=pid, province_name=pname,
            village_id=va.village_id, village_name=vname,
            ict_2g=va.ict_2g, ict_3g=va.ict_3g, ict_4g=va.ict_4g, ict_final=va.ict_final,
            cra_2g=va.cra_2g, cra_3g=va.cra_3g, cra_4g=va.cra_4g, cra_final=va.cra_final,
            depreciation_status=va.depreciation_status,
        )
        for va, sid, pid, pname, vname in rows
    ]
    return AcceptanceListResponse(total=total, page=page, page_size=page_size, items=items)


@app.get("/acceptance/{acceptance_id}", response_model=VillageAcceptanceRead)
def get_acceptance(
    acceptance_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acc = db.get(VillageAcceptance, acceptance_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="Acceptance record not found")
    visible = _acceptance_visible_site_ids(db, current_user)
    if visible is not None:
        allowed = db.execute(select(Site.id).where(Site.id == acc.site_id, Site.id.in_(visible))).first()
        if allowed is None:
            raise HTTPException(status_code=403, detail="This acceptance record is outside your scope")
    return acc


def _apply_side_update(
    acceptance_id: uuid.UUID, side: str, payload: AcceptanceSideUpdate,
    db: Session, user: User,
) -> VillageAcceptance:
    acc = db.get(VillageAcceptance, acceptance_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="Acceptance record not found")
    if user.role == "dt_coordinator" and not _coordinator_owns_site(db, user, acc.site_id):
        raise HTTPException(status_code=403, detail="This village is outside the provinces you coordinate")

    statuses = {}
    for gen, val in (("2g", payload.g2), ("3g", payload.g3), ("4g", payload.g4)):
        if val is not None:
            statuses[gen] = val.value
    try:
        update_acceptance_side(
            db, acc, side,
            statuses=statuses, comment=payload.comment,
            letter_number=payload.letter_number, letter_date=payload.letter_date,
            actor_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(acc)
    return acc


@app.put("/acceptance/{acceptance_id}/ict", response_model=VillageAcceptanceRead)
def update_acceptance_ict(
    acceptance_id: uuid.UUID,
    payload: AcceptanceSideUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "dt_coordinator")),
):
    """Update a village's ICT side. Coordinators are scoped to their own
    provinces; Admin is unrestricted. Stamps ict_approved_by (Single Source
    Ownership) and recomputes ict_final + depreciation."""
    return _apply_side_update(acceptance_id, "ict", payload, db, user)


@app.put("/acceptance/{acceptance_id}/cra", response_model=VillageAcceptanceRead)
def update_acceptance_cra(
    acceptance_id: uuid.UUID,
    payload: AcceptanceSideUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "dt_coordinator")),
):
    """Update a village's CRA side (independent of ICT). Same scoping and
    Single-Source-Ownership stamping as the ICT side."""
    return _apply_side_update(acceptance_id, "cra", payload, db, user)


# ===========================================================================
# Letters — one official letter clears one to thousands of villages at once
# (Rule 5 fan-out). ICT vs CRA is decided by the letter's organization.
# ===========================================================================

@app.post("/letters", response_model=LetterRead, status_code=201)
def create_letter(
    payload: LetterCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "dt_coordinator")),
):
    """Record one letter and fan it out: approve every requested technology
    on the letter's side across every linked village, in one transaction.
    Coordinators may only attach villages inside the provinces they
    coordinate."""
    if db.query(Letter).filter(Letter.letter_number == payload.letter_number).first():
        raise HTTPException(status_code=409, detail="A letter with that number already exists")

    accs = db.query(VillageAcceptance).filter(
        VillageAcceptance.id.in_(payload.village_acceptance_ids)
    ).all()
    found = {a.id for a in accs}
    missing = [str(v) for v in payload.village_acceptance_ids if v not in found]
    if missing:
        raise HTTPException(status_code=404, detail="Unknown village acceptance id(s): " + ", ".join(missing))

    if user.role == "dt_coordinator":
        for acc in accs:
            if not _coordinator_owns_site(db, user, acc.site_id):
                raise HTTPException(
                    status_code=403,
                    detail="One or more villages are outside the provinces you coordinate",
                )

    try:
        letter = register_letter(
            db,
            letter_number=payload.letter_number, letter_date=payload.letter_date,
            organization=payload.organization.value,
            province_or_region_id=payload.province_or_region_id,
            comment=payload.comment, pdf_attachment_url=payload.pdf_attachment_url,
            village_acceptance_ids=payload.village_acceptance_ids, actor_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(letter)
    return LetterRead(
        id=letter.id, letter_number=letter.letter_number, letter_date=letter.letter_date,
        organization=letter.organization, province_or_region_id=letter.province_or_region_id,
        comment=letter.comment, pdf_attachment_url=letter.pdf_attachment_url,
        created_at=letter.created_at, village_count=len(payload.village_acceptance_ids),
    )


@app.get("/letters", response_model=list[LetterRead])
def list_letters(
    search: str = "",
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """All letters, newest first, with a village count each. Optional search
    by letter number."""
    counts = dict(
        db.execute(
            select(LetterVillageMapping.letter_id, func.count(LetterVillageMapping.id))
            .group_by(LetterVillageMapping.letter_id)
        ).all()
    )
    q = select(Letter).order_by(Letter.created_at.desc())
    if search:
        q = q.where(Letter.letter_number.ilike(f"%{search.strip()}%"))
    letters = db.execute(q).scalars().all()
    return [
        LetterRead(
            id=l.id, letter_number=l.letter_number, letter_date=l.letter_date,
            organization=l.organization, province_or_region_id=l.province_or_region_id,
            comment=l.comment, pdf_attachment_url=l.pdf_attachment_url,
            created_at=l.created_at, village_count=counts.get(l.id, 0),
        )
        for l in letters
    ]


# ===========================================================================
# Drive Test — two-stage approval:
#   Subcontractor submits -> Coordinator validates -> PM approves/rejects.
# Separation of duties is enforced in drive_test_service (PM can only act on
# a coordinator-validated DT). A rejected DT is terminal; the subcontractor
# submits a fresh revision to retry.
# ===========================================================================

def _contractor_holds_assignment(db: Session, user_id: uuid.UUID, work_item_id: uuid.UUID) -> bool:
    return db.execute(
        select(ContractorAssignment.id).where(
            ContractorAssignment.work_item_id == work_item_id,
            ContractorAssignment.contractor_id == user_id,
            ContractorAssignment.ended_at.is_(None),
        )
    ).first() is not None


@app.get("/work-items/{work_item_id}/drive-tests", response_model=list[DriveTestRead])
def list_drive_tests(
    work_item_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Every drive test for a work item, newest revision first (its history)."""
    return db.execute(
        select(DriveTest).where(DriveTest.work_item_id == work_item_id)
        .order_by(DriveTest.revision_no.desc())
    ).scalars().all()


@app.get("/drive-tests/{drive_test_id}/reviews", response_model=list[DriveTestReviewItem])
def list_drive_test_reviews(
    drive_test_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """The per-stage decision ledger (coordinator then PM) for one drive test."""
    return db.execute(
        select(DriveTestReview).where(DriveTestReview.drive_test_id == drive_test_id)
        .order_by(DriveTestReview.review_date)
    ).scalars().all()


@app.post("/drive-tests", response_model=DriveTestRead, status_code=201)
def submit_dt(
    payload: DriveTestSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "field_subcontractor")),
):
    """Subcontractor submits a drive test for a work item they're actively
    assigned to (Admin may submit for any). Fails if a drive test is already
    in progress for that work item."""
    wi = db.get(WorkItem, payload.work_item_id)
    if wi is None:
        raise HTTPException(status_code=404, detail="Work item not found")
    if user.role == "field_subcontractor" and not _contractor_holds_assignment(db, user.id, wi.id):
        raise HTTPException(status_code=403, detail="You are not assigned to this work item")
    try:
        dt = submit_drive_test(
            db, wi, contractor_id=user.id,
            delivery_date=payload.delivery_date, report_url=payload.report_url,
        )
    except WorkflowError as e:
        raise HTTPException(status_code=409, detail=str(e))
    db.commit()
    db.refresh(dt)
    return dt


def _load_dt_for_stage(db: Session, drive_test_id: uuid.UUID) -> tuple[DriveTest, WorkItem]:
    dt = db.get(DriveTest, drive_test_id)
    if dt is None:
        raise HTTPException(status_code=404, detail="Drive test not found")
    wi = db.get(WorkItem, dt.work_item_id)
    return dt, wi


@app.put("/drive-tests/{drive_test_id}/validate", response_model=DriveTestRead)
def validate_dt(
    drive_test_id: uuid.UUID,
    payload: DriveTestValidate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "dt_coordinator")),
):
    """Coordinator stage-1 review. Coordinators are scoped to their own
    provinces. Approve queues it for the PM; reject sends it back."""
    dt, wi = _load_dt_for_stage(db, drive_test_id)
    if user.role == "dt_coordinator" and not _coordinator_owns_site(db, user, wi.site_id):
        raise HTTPException(status_code=403, detail="This work item is outside the provinces you coordinate")
    try:
        coordinator_validate(db, dt, approve=payload.approve, comment=payload.comment, reviewer_id=user.id)
    except WorkflowError as e:
        raise HTTPException(status_code=409, detail=str(e))
    db.commit()
    db.refresh(dt)
    return dt


@app.put("/drive-tests/{drive_test_id}/approve", response_model=DriveTestRead)
def approve_dt(
    drive_test_id: uuid.UUID,
    payload: DriveTestApprove,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "project_manager")),
):
    """PM stage-2 approval. Only valid on a coordinator-validated
    (UNDER_REVIEW) drive test. Marks the work item's DT status DONE."""
    dt, wi = _load_dt_for_stage(db, drive_test_id)
    try:
        pm_decide(db, dt, wi, approve=True, comment=payload.comment, reviewer_id=user.id)
    except WorkflowError as e:
        raise HTTPException(status_code=409, detail=str(e))
    db.commit()
    db.refresh(dt)
    return dt


@app.put("/drive-tests/{drive_test_id}/reject", response_model=DriveTestRead)
def reject_dt(
    drive_test_id: uuid.UUID,
    payload: DriveTestReject,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "project_manager")),
):
    """PM stage-2 rejection (reason required). Sends the drive test back so
    the subcontractor can submit a corrected revision."""
    dt, wi = _load_dt_for_stage(db, drive_test_id)
    try:
        pm_decide(db, dt, wi, approve=False, comment=payload.comment, reviewer_id=user.id)
    except WorkflowError as e:
        raise HTTPException(status_code=409, detail=str(e))
    db.commit()
    db.refresh(dt)
    return dt


# ===========================================================================
# CPM Change Review Center — a CPM re-import that would contradict a value a
# human already approved does NOT silently overwrite (or silently discard).
# It stages the conflict here for the PM to Accept (apply CPM's value),
# Ignore (keep the app value), or Flag (acknowledge, decide later).
# ===========================================================================

_ACCEPTANCE_FIELDS = {"ict_2g", "ict_3g", "ict_4g", "cra_2g", "cra_3g", "cra_4g"}


@app.get("/pending-changes", response_model=list[PendingChangeRead])
def list_pending_changes(
    decision: str = "pending",
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin", "project_manager")),
):
    """Staged CPM conflicts for PM review (default: unresolved 'pending').
    Enriched with village/site context so each row is actionable on its own."""
    q = select(PendingChange).order_by(PendingChange.created_at.desc())
    if decision:
        q = q.where(PendingChange.decision == decision)
    changes = db.execute(q).scalars().all()

    # Enrich village_acceptance conflicts with site/village context in one pass.
    acc_ids = [c.entity_id for c in changes if c.entity_type == "village_acceptance"]
    ctx: dict[uuid.UUID, tuple] = {}
    if acc_ids:
        rows = db.execute(
            select(VillageAcceptance.id, Site.site_id, Site.province_name, VillageAcceptance.village_id)
            .join(Site, Site.id == VillageAcceptance.site_id)
            .where(VillageAcceptance.id.in_(acc_ids))
        ).all()
        ctx = {r[0]: (r[1], r[2], r[3]) for r in rows}

    out = []
    for c in changes:
        sid, pname, vid = ctx.get(c.entity_id, (None, None, None))
        out.append(PendingChangeRead(
            id=c.id, entity_type=c.entity_type, entity_id=c.entity_id, field_name=c.field_name,
            old_value=c.old_value, new_value=c.new_value, severity=c.severity,
            decision=c.decision, created_at=c.created_at,
            site_business_id=sid, province_name=pname, village_id=vid,
        ))
    return out


@app.put("/pending-changes/{change_id}", response_model=PendingChangeRead)
def resolve_pending_change(
    change_id: uuid.UUID,
    payload: PendingChangeResolve,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "project_manager")),
):
    """Resolve a staged conflict.
      * accepted -> apply CPM's value to the live acceptance row (override the
        app value) and recompute Final + depreciation.
      * ignored  -> keep the app value; the conflict is dismissed.
      * flagged  -> acknowledged, kept visible for follow-up.
    """
    pc = db.get(PendingChange, change_id)
    if pc is None:
        raise HTTPException(status_code=404, detail="Pending change not found")
    if pc.decision != "pending":
        raise HTTPException(status_code=409, detail=f"This change was already resolved ('{pc.decision}')")

    if payload.decision == "accepted" and pc.entity_type == "village_acceptance" and pc.field_name in _ACCEPTANCE_FIELDS:
        acc = db.get(VillageAcceptance, pc.entity_id)
        if acc is not None:
            setattr(acc, pc.field_name, pc.new_value)
            acc.recompute_finals()

    pc.decision = payload.decision
    pc.decided_by = user.id
    pc.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pc)

    sid = pname = vid = None
    if pc.entity_type == "village_acceptance":
        row = db.execute(
            select(Site.site_id, Site.province_name, VillageAcceptance.village_id)
            .join(Site, Site.id == VillageAcceptance.site_id)
            .where(VillageAcceptance.id == pc.entity_id)
        ).first()
        if row:
            sid, pname, vid = row
    return PendingChangeRead(
        id=pc.id, entity_type=pc.entity_type, entity_id=pc.entity_id, field_name=pc.field_name,
        old_value=pc.old_value, new_value=pc.new_value, severity=pc.severity,
        decision=pc.decision, created_at=pc.created_at,
        site_business_id=sid, province_name=pname, village_id=vid,
    )
