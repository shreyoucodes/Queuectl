# 🧰 QueueCTL — CLI-Based Background Job Queue System

A lightweight, production-grade background job queue built in Python, supporting concurrent workers, automatic retries with exponential backoff, and a persistent Dead Letter Queue (DLQ) — all controllable via a clean CLI interface.

---

## 🚀 1. Setup Instructions

### ✅ Prerequisites

- Python 3.10+
- pip
- (Optional) Linux / WSL for best shell compatibility

### 📦 Installation

Clone the repository and install dependencies locally:

```bash
git clone https://github.com/<your-username>/queuectl.git
cd queuectl
python -m venv .venv
source .venv/bin/activate        # (On Windows: .venv\Scripts\activate)
pip install -e .
```

Initialize the persistent SQLite database:

```bash
python -m queuectl.storage
```

You should see:

```
DB initialized at: /home/<user>/.queuectl/queue.db
```
If you are following up on a new terminal:

```bash
queuectl init
```

---

## 💻 2. Usage Examples

### 🧱 Enqueue a Job

```bash
queuectl enqueue '{"id":"job1","command":"echo hello"}'
```

**Output:**

```
Job job1 enqueued successfully.
```

### ⚙️ Start Worker(s)

Start 3 workers in parallel:

```bash
queuectl worker start --count 3
```

**Example output:**

```
[manager] Started worker 4321-12ab...
[worker ...] Processing job job1 : echo hello
hello
[worker ...] Job job1 completed successfully.
```

Gracefully stop all running workers:

```bash
queuectl worker stop
```

### 📊 Queue Status

View counts of all job states:

```bash
queuectl status
```

**Example:**

```
          Queue Status
┏━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┳━━━━━━┓
┃ Pending ┃ Processing ┃ Completed ┃ Failed ┃ Dead ┃
┡━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━╇━━━━━━┩
│ 0       │ 0          │ 3         │ 0      │ 1    │
└─────────┴────────────┴───────────┴────────┴──────┘
```

### 📜 List Jobs by State

```bash
queuectl list --state pending
```

### ⚰️ Dead Letter Queue (DLQ)

List failed jobs:

```bash
queuectl dlq list
```

Retry a DLQ job:

```bash
queuectl dlq retry job1
```

### ⚙️ Configuration Management

Update retry and backoff settings:

```bash
queuectl config set max-retries 5
queuectl config set backoff-base 2
```

---

## 🧩 3. Architecture Overview

### 🧱 Core Components

| Component | Description |
|-----------|-------------|
| CLI (Typer + Rich) | User interface for enqueuing jobs, managing workers, and viewing status. |
| Storage Layer (SQLite) | Persists jobs, states, retries, and DLQ across restarts. |
| Worker Processes | Independent background processes executing jobs concurrently. |
| Retry Mechanism | Automatic exponential backoff (delay = base ^ attempts). |
| Dead Letter Queue (DLQ) | Stores permanently failed jobs after max_retries exhaustion. |
| Config Manager | Allows runtime configuration of retry count and backoff base. |

### 🔁 Job Lifecycle

| State | Description |
|-------|-------------|
| `pending` | Waiting for worker to pick up |
| `processing` | Currently being executed |
| `completed` | Successfully executed |
| `failed` | Retryable failure (scheduled with backoff) |
| `dead` | Permanently failed (moved to DLQ) |

### 💾 Data Persistence

Jobs are stored in a local SQLite database:

```
~/.queuectl/queue.db
```

Ensures job state survives process or system restarts.

### ⚙️ Worker Logic

Each worker:

1. Atomically leases a job (UPDATE ... RETURNING)
2. Executes the command via `subprocess.run()`
3. Marks job as `completed` or `failed`
4. Retries failed jobs with exponential delay
5. Moves to DLQ after `max_retries`

Multiple workers run in parallel safely without duplicating jobs.

---

## ⚖️ 4. Assumptions & Trade-offs

### ✅ Design Decisions

- SQLite chosen for persistence — simple, reliable for a single-host queue.
- Typer + Rich for a clean, modern CLI interface.
- Multiprocessing for true parallelism without threading overhead.
- Atomic SQL leasing (UPDATE ... RETURNING) to prevent duplicate job claims.

### ⚠️ Simplifications

- No distributed coordination (single-machine only).
- Lease timeout hardcoded to 30s (could be made configurable).
- Job output logged to console only (no file logs).
- DLQ retry keeps same job ID (in production, might clone instead).

---

## 🧪 5. Testing Instructions

You can test all required scenarios directly from the terminal.

### ✅ Basic Job Success

```bash
queuectl enqueue '{"id":"test_success","command":"echo ok"}'
queuectl worker start --count 1
```

**Expected:**

```
ok
Job test_success completed successfully.
```

### ✅ Retry & DLQ Handling

```bash
queuectl enqueue '{"id":"fail1","command":"false"}'
queuectl worker start --count 1
```

**Expected:**

```
Job fail1 failed (exit=1). Retrying...
...
Job fail1 moved to Dead Letter Queue.
```

Then verify:

```bash
queuectl dlq list
```

### ✅ Persistence Check

Restart your terminal and run:

```bash
queuectl list --state completed
```

→ Your completed jobs should still be visible.

### ✅ Parallel Workers

```bash
queuectl enqueue '{"id":"p1","command":"sleep 2"}'
queuectl enqueue '{"id":"p2","command":"sleep 2"}'
queuectl enqueue '{"id":"p3","command":"sleep 2"}'

queuectl worker start --count 3
```

**Expected:**

- Each worker processes one job.
- No duplicate processing lines.

### ✅ Configuration

```bash
queuectl config set max-retries 5
queuectl config set backoff-base 3
queuectl config get
```

---

## 🏗️ Folder Structure

```
queuectl/
├── queuectl/
│   ├── __init__.py
│   ├── cli.py
│   ├── worker.py
│   ├── models.py
│   ├── storage.py
│   ├── config.py
│   ├── utils.py
├── tests/
│   ├── smoke_test.py
│   ├── full_test_suite.py
├── README.md
├── setup.py
```

---

## 🧾 Example Demo

🎥 Part 1: https://drive.google.com/file/d/1F8OiYFTTi3AOnVlWv8B8QFDW4w9OCN5d/view?usp=sharing
🎥 Part 2: https://drive.google.com/file/d/1KhryZPjs-2S2jqIlErcisekPAkF9sYXb/view?usp=sharing

---

## 🧠 Author

**Shreya Kiran**  
QueueCTL — Backend Developer Internship Assignment  
Built with ❤️ using Python + Typer + Rich
