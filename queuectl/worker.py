import os
import signal
import subprocess
import time
import uuid
from multiprocessing import Process, Event
from typing import Optional
from pathlib import Path

from .models import (
    lease_next_job,
    mark_completed,
    mark_failed,
)
from .utils import utcnow, iso


stop_event = Event()


def handle_sigterm(signum, frame):
    print("[worker] Received stop signal. Shutting down gracefully...")
    stop_event.set()


# Register for SIGTERM / CTRL+C handling
signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)


def execute_command(command: str) -> int:
    """Execute a shell command and return its exit code."""
    try:
        proc = subprocess.Popen(command, shell=True)
        proc.wait()
        return proc.returncode
    except Exception:
        return -1  # treat unexpected exceptions as failure


def worker_loop(worker_id: str, backoff_base: int = 2):
    print(f"[worker {worker_id}] Started at {iso(utcnow())}")

    while not stop_event.is_set():
        # Try leasing a job
        job = lease_next_job(worker_id)

        if not job:
            time.sleep(1)  # No jobs available, avoid busy loop
            continue

        print(f"[worker {worker_id}] Processing job {job['id']} : {job['command']}")

        exit_code = execute_command(job["command"])

        if exit_code == 0:
            print(f"[worker {worker_id}] Job {job['id']} completed successfully.")
            mark_completed(job["id"])
        else:
            print(
                f"[worker {worker_id}] Job {job['id']} failed (exit={exit_code}). Retrying..."
            )
            mark_failed(job, backoff_base)

    print(f"[worker {worker_id}] Stopped gracefully.")


def start_workers(count: int, backoff_base: int = 2):
    """Start multiple worker processes and manage graceful shutdown."""

    workers = []
    for i in range(count):
        worker_id = f"{os.getpid()}-{uuid.uuid4()}"
        p = Process(target=worker_loop, args=(worker_id, backoff_base))
        p.start()
        record_worker_pid(p.pid)
        workers.append(p)
        print(f"[manager] Started worker {worker_id}")

    try:
        for p in workers:
            p.join()
    except KeyboardInterrupt:
        print("[manager] Stop signal received. Stopping all workers...")
        stop_event.set()
        for p in workers:
            p.terminate()
            p.join()
    finally:
        # ✅ only clear after all workers have stopped
        clear_worker_pids()


PID_FILE = Path.home() / ".queuectl" / "workers.pid"


def record_worker_pid(pid: int):
    """Append worker PID to file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PID_FILE, "a") as f:
        f.write(f"{pid}\n")


def clear_worker_pids():
    """Remove PID file if it exists."""
    if PID_FILE.exists():
        PID_FILE.unlink()


def get_all_worker_pids():
    """Read all worker PIDs from file."""
    if not PID_FILE.exists():
        return []
    with open(PID_FILE, "r") as f:
        return [int(line.strip()) for line in f if line.strip().isdigit()]
