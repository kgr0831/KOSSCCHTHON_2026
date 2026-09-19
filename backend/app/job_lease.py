"""Lock owner then job before checking a lease; a reclaimed job must not be overwritten."""
from sqlalchemy import select

from .common import lock_user
from .models import Job


def locked_lease(db, job_id, token):
    # Read the immutable owner first, then use the same owner -> job lock order
    # as document mutations and retries. Refresh the job after acquiring locks.
    user_id = db.scalar(select(Job.user_id).where(Job.id == job_id))
    if user_id is None:
        return None
    lock_user(db, user_id)
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update()
                    .execution_options(populate_existing=True))
    return job if job and job.lease_token == token and job.status == "running" else None
