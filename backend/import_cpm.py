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

ICT/CRA acceptance — golden rule, confirmed against the real CPM export:
  * Per-technology columns (2G-ICT / 3G-ICT / 4G-ICT and the CRA
    equivalents) hold the tech's own label ("2G"/"3G"/"4G") when approved,
    "Reject" when rejected, or blank otherwise. The "ICT Status"/"CRA
    Status" columns are ALWAYS blank in the real file — dead columns, never
    read. Final (ict_final/cra_final) is computed and stored by us
    (VillageAcceptance.recompute_finals): true only when EVERY requested
    technology (from "تکنولوژی درخواستی", not every possible one) is
    Approved on that side. A rejected or blank non-requested technology
    never blocks Final — "we are responsible only for requested technology".
  * Single Source Ownership after first app touch: once a human approves
    ICT or CRA for a village through the app (ict_approved_by /
    cra_approved_by gets set), CPM re-import must never overwrite that
    side's status/comment/letter fields again. Until then, CPM is the
    source of truth and re-imports (e.g. a corrected file) may refresh it.
  * Depreciation is imported from the legacy "وضعیت استهلاک " column (the
    new "Depreciation Status" column is app-managed going forward and
    starts blank). Depreciation only ever advances
    (Remain -> Waiting -> Depreciated), matching recompute_finals'
    golden-item rule that auto-advances to Waiting once both sides are
    Final, and never regresses an already-Depreciated record.
"""

import io
import uuid
from datetime import date

import pandas as pd
from sqlalchemy import bindparam, select, update
from sqlalchemy.orm import Session

from enums import AcceptanceStatus, DepreciationStatus, DTProblematicCategory, DTProgressStatus
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

# Drive test (site grain)
COL_DT_STATUS = "DT Status"
COL_DT_CATEGORY = "DT Problematic Category"
COL_DT_SC = "DT SC"
COL_DT_DATE = "DT Date"

# ICT / CRA acceptance (village grain)
COL_ICT_2G, COL_ICT_3G, COL_ICT_4G = "2G-ICT", "3G-ICT", "4G-ICT"
COL_ICT_COMMENT, COL_ICT_LETTER_DATE, COL_ICT_LETTER_NUMBER = "Comment-ICT", "Letter Date-ICT", "Letter Number-ICT"
COL_CRA_2G, COL_CRA_3G, COL_CRA_4G = "2G-CRA", "3G-CRA", "4G-CRA"
COL_CRA_COMMENT, COL_CRA_LETTER_DATE, COL_CRA_LETTER_NUMBER = "Comment-CRA", "Letter Date-CRA", "Letter Number-CRA"

# Legacy depreciation column (historical baseline; the new "Depreciation
# Status" column is app-managed going forward and starts blank).
COL_DEPRECIATION_LEGACY = "وضعیت استهلاک "  # NOTE: trailing space is exact in the file

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

# Maps a cellular technology to the per-generation acceptance column suffix,
# and back to the exact label used in the ICT/CRA columns.
TECH_TO_GEN = {"GSM": "2g", "UMTS": "3g", "LTE": "4g"}
GEN_LABEL = {"2g": "2G", "3g": "3G", "4g": "4G"}

DT_STATUS_MAP = {
    "Done": DTProgressStatus.DONE.value,
    "Ongoing": DTProgressStatus.ONGOING.value,
    "Problematic": DTProgressStatus.PROBLEMATIC.value,
}
DT_CATEGORY_MAP = {
    "Project Responsibility": DTProblematicCategory.PROJECT_RESPONSIBILITY.value,
    "MS Responsibility": DTProblematicCategory.MS_RESPONSIBILITY.value,
    "Temp Power": DTProblematicCategory.TEMP_POWER.value,
    "NWG Responsibility": DTProblematicCategory.NWG_RESPONSIBILITY.value,
    "Other": DTProblematicCategory.OTHER.value,
}
# Canonical display name per DT Subcontractor, keyed by UPPERCASE so casing
# variants (the real file has both "Pcom" and "PCOM") collapse to one bar on
# the per-subcontractor charts instead of silently splitting in two. Any
# contractor not yet seen here passes through unchanged rather than being
# dropped, so a new name never disappears — it just won't be normalized
# until added here.
DT_SC_CANONICAL = {
    "SFO": "SFO", "INFINITEL": "Infinitel", "SITE SC": "Site SC",
    "PCOM": "Pcom", "HFN": "HFN", "VIHAN": "Vihan",
}

DEPRECIATION_LEGACY_MAP = {
    "---": DepreciationStatus.REMAIN.value,
    "مستهلک فنی و مالی شده است": DepreciationStatus.DEPRECIATED.value,
    "تایید فنی شده و باید مستهلک شود": DepreciationStatus.WAITING.value,
}
# Depreciation only ever advances; never regress a further-along status.
DEP_RANK = {DepreciationStatus.REMAIN.value: 0, DepreciationStatus.WAITING.value: 1, DepreciationStatus.DEPRECIATED.value: 2}


def _region_uuid(label: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"region::{label}")


def _province_uuid(label: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"province::{label}")


def _clean(v) -> str:
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def _normalize_dt_sc(raw) -> str | None:
    val = _clean(raw)
    if not val:
        return None
    return DT_SC_CANONICAL.get(val.upper(), val)[:255]


def _resolve_site_key(official_raw: str, temp_raw: str) -> str:
    if official_raw and official_raw != NO_OFFICIAL_ID_PLACEHOLDER:
        return official_raw
    return temp_raw


def _tech_status(raw, gen_label: str) -> str:
    """2G-ICT/3G-ICT/4G-ICT (and CRA) cell -> AcceptanceStatus.value.
    The cell holds the tech's own label when approved, "Reject" when
    rejected, or is blank otherwise — there is no other value in practice."""
    val = _clean(raw).upper()
    if not val:
        return AcceptanceStatus.NOT_SUBMITTED.value
    if val.startswith("REJ"):
        return AcceptanceStatus.REJECTED.value
    if val == gen_label:
        return AcceptanceStatus.APPROVED.value
    return AcceptanceStatus.NOT_SUBMITTED.value


def _to_date(raw) -> date | None:
    ts = pd.to_datetime(raw, errors="coerce")
    return None if pd.isna(ts) else ts.date()


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
    # Work Item: id/on_air plus the current DT/depreciation fields, so we
    # only ever FILL BLANKS on re-import — an existing non-null value (set
    # by a previous import or, later, by the app) is never overwritten.
    workitem_by_key: dict[tuple, dict] = {
        (row.site_id, row.site_type): {
            "id": row.id, "is_on_air": row.is_on_air, "dt_status": row.dt_status,
            "dt_problematic_category": row.dt_problematic_category,
            "dt_date": row.dt_date,
            "dt_subcontractor_name": row.dt_subcontractor_name,
            "depreciation_status": row.depreciation_status,
        }
        for row in db.execute(select(
            WorkItem.id, WorkItem.site_id, WorkItem.site_type, WorkItem.is_on_air,
            WorkItem.dt_status, WorkItem.dt_problematic_category, WorkItem.dt_date,
            WorkItem.dt_subcontractor_name, WorkItem.depreciation_status,
        ))
    }
    # Acceptance is one row per (site, village). Preload the per-tech values
    # AND the approved_by markers — once a side has approved_by set, a human
    # has acted on it in the app and CPM must never touch that side again.
    existing_acceptance: dict[tuple, dict] = {
        (row.site_id, row.village_id): {
            "id": row.id,
            "ict_2g": row.ict_2g, "ict_3g": row.ict_3g, "ict_4g": row.ict_4g,
            "ict_approved_by": row.ict_approved_by,
            "cra_2g": row.cra_2g, "cra_3g": row.cra_3g, "cra_4g": row.cra_4g,
            "cra_approved_by": row.cra_approved_by,
            "depreciation_status": row.depreciation_status,
        }
        for row in db.execute(select(
            VillageAcceptance.id, VillageAcceptance.site_id, VillageAcceptance.village_id,
            VillageAcceptance.ict_2g, VillageAcceptance.ict_3g, VillageAcceptance.ict_4g,
            VillageAcceptance.ict_approved_by,
            VillageAcceptance.cra_2g, VillageAcceptance.cra_3g, VillageAcceptance.cra_4g,
            VillageAcceptance.cra_approved_by,
            VillageAcceptance.depreciation_status,
        ))
    }

    new_sites: dict[str, Site] = {}
    new_villages: dict[tuple, Village] = {}
    new_workitems: dict[tuple, WorkItem] = {}
    new_acceptance: dict[tuple, VillageAcceptance] = {}
    villages_to_flip_on: set = set()   # existing Village.id needing is_on_air -> True
    workitems_to_flip_on: set = set()  # existing WorkItem.id needing is_on_air -> True
    workitem_field_updates: dict[uuid.UUID, dict] = {}      # existing WorkItem.id -> {field: value}
    acceptance_field_updates: dict[uuid.UUID, dict] = {}    # existing VillageAcceptance.id -> {field: value}

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

        # --- Drive test + depreciation fields (Work Item / site grain) ---
        dt_status_val = DT_STATUS_MAP.get(_clean(r.get(COL_DT_STATUS)))
        dt_category_val = (
            DT_CATEGORY_MAP.get(_clean(r.get(COL_DT_CATEGORY)))
            if dt_status_val == DTProgressStatus.PROBLEMATIC.value else None
        )
        dt_sc_val = _normalize_dt_sc(r.get(COL_DT_SC))
        dt_date_val = _to_date(r.get(COL_DT_DATE))
        dep_legacy_val = DEPRECIATION_LEGACY_MAP.get(_clean(r.get(COL_DEPRECIATION_LEGACY)))

        # --- Work Item = Index 1 (Site + Site Type) ---
        stype = _clean(r.get(COL_SITE_TYPE))
        if stype:
            wkey = (site_uuid, stype)
            wi_existing = workitem_by_key.get(wkey)
            wi_new = new_workitems.get(wkey)
            if wi_existing is not None:
                if row_is_on_air and not wi_existing["is_on_air"]:
                    workitems_to_flip_on.add(wi_existing["id"])
                    wi_existing["is_on_air"] = True
                # Fill-blanks only: never overwrite a value already present.
                fields = {}
                if wi_existing["dt_status"] is None and dt_status_val:
                    fields["dt_status"] = dt_status_val
                    wi_existing["dt_status"] = dt_status_val
                if wi_existing["dt_problematic_category"] is None and dt_category_val:
                    fields["dt_problematic_category"] = dt_category_val
                    wi_existing["dt_problematic_category"] = dt_category_val
                if wi_existing["dt_subcontractor_name"] is None and dt_sc_val:
                    fields["dt_subcontractor_name"] = dt_sc_val
                    wi_existing["dt_subcontractor_name"] = dt_sc_val
                if wi_existing["dt_date"] is None and dt_date_val:
                    fields["dt_date"] = dt_date_val
                    wi_existing["dt_date"] = dt_date_val
                # Depreciation only ever advances.
                cur_rank = DEP_RANK.get(wi_existing["depreciation_status"], -1)
                new_rank = DEP_RANK.get(dep_legacy_val, -1)
                if dep_legacy_val and new_rank > cur_rank:
                    fields["depreciation_status"] = dep_legacy_val
                    wi_existing["depreciation_status"] = dep_legacy_val
                if fields:
                    workitem_field_updates.setdefault(wi_existing["id"], {}).update(fields)
            elif wi_new is not None:
                if row_is_on_air and not wi_new.is_on_air:
                    wi_new.is_on_air = True
                if wi_new.dt_status is None and dt_status_val:
                    wi_new.dt_status = dt_status_val
                if wi_new.dt_problematic_category is None and dt_category_val:
                    wi_new.dt_problematic_category = dt_category_val
                if wi_new.dt_subcontractor_name is None and dt_sc_val:
                    wi_new.dt_subcontractor_name = dt_sc_val
                if wi_new.dt_date is None and dt_date_val:
                    wi_new.dt_date = dt_date_val
                if dep_legacy_val and DEP_RANK.get(dep_legacy_val, -1) > DEP_RANK.get(wi_new.depreciation_status, -1):
                    wi_new.depreciation_status = dep_legacy_val
            else:
                new_wi = WorkItem(
                    id=uuid.uuid4(), site_id=site_uuid, site_type=stype,
                    assignment_date=None, cpm_raw_status=status or None,
                    is_on_air=row_is_on_air,
                    dt_status=dt_status_val, dt_problematic_category=dt_category_val,
                    dt_date=dt_date_val,
                    dt_subcontractor_name=dt_sc_val, depreciation_status=dep_legacy_val,
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

            # --- Acceptance: one row per (site, village). Only requested
            # technologies (from تکنولوژی درخواستی) get a status; everything
            # else stays NULL ("not requested"). ---
            tech_label = _clean(r.get(COL_TECH))
            requested_gens = {TECH_TO_GEN[t] for t in TECH_SPLIT.get(tech_label, []) if t in TECH_TO_GEN}
            if requested_gens:
                ict_vals = {gen: _tech_status(r.get(f"{GEN_LABEL[gen]}-ICT"), GEN_LABEL[gen]) for gen in requested_gens}
                cra_vals = {gen: _tech_status(r.get(f"{GEN_LABEL[gen]}-CRA"), GEN_LABEL[gen]) for gen in requested_gens}
                ict_comment = _clean(r.get(COL_ICT_COMMENT)) or None
                ict_letter_number = _clean(r.get(COL_ICT_LETTER_NUMBER))[:100] or None
                ict_letter_date = _to_date(r.get(COL_ICT_LETTER_DATE))
                cra_comment = _clean(r.get(COL_CRA_COMMENT)) or None
                cra_letter_number = _clean(r.get(COL_CRA_LETTER_NUMBER))[:100] or None
                cra_letter_date = _to_date(r.get(COL_CRA_LETTER_DATE))

                akey = (site_uuid, vcode)
                existing = existing_acceptance.get(akey)
                if existing is not None:
                    fields = {}
                    # ICT side: only touch it if no human has approved it in
                    # the app yet (Single Source Ownership after first touch).
                    if existing["ict_approved_by"] is None:
                        for gen in requested_gens:
                            if existing[f"ict_{gen}"] != ict_vals[gen]:
                                fields[f"ict_{gen}"] = ict_vals[gen]
                                existing[f"ict_{gen}"] = ict_vals[gen]
                        if ict_comment:
                            fields["ict_comment"] = ict_comment
                        if ict_letter_number:
                            fields["ict_letter_number"] = ict_letter_number
                        if ict_letter_date:
                            fields["ict_letter_date"] = ict_letter_date
                    if existing["cra_approved_by"] is None:
                        for gen in requested_gens:
                            if existing[f"cra_{gen}"] != cra_vals[gen]:
                                fields[f"cra_{gen}"] = cra_vals[gen]
                                existing[f"cra_{gen}"] = cra_vals[gen]
                        if cra_comment:
                            fields["cra_comment"] = cra_comment
                        if cra_letter_number:
                            fields["cra_letter_number"] = cra_letter_number
                        if cra_letter_date:
                            fields["cra_letter_date"] = cra_letter_date
                    # Depreciation only ever advances (independent of the
                    # ICT/CRA approved_by guard above — it's always safe to
                    # move forward on the historical legacy value).
                    cur_rank = DEP_RANK.get(existing["depreciation_status"], -1)
                    new_rank = DEP_RANK.get(dep_legacy_val, -1)
                    if dep_legacy_val and new_rank > cur_rank:
                        fields["depreciation_status"] = dep_legacy_val
                        existing["depreciation_status"] = dep_legacy_val
                    if fields:
                        acceptance_field_updates.setdefault(existing["id"], {}).update(fields)
                else:
                    va = new_acceptance.get(akey)
                    if va is None:
                        va = VillageAcceptance(id=uuid.uuid4(), site_id=site_uuid, village_id=vcode)
                        new_acceptance[akey] = va
                        counts["acceptance"] += 1
                    for gen in requested_gens:
                        setattr(va, f"ict_{gen}", ict_vals[gen])
                        setattr(va, f"cra_{gen}", cra_vals[gen])
                    va.ict_comment = va.ict_comment or ict_comment
                    va.ict_letter_number = va.ict_letter_number or ict_letter_number
                    va.ict_letter_date = va.ict_letter_date or ict_letter_date
                    va.cra_comment = va.cra_comment or cra_comment
                    va.cra_letter_number = va.cra_letter_number or cra_letter_number
                    va.cra_letter_date = va.cra_letter_date or cra_letter_date
                    if dep_legacy_val and DEP_RANK.get(dep_legacy_val, -1) > DEP_RANK.get(va.depreciation_status, -1):
                        va.depreciation_status = dep_legacy_val

    # New acceptance rows: refresh cached Final flags (and the depreciation
    # golden rule) now that every requested technology has been set.
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

    # Existing Work Items that gained previously-blank DT/depreciation
    # fields: one executemany-style UPDATE, not one round trip per row.
    if workitem_field_updates:
        all_fields = sorted({f for fields in workitem_field_updates.values() for f in fields})
        # Core Table (not the ORM class) so this is a plain executemany
        # UPDATE — the ORM entity form of update() intercepts list-of-dicts
        # execution as its own "bulk update by primary key" feature, which
        # requires an "id" key rather than our "_id" WHERE bindparam.
        stmt = update(WorkItem.__table__).where(WorkItem.id == bindparam("_id")).values(
            **{f: bindparam(f, value=None) for f in all_fields}
        )
        params = [
            {"_id": wid, **{f: fields.get(f) for f in all_fields}}
            for wid, fields in workitem_field_updates.items()
        ]
        db.execute(stmt, params)

    # Existing acceptance rows that gained refreshed ICT/CRA/depreciation
    # values (only where not yet app-approved) — same batched pattern.
    if acceptance_field_updates:
        all_fields = sorted({f for fields in acceptance_field_updates.values() for f in fields})
        stmt = update(VillageAcceptance.__table__).where(VillageAcceptance.id == bindparam("_id")).values(
            **{f: bindparam(f, value=None) for f in all_fields}
        )
        params = [
            {"_id": vid, **{f: fields.get(f) for f in all_fields}}
            for vid, fields in acceptance_field_updates.items()
        ]
        db.execute(stmt, params)
        # The bulk update bypassed the ORM identity map (synchronize_session
        # off), so any already-loaded objects in this session could be
        # stale — expire before re-reading so recompute_finals sees the
        # values the bulk update just wrote.
        db.expire_all()
        # Re-derive Final + depreciation for every touched row in one query
        # (cheaper than hydrating full ORM objects during the main loop).
        touched = db.query(VillageAcceptance).filter(VillageAcceptance.id.in_(acceptance_field_updates.keys())).all()
        for va in touched:
            va.recompute_finals()

    db.commit()

    return counts
