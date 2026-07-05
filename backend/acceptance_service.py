"""
Acceptance write logic — the in-app counterpart to the CPM importer.

Two operations live here, both of which flip a village's ICT or CRA side
from "CPM-owned" to "human-owned" (Single Source Ownership, Rule 1): once
a human touches a side through the app, `*_approved_by` is stamped and the
CPM importer will never overwrite that side again (see import_cpm.py's
`ict_approved_by is None` / `cra_approved_by is None` guards).

  1. update_acceptance_side() — a coordinator edits one village's ICT or
     CRA side directly (per-technology statuses + comment + letter fields).

  2. register_letter() — the "one letter, many villages" fan-out (Rule 5).
     A single official letter approves every requested technology on its
     side across one to thousands of linked villages, in one transaction.
     This is the whole point of the Letter entity: a coordinator records
     the letter once instead of editing thousands of rows by hand.

Only *requested* technologies participate. A village's per-tech column is
NULL when that generation was never requested for it (per CPM تکنولوژی
درخواستی); we never invent a status for a non-requested technology, exactly
as the importer and recompute_finals() already assume.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from enums import AcceptanceStatus, LetterOrganization
from models import Letter, LetterVillageMapping, Village, VillageAcceptance

# Per-tech column suffixes on VillageAcceptance for each side.
_GENS = ("2g", "3g", "4g")


def _side_prefix(side: str) -> str:
    if side not in ("ict", "cra"):
        raise ValueError("side must be 'ict' or 'cra'")
    return side


def _requested_gens(acc: VillageAcceptance, side: str) -> list[str]:
    """Generations actually requested for this village on this side — the
    ones whose per-tech column is non-NULL."""
    return [g for g in _GENS if getattr(acc, f"{side}_{g}") is not None]


def _letter_side(org: str) -> str:
    """ICT letter organizations map to the ICT side, CRA to the CRA side."""
    if org in (LetterOrganization.ICT_PROVINCE.value, LetterOrganization.ICT_HQ.value):
        return "ict"
    if org in (LetterOrganization.CRA_REGION.value, LetterOrganization.CRA_HQ.value):
        return "cra"
    raise ValueError(f"Unrecognized letter organization: {org}")


def update_acceptance_side(
    db: Session,
    acc: VillageAcceptance,
    side: str,
    *,
    statuses: dict[str, str],          # {"2g": AcceptanceStatus.value, ...} for requested gens only
    comment: str | None,
    letter_number: str | None,
    letter_date,
    actor_id: uuid.UUID,
) -> None:
    """Apply a coordinator's ICT or CRA edit to one village. Only requested
    generations may be set — a status for a non-requested generation is a
    caller error (validated in the route). Stamps approved_by/at (Single
    Source Ownership) and recomputes Final + the depreciation golden rule.

    Does NOT commit — the caller owns the transaction boundary."""
    side = _side_prefix(side)
    requested = set(_requested_gens(acc, side))

    for gen, value in statuses.items():
        if gen not in requested:
            raise ValueError(
                f"{gen.upper()} was not a requested technology for this village's "
                f"{side.upper()} side; it cannot be given a status."
            )
        setattr(acc, f"{side}_{gen}", value)

    if comment is not None:
        setattr(acc, f"{side}_comment", comment)
    if letter_number is not None:
        setattr(acc, f"{side}_letter_number", letter_number)
    if letter_date is not None:
        setattr(acc, f"{side}_letter_date", letter_date)

    # Human ownership of this side from now on — CPM must never overwrite it.
    setattr(acc, f"{side}_approved_by", actor_id)
    setattr(acc, f"{side}_approved_at", datetime.now(timezone.utc))

    acc.recompute_finals()


def register_letter(
    db: Session,
    *,
    letter_number: str,
    letter_date,
    organization: str,
    province_or_region_id: uuid.UUID,
    comment: str | None,
    pdf_attachment_url: str | None,
    village_acceptance_ids: list[uuid.UUID],
    actor_id: uuid.UUID,
) -> Letter:
    """Record one official letter and fan it out to every linked village.

    For each linked village, on the letter's side (ICT or CRA, from the
    organization): approve every *requested* technology, stamp the letter
    number/date, set approved_by/at, and recompute Final + depreciation.
    All village_acceptance_ids must exist, or the whole thing raises before
    anything is written. Does NOT commit — caller owns the transaction."""
    side = _letter_side(organization)

    accs = (
        db.query(VillageAcceptance)
        .filter(VillageAcceptance.id.in_(village_acceptance_ids))
        .all()
    )
    found = {a.id for a in accs}
    missing = [str(vid) for vid in village_acceptance_ids if vid not in found]
    if missing:
        raise ValueError(f"Unknown village acceptance id(s): {', '.join(missing)}")

    letter = Letter(
        id=uuid.uuid4(),
        letter_number=letter_number,
        letter_date=letter_date,
        organization=organization,
        province_or_region_id=province_or_region_id,
        comment=comment,
        pdf_attachment_url=pdf_attachment_url,
    )
    db.add(letter)

    now = datetime.now(timezone.utc)
    for acc in accs:
        for gen in _requested_gens(acc, side):
            setattr(acc, f"{side}_{gen}", AcceptanceStatus.APPROVED.value)
        setattr(acc, f"{side}_letter_number", letter_number)
        setattr(acc, f"{side}_letter_date", letter_date)
        setattr(acc, f"{side}_approved_by", actor_id)
        setattr(acc, f"{side}_approved_at", now)
        acc.recompute_finals()
        db.add(LetterVillageMapping(
            id=uuid.uuid4(), letter_id=letter.id, village_acceptance_id=acc.id
        ))

    return letter


def village_name_map(db: Session, acc_rows: list[VillageAcceptance]) -> dict[tuple, str]:
    """(site_id, village_id) -> village_name for a batch of acceptance rows,
    joined from the Village table (VillageAcceptance stores only the code)."""
    keys = {(a.site_id, a.village_id) for a in acc_rows}
    if not keys:
        return {}
    site_ids = {sid for sid, _ in keys}
    vcodes = {vc for _, vc in keys}
    rows = (
        db.query(Village.site_id, Village.village_id, Village.village_name)
        .filter(Village.site_id.in_(site_ids), Village.village_id.in_(vcodes))
        .all()
    )
    return {(sid, vc): name for sid, vc, name in rows}
