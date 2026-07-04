"""
BRIEF: this is the actual "waiter." It exposes a fixed menu of URLs
(routes) that the frontend — or a browser directly, for testing — can
call. Every route either needs no login (/health) or requires a valid
badge (JWT) and, for some, a specific role.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from auth import create_access_token, hash_password, verify_password
from dashboards import build_pm_dashboard, build_project_delivery_dashboard
from database import get_db
from deps import get_current_user, require_role
from import_cpm import import_cpm_bytes
from models import ContractorAssignment, Site, User, Village, VillageAcceptance, WorkItem
from schemas import (
    AssignmentRead, AssignSiteRequest, SiteFilterOptions, SiteListItem, SiteListResponse,
    SiteRead, UserCreate, UserRead, UserUpdate,
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


@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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
    user = User(
        id=uuid.uuid4(),
        email=payload.email,
        full_name=payload.full_name,
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

    if payload.full_name is not None:
        user.full_name = payload.full_name
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
