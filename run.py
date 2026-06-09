"""Entrypoint — starts the FastAPI server and optionally the React UI dev server."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import platform
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Email Agent")
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Start the FastAPI server only (skip frontend).",
    )
    parser.add_argument(
        "--ui",
        choices=["react", "streamlit"],
        default="react",
        help="Which UI to start (default: react).",
    )
    args = parser.parse_args()

    api_port = os.getenv("API_PORT", "8000")

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
        time.sleep(2)

        if args.ui == "react":
            frontend_dir = PROJECT_ROOT / "frontend"
            ui_cmd = ["npm", "run", "dev"]
            print(f"Starting React UI (Vite dev server)")
            if platform.system() == "Windows":
                ui_proc = subprocess.Popen(
                    " ".join(ui_cmd),
                    cwd=frontend_dir,
                    shell=True
                )
            else:
                ui_proc = subprocess.Popen(ui_cmd, cwd=frontend_dir)
        else:
            ui_port = os.getenv("UI_PORT", "8501")
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
