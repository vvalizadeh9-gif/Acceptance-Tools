"""
Drive Test two-stage approval workflow.

The lifecycle, matching the PM/Coordinator/Subcontractor workflow split:

    Subcontractor submits
            |
            v
        SUBMITTED  ──(coordinator rejects)──▶ REJECTED ──▶ (subcontractor
            |                                                may resubmit:
    (coordinator validates)                                 new revision)
            |
            v
      UNDER_REVIEW  ──(PM rejects)──────────▶ REJECTED
            |
     (PM approves)
            |
            v
        APPROVED   ──▶ Work Item dt_status = DONE, dt_date = delivery_date

Separation of duties (SEC-03): PM approval can only act on an UNDER_REVIEW
drive test — i.e. the coordinator must have validated first. No single actor
can carry a drive test from submission to final approval.

Invariant (Domain 5): a Work Item has at most one *active* drive test
(SUBMITTED or UNDER_REVIEW) at a time. A rejected drive test is terminal for
its revision and stays in history; the subcontractor submits a fresh revision
to try again. The latest APPROVED drive test is the operative one.

Each transition appends an immutable DriveTestReview (the per-stage decision
ledger) and a TimelineEvent (the Work Item's lifecycle log). Nothing here
commits — the route owns the transaction boundary.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from enums import DriveTestStatus, DTProgressStatus, ReviewDecision
from models import DriveTest, DriveTestReview, TimelineEvent, WorkItem

_ACTIVE_STATUSES = (DriveTestStatus.SUBMITTED.value, DriveTestStatus.UNDER_REVIEW.value)


class WorkflowError(Exception):
    """Raised on an illegal transition; the route maps it to HTTP 409."""


def _timeline(db: Session, work_item_id: uuid.UUID, event_type: str, description: str, actor_id: uuid.UUID) -> None:
    db.add(TimelineEvent(
        id=uuid.uuid4(), work_item_id=work_item_id,
        event_type=event_type, description=description, actor_id=actor_id,
    ))


def submit_drive_test(
    db: Session, work_item: WorkItem, *,
    contractor_id: uuid.UUID, delivery_date: date, report_url: str,
) -> DriveTest:
    """Subcontractor submits a drive test for a work item they're assigned to.
    Rejected only if an active (SUBMITTED/UNDER_REVIEW) drive test already
    exists — you can't stack two in flight. Revision number increments across
    resubmissions so the history is ordered."""
    active = db.execute(
        select(DriveTest.id).where(
            DriveTest.work_item_id == work_item.id,
            DriveTest.status.in_(_ACTIVE_STATUSES),
        )
    ).first()
    if active is not None:
        raise WorkflowError(
            "This work item already has a drive test in progress; resolve it before submitting another."
        )
    prior = db.execute(
        select(DriveTest.revision_no).where(DriveTest.work_item_id == work_item.id)
    ).scalars().all()
    revision = (max(prior) + 1) if prior else 1

    dt = DriveTest(
        id=uuid.uuid4(), work_item_id=work_item.id, contractor_id=contractor_id,
        delivery_date=delivery_date, report_url=report_url,
        status=DriveTestStatus.SUBMITTED.value, revision_no=revision,
    )
    db.add(dt)
    _timeline(db, work_item.id, "dt_submitted",
              f"Drive test revision {revision} submitted", contractor_id)
    return dt


def coordinator_validate(
    db: Session, dt: DriveTest, *, approve: bool, comment: str, reviewer_id: uuid.UUID,
) -> DriveTest:
    """Coordinator's stage-1 review. Approve moves SUBMITTED -> UNDER_REVIEW
    (queued for PM); reject moves SUBMITTED -> REJECTED (back to the
    subcontractor)."""
    if dt.status != DriveTestStatus.SUBMITTED.value:
        raise WorkflowError(
            f"Only a submitted drive test can be validated by a coordinator (this one is '{dt.status}')."
        )
    if approve:
        dt.status = DriveTestStatus.UNDER_REVIEW.value
        decision, event, msg = ReviewDecision.APPROVED.value, "dt_coordinator_validated", "Coordinator validated the drive test"
    else:
        dt.status = DriveTestStatus.REJECTED.value
        decision, event, msg = ReviewDecision.REJECTED.value, "dt_coordinator_rejected", "Coordinator rejected the drive test"

    db.add(DriveTestReview(
        id=uuid.uuid4(), drive_test_id=dt.id, reviewer=reviewer_id,
        review_level="coordinator", decision=decision, comment=comment,
    ))
    _timeline(db, dt.work_item_id, event, msg, reviewer_id)
    return dt


def pm_decide(
    db: Session, dt: DriveTest, work_item: WorkItem, *,
    approve: bool, comment: str, reviewer_id: uuid.UUID,
) -> DriveTest:
    """PM's stage-2 review. Guarded to UNDER_REVIEW only, so the coordinator
    must have validated first (separation of duties). Approval marks the Work
    Item's site-grain DT status DONE and records the delivery date."""
    if dt.status != DriveTestStatus.UNDER_REVIEW.value:
        raise WorkflowError(
            f"PM approval requires a coordinator-validated drive test (this one is '{dt.status}')."
        )
    if approve:
        dt.status = DriveTestStatus.APPROVED.value
        work_item.dt_status = DTProgressStatus.DONE.value
        work_item.dt_date = dt.delivery_date
        decision, event, msg = ReviewDecision.APPROVED.value, "dt_pm_approved", "PM approved the drive test"
    else:
        dt.status = DriveTestStatus.REJECTED.value
        decision, event, msg = ReviewDecision.REJECTED.value, "dt_pm_rejected", "PM rejected the drive test"

    db.add(DriveTestReview(
        id=uuid.uuid4(), drive_test_id=dt.id, reviewer=reviewer_id,
        review_level="pm", decision=decision, comment=comment,
    ))
    _timeline(db, dt.work_item_id, event, msg, reviewer_id)
    return dt
