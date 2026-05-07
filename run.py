"""Entrypoint — starts the FastAPI server and optionally the Streamlit UI."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Email Agent")
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Start the FastAPI server only (skip Streamlit).",
    )
    args = parser.parse_args()

    api_port = os.getenv("API_PORT", "8000")
    ui_port = os.getenv("UI_PORT", "8501")

    # Start the FastAPI server.
    api_cmd = [
        sys.executable, "-m", "uvicorn",
        "src.api.app:create_app",
        "--factory",
        "--host", "0.0.0.0",
        "--port", api_port,
        "--reload",
    ]
    print(f"Starting API server on http://localhost:{api_port}")
    api_proc = subprocess.Popen(api_cmd)

    ui_proc = None
    if not args.api_only:
        # Give uvicorn a moment to bind the port before Streamlit tries to reach it.
        time.sleep(2)

        ui_cmd = [
            sys.executable, "-m", "streamlit", "run",
            "ui/app.py",
            "--server.port", ui_port,
            "--server.headless", "true",
        ]
        print(f"Starting Streamlit UI on http://localhost:{ui_port}")
        ui_proc = subprocess.Popen(ui_cmd)

    try:
        api_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        api_proc.terminate()
        if ui_proc:
            ui_proc.terminate()


if __name__ == "__main__":
    main()
