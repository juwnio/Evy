#!/usr/bin/env python3
"""One-time setup: create .venv, install requirements, install Playwright."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
VENV = ROOT / ".venv"
PYTHON = VENV / "bin" / "python"


def main():
    if not VENV.exists():
        print("Creating .venv...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)

    print("Installing requirements...")
    subprocess.run([str(PYTHON), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)

    print("Installing Playwright Chromium...")
    subprocess.run([str(PYTHON), "-m", "playwright", "install", "chromium"], check=True)

    print("Setup complete.")


if __name__ == "__main__":
    main()
