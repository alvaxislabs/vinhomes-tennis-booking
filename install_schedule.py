#!/usr/bin/env python3
"""Install the daily background scheduler for the current macOS user."""

import os
import plistlib
import subprocess
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
LABEL = "local.vinhomes.tennis-booking"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
LOGS = PROJECT / "logs"


def main() -> None:
    python = subprocess.check_output(["/usr/bin/env", "python3", "-c", "import sys; print(sys.executable)"], text=True).strip()
    LOGS.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "Label": LABEL,
        # Keep macOS awake while waiting for 06:00. The display may sleep.
        "ProgramArguments": ["/usr/bin/caffeinate", "-i", python, str(PROJECT / "booking.py"), "--watch"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(PROJECT),
        "StandardOutPath": str(LOGS / "scheduler.out.log"),
        "StandardErrorPath": str(LOGS / "scheduler.err.log"),
        "ProcessType": "Background",
    }
    with PLIST.open("wb") as out:
        plistlib.dump(config, out)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], check=False, capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST)], check=True)
    print(f"Installed and started daily scheduler: {PLIST}")
    print("It preflights at 05:55 and starts booking at 06:00 Asia/Ho_Chi_Minh. Keep the Mac plugged in, logged in, and the emulator booted.")


if __name__ == "__main__":
    main()
