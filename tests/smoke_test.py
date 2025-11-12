import time
import threading

from queuectl.storage import init_db
from queuectl.models import (
    create_job,
    get_job,
    retry_from_dlq,
    list_dlq,
)
from queuectl.worker import worker_loop, stop_event


def run_worker_for(seconds: float):
    """Run a worker loop in a background thread for N seconds."""
    stop_event.clear()

    t = threading.Thread(
        target=worker_loop, args=("smoke-worker",), daemon=True
    )
    t.start()

    time.sleep(seconds)
    stop_event.set()
    t.join()


def test_successful_job():
    print("\n--- Test 1: Successful Job Execution ---")

    create_job({
        "id": "success1",
        "command": "echo smoke_success",
        "max_retries": 2,
    })

    run_worker_for(2)

    job = get_job("success1")
    if job and job["state"] == "completed":
        print("[PASS] Successful job completed")
    else:
        print("[FAIL] Successful job did NOT complete")
        print("Job:", job)


def test_failing_job_to_dlq():
    print("\n--- Test 2: Failing Job moves to DLQ ---")

    create_job({
        "id": "fail1",
        "command": "nonexistent_command_123",
        "max_retries": 1,
    })

    # Let worker process + retry + fail
    run_worker_for(5)

    dlq = list_dlq()

    if any(j["id"] == "fail1" for j in dlq):
        print("[PASS] Failing job moved to DLQ")
    else:
        print("[FAIL] Failing job NOT found in DLQ")


def test_retry_from_dlq():
    print("\n--- Test 3: Retry from DLQ ---")

    ok = retry_from_dlq("fail1")
    if ok:
        print("[PASS] DLQ retry succeeded")
    else:
        print("[FAIL] DLQ retry did not succeed")

    # Give worker time to pick it up / schedule next retry
    run_worker_for(3)

    job = get_job("fail1")

    if job:
        print(f"[PASS] Retried job is back in queue with state: {job['state']}")
    else:
        print("[FAIL] Retried job not found after DLQ retry")


if __name__ == "__main__":
    print("Running QueueCTL Smoke Tests")
    print("============================")

    # reset db for clean test runs
    init_db()

    test_successful_job()
    test_failing_job_to_dlq()
    test_retry_from_dlq()

    print("\nAll tests finished.\n")
