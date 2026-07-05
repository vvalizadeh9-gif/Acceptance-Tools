"""
Acceptance dashboard aggregation (ICT & CRA, kept side-by-side and independent).

Definitions locked with the owner:

  * "Villages with DT" — the denominator everywhere — is villages whose SITE
    has a completed drive test (at least one WorkItem with dt_status = 'done').
    Acceptance only makes sense after the drive test, so ungdt villages are
    excluded from every count.

  * Per village, per side (ICT / CRA), using only REQUESTED technologies
    (the non-NULL per-tech columns), each village lands in exactly one bucket
    so the four sum to the total:
      - approved     : the side is Final (every requested tech approved)
      - rejected     : at least one requested tech rejected (and not Final)
      - no_feedback  : every requested tech is not_submitted (untouched)
      - remaining    : anything in between (partial progress, no rejection)

  * Site rollups (a "village approved" = both ICT-final AND CRA-final):
      - fully_ict   : all the site's villages are ICT-final
      - fully_cra   : all CRA-final
      - fully_both  : all villages approved (both)
      - partial     : at least one village approved but NOT all (owner's rule:
                      2 approved + 1 rejected on a site = partial, not full)
      - ict_not_cra : site fully ICT-approved but not fully CRA-approved
      - cra_not_ict : the reverse

  * Current-month progress is EXACT and event-based: villages whose
    ict_approved_at / cra_approved_at falls in the current Jalali month, vs the
    previous Jalali month. No snapshot guesswork.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from jalali import (
    MONTHS_EN, current_period, days_in_period, jalali_day, jalali_period,
    period_label, previous_period,
)
from models import Site, VillageAcceptance, WorkItem

_GENS = ("2g", "3g", "4g")
_APPROVED = "approved"
_REJECTED = "rejected"
_NOT_SUBMITTED = "not_submitted"


def _classify(acc: VillageAcceptance, side: str) -> str:
    """One of approved / rejected / no_feedback / remaining for this side."""
    requested = [getattr(acc, f"{side}_{g}") for g in _GENS if getattr(acc, f"{side}_{g}") is not None]
    if not requested:
        return "no_feedback"  # nothing requested on this side -> nothing to approve
    if getattr(acc, f"{side}_final"):
        return "approved"
    if any(v == _REJECTED for v in requested):
        return "rejected"
    if all(v == _NOT_SUBMITTED for v in requested):
        return "no_feedback"
    return "remaining"


def _pct(n: int, total: int) -> float:
    return round(n * 100.0 / total, 1) if total else 0.0


def _blank_bucket() -> dict:
    return {"total": 0, "approved": 0, "remaining": 0, "rejected": 0, "no_feedback": 0}


def build_acceptance_dashboard(db: Session, technology: str | None = None) -> dict:
    """technology filter: None/'all' = every requested tech; '2g'/'3g'/'4g'
    restricts the classification to that generation only."""
    tech = (technology or "all").lower()
    gens = _GENS if tech in ("all", "") else (tech,)

    # Sites whose drive test is done (>=1 done work item) -> the DT gate.
    dt_site_ids = set(db.execute(
        select(WorkItem.site_id).where(WorkItem.dt_status == "done").distinct()
    ).scalars().all())

    # Pull acceptance rows joined to their site's province, restricted to DT sites.
    rows = db.execute(
        select(VillageAcceptance, Site.province_name).join(Site, Site.id == VillageAcceptance.site_id)
    ).all()

    ict_summary = _blank_bucket()
    cra_summary = _blank_bucket()
    ict_by_prov: dict[str, dict] = {}
    cra_by_prov: dict[str, dict] = {}
    # site_id -> {"total": n, "ict_final": n, "cra_final": n, "both": n}
    site_stats: dict = {}

    cur = current_period()
    prev = previous_period(cur)
    ict_month = {"cur": 0, "prev": 0, "daily": [0] * (days_in_period(cur) + 1)}
    cra_month = {"cur": 0, "prev": 0, "daily": [0] * (days_in_period(cur) + 1)}

    def _classify_tech(acc, side):
        # honor the technology filter by nulling out non-selected gens
        if gens == _GENS:
            return _classify(acc, side)
        # build a shim view: only the selected gen counts
        vals = [getattr(acc, f"{side}_{g}") for g in gens if getattr(acc, f"{side}_{g}") is not None]
        if not vals:
            return "no_feedback"
        if all(v == _APPROVED for v in vals):
            return "approved"
        if any(v == _REJECTED for v in vals):
            return "rejected"
        if all(v == _NOT_SUBMITTED for v in vals):
            return "no_feedback"
        return "remaining"

    for acc, province in rows:
        if acc.site_id not in dt_site_ids:
            continue
        province = province or "Unknown"

        ic = _classify_tech(acc, "ict")
        cc = _classify_tech(acc, "cra")

        for summ, by_prov, bucket in ((ict_summary, ict_by_prov, ic), (cra_summary, cra_by_prov, cc)):
            summ["total"] += 1
            summ[bucket] += 1
            p = by_prov.setdefault(province, _blank_bucket())
            p["total"] += 1
            p[bucket] += 1

        # site rollup uses full (all-tech) finals, not the tech filter
        s = site_stats.setdefault(acc.site_id, {"total": 0, "ict_final": 0, "cra_final": 0, "both": 0})
        s["total"] += 1
        if acc.ict_final:
            s["ict_final"] += 1
        if acc.cra_final:
            s["cra_final"] += 1
        if acc.ict_final and acc.cra_final:
            s["both"] += 1

        # current-month progress (event-based, exact)
        for side, box in (("ict", ict_month), ("cra", cra_month)):
            ap = getattr(acc, f"{side}_approved_at")
            per = jalali_period(ap)
            if per == cur:
                box["cur"] += 1
                d = jalali_day(ap)
                if d and d < len(box["daily"]):
                    box["daily"][d] += 1
            elif per == prev:
                box["prev"] += 1

    # --- site rollups ---
    fully_ict = fully_cra = fully_both = partial = ict_not_cra = cra_not_ict = 0
    for s in site_stats.values():
        t = s["total"]
        if t == 0:
            continue
        fi = s["ict_final"] == t
        fc = s["cra_final"] == t
        fb = s["both"] == t
        if fi:
            fully_ict += 1
        if fc:
            fully_cra += 1
        if fb:
            fully_both += 1
        if s["both"] > 0 and s["both"] < t:
            partial += 1
        if fi and not fc:
            ict_not_cra += 1
        if fc and not fi:
            cra_not_ict += 1

    def _summary_out(b: dict) -> dict:
        t = b["total"]
        return {
            "total": t,
            "approved": b["approved"], "approved_pct": _pct(b["approved"], t),
            "remaining": b["remaining"], "remaining_pct": _pct(b["remaining"], t),
            "rejected": b["rejected"], "rejected_pct": _pct(b["rejected"], t),
            "no_feedback": b["no_feedback"], "no_feedback_pct": _pct(b["no_feedback"], t),
        }

    def _prov_out(by_prov: dict) -> list:
        out = []
        for name, b in by_prov.items():
            t = b["total"]
            out.append({
                "province": name, "total_with_dt": t,
                "approved": b["approved"], "approved_pct": _pct(b["approved"], t),
                "remaining": b["remaining"], "remaining_pct": _pct(b["remaining"], t),
                "rejected": b["rejected"], "rejected_pct": _pct(b["rejected"], t),
                "no_feedback": b["no_feedback"], "no_feedback_pct": _pct(b["no_feedback"], t),
            })
        out.sort(key=lambda r: r["approved"], reverse=True)
        return out

    def _month_out(box: dict) -> dict:
        delta = box["cur"] - box["prev"]
        pct = round((delta * 100.0 / box["prev"]), 1) if box["prev"] else None
        # cumulative daily series for the line chart
        cum, running = [], 0
        for i in range(1, len(box["daily"])):
            running += box["daily"][i]
            cum.append(running)
        return {"approved_this_month": box["cur"], "last_month": box["prev"],
                "delta": delta, "delta_pct": pct, "daily_cumulative": cum}

    return {
        "months": {
            "current": cur, "current_label": period_label(cur),
            "previous": prev, "previous_label": period_label(prev),
            "month_names": MONTHS_EN,
        },
        "technology": tech,
        "ict": {
            "summary": _summary_out(ict_summary),
            "by_province": _prov_out(ict_by_prov),
            "current_month": _month_out(ict_month),
        },
        "cra": {
            "summary": _summary_out(cra_summary),
            "by_province": _prov_out(cra_by_prov),
            "current_month": _month_out(cra_month),
        },
        "site_rollup": {
            "fully_ict": fully_ict, "fully_cra": fully_cra, "fully_both": fully_both,
            "partial": partial, "ict_not_cra": ict_not_cra, "cra_not_ict": cra_not_ict,
        },
    }
