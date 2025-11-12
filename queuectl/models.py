import uuid
import time
from typing import Optional, List, Dict

from .storage import execute, fetchone, fetchall, get_connection
from .utils import utcnow, iso

def query(sql: str, params: tuple = ()):
    """Run a SELECT query and return rows as a list of dicts."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows

# -----------------------------
# Job CRUD
# -----------------------------

def create_job(job: dict):
    """
    Insert a new job into the jobs table.
    Ensures all required fields are populated as per spec.
    """
    now = iso(utcnow())

    # set default values if missing
    job.setdefault("state", "pending")
    job.setdefault("attempts", 0)
    job.setdefault("max_retries", 3)
    job.setdefault("created_at", now)
    job.setdefault("updated_at", now)
    job.setdefault("run_after", 0.0)
    job.setdefault("lease_id", None)
    job.setdefault("lease_until", None)

    execute(
        """
        INSERT INTO jobs (
            id,
            command,
            state,
            attempts,
            max_retries,
            created_at,
            updated_at,
            run_after,
            lease_id,
            lease_until
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job["id"],
            job["command"],
            job["state"],
            job["attempts"],
            job["max_retries"],
            job["created_at"],
            job["updated_at"],
            job["run_after"],
            job["lease_id"],
            job["lease_until"],
        ),
    )




def get_job(job_id: str) -> Optional[dict]:
    row = fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
    return dict(row) if row else None


def list_jobs(state: Optional[str] = None) -> List[dict]:
    if state:
        rows = fetchall("SELECT * FROM jobs WHERE state = ?", (state,))
    else:
        rows = fetchall("SELECT * FROM jobs")
    return [dict(r) for r in rows]


# -----------------------------
# Leasing (atomic job reservation)
# -----------------------------

LEASE_DURATION = 30  # seconds for a worker lock


import time
from queuectl.storage import get_connection
from queuectl.utils import iso, utcnow

def lease_next_job(worker_id: str):
    """Atomically claim the next available job without blocking other workers."""
    now_ts = time.time()
    lease_until = now_ts + 30
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE jobs
        SET state='processing',
            lease_id=?,
            lease_until=?,
            updated_at=?
        WHERE id = (
            SELECT id FROM jobs
            WHERE state IN ('pending', 'failed')
              AND (run_after IS NULL OR run_after <= ?)
            ORDER BY created_at ASC
            LIMIT 1
        )
        RETURNING id, command, state, attempts, max_retries, created_at, updated_at, run_after;
        """,
        (worker_id, lease_until, iso(utcnow()), now_ts),
    )

    row = cur.fetchone()
    conn.commit()
    conn.close()
    if not row:
        return None
    cols = ["id", "command", "state", "attempts", "max_retries", "created_at", "updated_at", "run_after"]
    return dict(zip(cols, row))



# -----------------------------
# Job completion / failures
# -----------------------------

def mark_completed(job_id: str):
    execute(
        """
        UPDATE jobs
        SET state='completed',
            updated_at=?,
            lease_id=NULL,
            lease_until=NULL
        WHERE id=?
        """,
        (iso(utcnow()), job_id),
    )

import math
from queuectl.storage import execute
from queuectl.utils import utcnow, iso

def mark_failed(job, backoff_base=2):
    """Mark a job as failed and handle retries with exponential backoff."""
    job_id = job["id"]
    job["attempts"] += 1
    now = iso(utcnow())

    # if max retries exceeded → move to DLQ
    if job["attempts"] >= job["max_retries"]:
        execute(
            """
            UPDATE jobs
            SET state = 'dead', updated_at = ?, lease_id = NULL, lease_until = NULL
            WHERE id = ?
            """,
            (now, job_id),
        )
        # record to DLQ table
        execute(
            """
            INSERT INTO dlq (id, command, attempts, reason, failed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                job_id,
                job["command"],
                job["attempts"],
                f"Max retries ({job['max_retries']}) exhausted",
                now,
            ),
        )
        print(f"[DLQ] Job {job_id} moved to Dead Letter Queue.")
        return

    # else retry with exponential backoff
    delay = math.pow(backoff_base, job["attempts"])
    next_run = time.time() + delay
    execute(
        """
        UPDATE jobs
        SET state = 'failed',
            attempts = ?,
            updated_at = ?,
            run_after = ?,
            lease_id = NULL,
            lease_until = NULL
        WHERE id = ?
        """,
        (job["attempts"], now, next_run, job_id),
    )
    print(f"[worker] Job {job_id} scheduled to retry in {delay:.1f}s.")



# -----------------------------
# DLQ handling
# -----------------------------

def move_to_dlq(job: dict, reason: str):
    execute(
        """
        INSERT OR REPLACE INTO dlq (id, command, attempts, reason, failed_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            job["id"],
            job["command"],
            job["attempts"],
            reason,
            iso(utcnow()),
        ),
    )

    execute("DELETE FROM jobs WHERE id = ?", (job["id"],))


def list_dlq() -> List[dict]:
    rows = fetchall("SELECT * FROM dlq")
    return [dict(r) for r in rows]


def retry_from_dlq(job_id: str):
    """Move a job from DLQ back into the main queue for reprocessing."""
    # fetch from DLQ
    rows = query("SELECT * FROM dlq WHERE id = ?", (job_id,))
    if not rows:
        print(f"[red]No such job {job_id} in DLQ.[/red]")
        return False

    job = dict(rows[0])

    # delete old entry from jobs table (if exists)
    execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    # re-enqueue as a fresh job
    now = iso(utcnow())
    create_job(
        {
            "id": job["id"],
            "command": job["command"],
            "state": "pending",
            "attempts": 0,
            "max_retries": 3,
            "created_at": now,
            "updated_at": now,
            "run_after": 0.0,
            "lease_id": None,
            "lease_until": None,
        }
    )

    # remove from DLQ
    execute("DELETE FROM dlq WHERE id = ?", (job_id,))

    return True


def count_jobs_by_state():
    rows = query("SELECT state, COUNT(*) AS c FROM jobs GROUP BY state")
    return {r["state"]: r["c"] for r in rows}
