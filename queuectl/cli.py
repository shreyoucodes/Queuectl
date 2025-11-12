import json
import typer
from rich import print
from rich.table import Table

from .storage import init_db, execute, fetchone
from .models import (
    create_job,
    list_jobs,
    get_job,
    list_dlq,
    retry_from_dlq,
)
from .worker import start_workers

app = typer.Typer(help="QueueCTL - Background Job Queue System")
worker_app = typer.Typer(help="Worker related commands")
dlq_app = typer.Typer(help="Dead Letter Queue commands")
config_app = typer.Typer(help="Configuration commands")

app.add_typer(worker_app, name="worker")
app.add_typer(dlq_app, name="dlq")
app.add_typer(config_app, name="config")


@app.command()
def enqueue(job_json: str):
    """
    Enqueue a new job.
    Example:
    queuectl enqueue '{"id":"job1","command":"echo hello"}'
    """
    try:
        job = json.loads(job_json)
        create_job(job)
        print(f"[green]Job {job.get('id')} enqueued successfully.[/green]")
    except json.JSONDecodeError:
        print("[red]Invalid JSON[/red]")


# ---------------------------
# WORKER COMMANDS
# ---------------------------

@worker_app.command("start")
def worker_start(count: int = typer.Option(1, help="Number of workers")):
    """Start background workers."""
    print(f"[cyan]Starting {count} worker(s)...[/cyan]")
    start_workers(count)

@worker_app.command("stop")
def stop_workers():
    """Stop all running workers gracefully."""
    from queuectl.worker import get_all_worker_pids, PID_FILE
    import os, signal, time

    pids = get_all_worker_pids()
    if not pids:
        print("[yellow]No active workers found.[/yellow]")
        return

    print(f"Stopping {len(pids)} worker(s)...")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to worker PID {pid}")
        except ProcessLookupError:
            print(f"[red]Worker {pid} already stopped.[/red]")

    time.sleep(1)
    if PID_FILE.exists():
        PID_FILE.unlink()

    print("[green]All workers stopped gracefully.[/green]")

# ---------------------------
# JOB LISTING & STATUS
# ---------------------------

@app.command()
def list(state: str = None):
    """List jobs by state. Example: queuectl list --state pending"""
    jobs = list_jobs(state)
    table = Table(title=f"Jobs (state={state or 'all'})")
    table.add_column("ID")
    table.add_column("Command")
    table.add_column("State")
    table.add_column("Attempts")
    table.add_column("Max")
    table.add_column("Updated")

    for j in jobs:
        table.add_row(
            j["id"],
            j["command"],
            j["state"],
            str(j["attempts"]),
            str(j["max_retries"]),
            j["updated_at"],
        )

    print(table)


@app.command()
def status():
    """Show summary of all job states & active workers."""
    from rich.table import Table
    from rich.console import Console
    from queuectl.models import count_jobs_by_state
    import psutil

    # Count jobs by each state
    counts = count_jobs_by_state()
    states = ["pending", "processing", "completed", "failed", "dead"]

    # Count active workers using psutil (optional enhancement)
    active_workers = 0
    try:
        from queuectl.worker import get_all_worker_pids
        for pid in get_all_worker_pids():
            if psutil.pid_exists(pid):
                active_workers += 1
    except Exception:
        pass

    # Build rich table
    table = Table(title="Queue Status")
    for state in states:
        table.add_column(state.capitalize())

    table.add_row(*(str(counts.get(s, 0)) for s in states))

    Console().print(table)

    print(f"\nActive Workers: {active_workers}")



# ---------------------------
# DLQ COMMANDS
# ---------------------------

@dlq_app.command("list")
def dlq_list():
    """List dead letter queue jobs."""
    jobs = list_dlq()

    table = Table(title="Dead Letter Queue")
    table.add_column("ID")
    table.add_column("Command")
    table.add_column("Attempts")
    table.add_column("Reason")
    table.add_column("Failed At")

    for j in jobs:
        table.add_row(
            j["id"],
            j["command"],
            str(j["attempts"]),
            j["reason"],
            j["failed_at"],
        )
    print(table)


@dlq_app.command("retry")
def dlq_retry(job_id: str):
    """Retry a DLQ job by moving it back to queue."""
    ok = retry_from_dlq(job_id)
    if ok:
        print(f"[green]Job {job_id} moved back to queue.[/green]")
    else:
        print(f"[red]Job {job_id} not found in DLQ.[/red]")


# ---------------------------
# CONFIG COMMANDS
# ---------------------------

@config_app.command("set")
def config_set(key: str, value: str):
    """Set a configuration value."""
    execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        (key, value),
    )
    print(f"[green]Config {key} set to {value}.[/green]")


@config_app.command("get")
def config_get(key: str):
    """Get a configuration value."""
    row = fetchone("SELECT value FROM config WHERE key=?", (key,))
    if row:
        print(f"{key} = {row['value']}")
    else:
        print(f"[yellow]Config {key} not found.[/yellow]")


# ---------------------------
# INIT
# ---------------------------

@app.command()
def init():
    """Initialize DB explicitly."""
    init_db()
    print("[green]Database initialized.[/green]")
