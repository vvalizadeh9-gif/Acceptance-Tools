"""
CPM Excel import — fast, correct, and honestly reported.

Performance note: earlier versions preloaded existing rows as FULL ORM
objects (Site(), Village()...), which meant SQLAlchemy hydrating tens of
thousands of Python objects just to read one ID off each — the actual
source of the ~30s import time at real data volume. This version selects
only the specific columns needed as lightweight tuples, which is why it
runs in a couple of seconds even at ~30k existing rows.

Business logic:
  * Sheet name is auto-detected (CPM, Sheet1, ...).
  * Filter to Target rows only: column "هدف/ اقماری" (AD) exactly == "هدف".
  * Site identity: official Irancell ID when present and not the literal
    "No Site ID" placeholder; otherwise the temporary site code.
  * "---" in the village-code column is a missing-code placeholder (same
    pattern as "No Site ID") and is never treated as a real village.
  * On-air = CPM "last stage" status is either permanent or temporary
    launch. WorkItem (Site+SiteType = Index 1) and Village (Site+VillageID
    = Index 2) both track an is_on_air flag, OR'd across all rows that
    reference them — if any row says on-air, it counts as on-air.
  * Idempotent: re-importing adds only new records, and upgrades any
    existing WorkItem/Village from not-on-air to on-air if newer data
    shows it went live. Never downgrades on-air back to not-on-air.
"""

import io
import uuid
from datetime import date

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from enums import AcceptanceStatus
from models import Site, Village, VillageAcceptance, WorkItem

# ---- Exact column names from the CPM file ----
COL_SITE = "کدسایت موقت"                 # temporary site code (fallback identity)
COL_OFFICIAL_SITE = "کد سایت ایرانسل"     # official Irancell site ID (preferred identity)
COL_PROVINCE = "استان"
COL_REGION = "منطقه"
COL_VILLAGE_CODE = "کد آبادی"
COL_VILLAGE_NAME = "آبادی"
COL_SITE_TYPE = "نوع سایت"
COL_TECH = "تکنولوژی درخواستی"
COL_TARGET = "هدف/ اقماری"                # column AD — target/satellite classification
COL_STATUS = "آخرین مرحله انجام شده"       # last stage completed (site status)

HADAF_VALUE = "هدف"                       # exact match only
NO_OFFICIAL_ID_PLACEHOLDER = "No Site ID"
NO_VILLAGE_CODE_PLACEHOLDER = "---"
ON_AIR_STATUSES = {"راه_اندازی_دائم", "راه_اندازی_موقت"}  # permanent / temporary launch

TECH_SPLIT = {
    "2G": ["GSM"], "3G": ["UMTS"], "4G": ["LTE"],
    "2G3G4G": ["GSM", "UMTS", "LTE"],
    "2G4G": ["GSM", "LTE"], "2G3G": ["GSM", "UMTS"],
    "3G4G": ["UMTS", "LTE"], "3G/4G": ["UMTS", "LTE"],
    "MW": [],  # microwave transmission — not a cellular acceptance technology
}

# Maps a cellular technology to the per-generation acceptance column suffix.
TECH_TO_GEN = {"GSM": "2g", "UMTS": "3g", "LTE": "4g"}


def _region_uuid(label: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"region::{label}")


def _province_uuid(label: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"province::{label}")


def _clean(v) -> str:
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def _resolve_site_key(official_raw: str, temp_raw: str) -> str:
    if official_raw and official_raw != NO_OFFICIAL_ID_PLACEHOLDER:
        return official_raw
    return temp_raw


def import_cpm_bytes(data: bytes, db: Session) -> dict:
    # --- Locate the right sheet (tolerant of name) ---
    xls = pd.ExcelFile(io.BytesIO(data))
    chosen = None
    for name in xls.sheet_names:
        try:
            probe = pd.read_excel(xls, sheet_name=name, header=2, nrows=1)
            if COL_SITE in probe.columns:
                chosen = name
                break
        except Exception:
            continue
    if chosen is None:
        raise ValueError(
            f"Could not find the CPM data. Expected a sheet with column '{COL_SITE}' on row 3."
        )

    df = pd.read_excel(xls, sheet_name=chosen, header=2)

    required = [COL_SITE, COL_VILLAGE_CODE, COL_TARGET, COL_TECH, COL_SITE_TYPE, COL_STATUS]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("The file is missing required column(s): " + ", ".join(missing))

    df = df[df[COL_SITE].notna()]
    total_rows = len(df)

    df = df[df[COL_TARGET].astype(str).str.strip() == HADAF_VALUE]
    target_rows = len(df)
    excluded = total_rows - target_rows

    # --- Lightweight preloads: specific columns only, not full ORM objects ---
    site_id_by_key: dict[str, uuid.UUID] = {
        row.site_id: row.id for row in db.execute(select(Site.id, Site.site_id))
    }
    village_pk_by_key: dict[tuple, tuple] = {
        (row.site_id, row.village_id): (row.id, row.is_on_air)
        for row in db.execute(select(Village.id, Village.site_id, Village.village_id, Village.is_on_air))
    }
    workitem_pk_by_key: dict[tuple, tuple] = {
        (row.site_id, row.site_type): (row.id, row.is_on_air)
        for row in db.execute(select(WorkItem.id, WorkItem.site_id, WorkItem.site_type, WorkItem.is_on_air))
    }
    # Acceptance is now one row per (site, village). Preload the per-tech
    # request flags so re-import can mark newly-requested technologies without
    # hydrating full ORM objects.
    existing_acceptance: dict[tuple, dict] = {
        (row.site_id, row.village_id): {"id": row.id, "2g": row.ict_2g, "3g": row.ict_3g, "4g": row.ict_4g}
        for row in db.execute(select(
            VillageAcceptance.id, VillageAcceptance.site_id, VillageAcceptance.village_id,
            VillageAcceptance.ict_2g, VillageAcceptance.ict_3g, VillageAcceptance.ict_4g,
        ))
    }

    new_sites: dict[str, Site] = {}
    new_villages: dict[tuple, Village] = {}
    new_workitems: dict[tuple, WorkItem] = {}
    new_acceptance: dict[tuple, VillageAcceptance] = {}
    # Existing acceptance rows that gained a newly-requested technology:
    # {tech_attr: {village_acceptance_id, ...}} -> flipped NULL -> not_submitted.
    acceptance_tech_to_flip: dict[str, set] = {"2g": set(), "3g": set(), "4g": set()}
    villages_to_flip_on: set = set()   # existing Village.id needing is_on_air -> True
    workitems_to_flip_on: set = set()  # existing WorkItem.id needing is_on_air -> True

    counts = {"sites": 0, "villages": 0, "work_items": 0, "acceptance": 0,
              "target_rows": target_rows, "excluded_non_target": excluded}

    for r in df.to_dict("records"):
        temp_code = _clean(r.get(COL_SITE))
        official_code = _clean(r.get(COL_OFFICIAL_SITE))
        site_code = _resolve_site_key(official_code, temp_code)
        if not site_code:
            continue

        status = _clean(r.get(COL_STATUS))
        row_is_on_air = status in ON_AIR_STATUSES

        # --- Site (business-key resolved) ---
        site_uuid = site_id_by_key.get(site_code)
        if site_uuid is None:
            existing_new = new_sites.get(site_code)
            if existing_new is None:
                province_name = _clean(r.get(COL_PROVINCE)) or "Unknown"
                region_name = _clean(r.get(COL_REGION)) or "Unknown"
                new_site = Site(
                    id=uuid.uuid4(),
                    site_id=site_code,
                    official_site_id=official_code if official_code and official_code != NO_OFFICIAL_ID_PLACEHOLDER else None,
                    temp_site_code=temp_code or None,
                    province_id=_province_uuid(province_name),
                    region_id=_region_uuid(region_name),
                    province_name=province_name,
                    region_name=region_name,
                )
                new_sites[site_code] = new_site
                site_id_by_key[site_code] = new_site.id  # so later rows in this batch find it
                counts["sites"] += 1
                site_uuid = new_site.id
            else:
                site_uuid = existing_new.id

        # --- Work Item = Index 1 (Site + Site Type) ---
        stype = _clean(r.get(COL_SITE_TYPE))
        if stype:
            wkey = (site_uuid, stype)
            wi_existing = workitem_pk_by_key.get(wkey)
            wi_new = new_workitems.get(wkey)
            if wi_existing is not None:
                wi_id, wi_on_air = wi_existing
                if row_is_on_air and not wi_on_air:
                    workitems_to_flip_on.add(wi_id)
                    workitem_pk_by_key[wkey] = (wi_id, True)
            elif wi_new is not None:
                if row_is_on_air and not wi_new.is_on_air:
                    wi_new.is_on_air = True
            else:
                new_wi = WorkItem(
                    id=uuid.uuid4(), site_id=site_uuid, site_type=stype,
                    assignment_date=None, cpm_raw_status=status or None,
                    is_on_air=row_is_on_air,
                )
                new_workitems[wkey] = new_wi
                counts["work_items"] += 1

        # --- Village = Index 2 (Site + Village ID) ---
        vcode = _clean(r.get(COL_VILLAGE_CODE))
        if vcode and vcode != NO_VILLAGE_CODE_PLACEHOLDER:
            vkey = (site_uuid, vcode)
            v_existing = village_pk_by_key.get(vkey)
            v_new = new_villages.get(vkey)
            if v_existing is not None:
                v_id, v_on_air = v_existing
                if row_is_on_air and not v_on_air:
                    villages_to_flip_on.add(v_id)
                    village_pk_by_key[vkey] = (v_id, True)
            elif v_new is not None:
                if row_is_on_air and not v_new.is_on_air:
                    v_new.is_on_air = True
            else:
                new_v = Village(
                    id=uuid.uuid4(), site_id=site_uuid, village_id=vcode,
                    village_name=_clean(r.get(COL_VILLAGE_NAME))[:255] or "-",
                    is_on_air=row_is_on_air,
                )
                new_villages[vkey] = new_v
                counts["villages"] += 1

            # --- Acceptance: one row per (site, village); mark requested
            # technologies as not_submitted (NULL means "not requested").
            # The 6 new CPM acceptance columns (ICT/CRA 2G/3G/4G, letters,
            # depreciation) are parsed once the updated CPM file arrives; for
            # now we only record which technologies were requested. ---
            tech_label = _clean(r.get(COL_TECH))
            requested_gens = {TECH_TO_GEN[t] for t in TECH_SPLIT.get(tech_label, []) if t in TECH_TO_GEN}
            if requested_gens:
                akey = (site_uuid, vcode)
                existing = existing_acceptance.get(akey)
                if existing is not None:
                    # Flip any newly-requested generation from NULL -> not_submitted.
                    for gen in requested_gens:
                        if existing[gen] is None:
                            acceptance_tech_to_flip[gen].add(existing["id"])
                            existing[gen] = AcceptanceStatus.NOT_SUBMITTED
                else:
                    va = new_acceptance.get(akey)
                    if va is None:
                        va = VillageAcceptance(id=uuid.uuid4(), site_id=site_uuid, village_id=vcode)
                        new_acceptance[akey] = va
                        counts["acceptance"] += 1
                    for gen in requested_gens:
                        setattr(va, f"ict_{gen}", AcceptanceStatus.NOT_SUBMITTED)
                        setattr(va, f"cra_{gen}", AcceptanceStatus.NOT_SUBMITTED)

    # New acceptance rows: refresh their cached Final flags (all False here
    # since nothing is approved yet, but keeps the invariant honest).
    for va in new_acceptance.values():
        va.recompute_finals()

    # --- Bulk writes: a handful of statements, not thousands ---
    db.add_all(new_sites.values())
    db.add_all(new_workitems.values())
    db.add_all(new_villages.values())
    db.add_all(new_acceptance.values())
    if workitems_to_flip_on:
        db.execute(update(WorkItem).where(WorkItem.id.in_(workitems_to_flip_on)).values(is_on_air=True))
    if villages_to_flip_on:
        db.execute(update(Village).where(Village.id.in_(villages_to_flip_on)).values(is_on_air=True))
    for gen, ids in acceptance_tech_to_flip.items():
        if ids:
            db.execute(update(VillageAcceptance).where(VillageAcceptance.id.in_(ids)).values(
                **{f"ict_{gen}": AcceptanceStatus.NOT_SUBMITTED, f"cra_{gen}": AcceptanceStatus.NOT_SUBMITTED}
            ))
    db.commit()

    return counts
