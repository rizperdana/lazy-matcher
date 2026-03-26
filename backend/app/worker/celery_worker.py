"""Entry point for running Celery worker.

Usage:
    # Local
    cd backend && PYTHON_GIL=0 .venv/bin/celery -A app.core.celery worker --loglevel=info

    # Leapcell (persistent worker service)
    cd backend && PYTHON_GIL=0 .venv/bin/python -m app.worker.celery_worker
"""

import subprocess
import sys
import os


def main():
    """Launch Celery worker via CLI."""
    # Ensure we're in the backend directory
    backend_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    os.chdir(backend_dir)

    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.core.celery",
        "worker",
        "--loglevel=info",
        "--concurrency=2",
        "--without-heartbeat",
        "--without-mingle",
        "--without-gossip",
    ]

    print(f"Starting Celery worker: {' '.join(cmd)}")
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
