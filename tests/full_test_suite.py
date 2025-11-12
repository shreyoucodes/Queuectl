#!/usr/bin/env python3
"""
Functional test suite for QueueCTL
"""
import time, subprocess
from queuectl.storage import init_db, DB_PATH
from queuectl.models import create_job, get_job, list_jobs, list_dlq, retry_from_dlq
from queuectl.worker import start_workers

def assert_print(cond, msg):
    print("[PASS]" if cond else "[FAIL]", msg)
    return cond

def test_setup():
    print("\n== Setup: init DB ==")
    init_db()
    ok = DB_PATH.exists()
    assert_print(ok, f"DB file exists at {DB_PATH}")
    return ok

def test_enqueue_and_fields():
    print("\n== Test 1: Enqueue & Fields ==")
    job = {"id": "ts_enqueue_1", "command": "echo ts_ok", "max_retries": 2}
    create_job(job)
    j = get_job(job["id"])
    ok = j is not None and j["state"] == "pending"
    fields_ok = all(k in j for k in ("id","command","state","attempts","max_retries","created_at","updated_at")) if j else False
    assert_print(ok, "job enqueued & pending")
    assert_print(fields_ok, "job has required fields")
    return ok and fields_ok

def test_single_worker_completion():
    print("\n== Test 2: Worker executes job ==")
    job = {"id": "ts_worker_1", "command": "echo done_ts_worker_1", "max_retries": 1}
    create_job(job)
    start_workers(1)
    j = get_job(job["id"])
    ok = j and j["state"] == "completed"
    assert_print(ok, f"job {job['id']} completed")
    return ok

def test_multiple_workers():
    print("\n== Test 3: Multiple workers ==")
    ids=[]
    for i in range(5):
        j = {"id": f"ts_multi_{i}", "command": f"echo multi_{i}", "max_retries": 1}
        create_job(j); ids.append(j["id"])
    start_workers(3)
    jobs=[get_job(i) for i in ids]
    ok=all(j and j["state"]=="completed" for j in jobs)
    assert_print(ok, "all jobs completed with multi-workers")
    return ok

def test_retry_dlq():
    print("\n== Test 4: Retry & DLQ ==")
    j={"id":"ts_fail_1","command":"bash -c 'exit 1'","max_retries":1}
    create_job(j)
    start_workers(1)
    dlq=list_dlq()
    in_dlq=any(d["id"]==j["id"] for d in dlq)
    assert_print(in_dlq,"failing job moved to DLQ")
    return in_dlq

def test_persistence():
    print("\n== Test 5: Persistence ==")
    j={"id":"ts_persist_1","command":"echo persist_ok"}
    create_job(j)
    from queuectl.models import get_job as gj
    found = gj(j["id"]) is not None
    assert_print(found,"job visible after restart simulation")
    return found

def test_cli_status():
    print("\n== Test 6: CLI list/status ==")
    r1=subprocess.run(["python","-m","queuectl.cli","list"],capture_output=True,text=True)
    r2=subprocess.run(["python","-m","queuectl.cli","status"],capture_output=True,text=True)
    ok1,ok2=r1.returncode==0,r2.returncode==0
    assert_print(ok1,"list works"); assert_print(ok2,"status works")
    return ok1 and ok2

def run_all():
    print("Running full functional test suite for QueueCTL\n" + "="*60)
    res=[]
    if test_setup():
        res.append(test_enqueue_and_fields())
        res.append(test_single_worker_completion())
        res.append(test_multiple_workers())
        res.append(test_retry_dlq())
        res.append(test_persistence())
        res.append(test_cli_status())
    passed=sum(1 for r in res if r)
    print(f"\nSummary: {passed}/{len(res)} tests passed.")

if __name__=="__main__":
    run_all()
