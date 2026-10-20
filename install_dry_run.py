#!/usr/bin/env python3
"""Schedule one safe dry run for the next 06:00 opening."""

import os
import plistlib
import shutil
import subprocess
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
LABEL = "local.vinhomes.tennis-booking-dry-run-once"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
RUNTIME = Path.home() / "Library/Application Support/VinhomesTennisBooking"
LOGS = RUNTIME / "logs"


def main() -> None:
    python = subprocess.check_output(
        ["/usr/bin/env", "python3", "-c", "import sys; print(sys.executable)"],
        text=True,
    ).strip()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT / "booking.py", RUNTIME / "booking.py")
    shutil.copy2(PROJECT / "fast_flow.py", RUNTIME / "fast_flow.py")
    shutil.copy2(PROJECT / "auth.py", RUNTIME / "auth.py")
    shutil.copy2(PROJECT / "screen_ocr.swift", RUNTIME / "screen_ocr.swift")
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "Label": LABEL,
        "ProgramArguments": [python, str(RUNTIME / "booking.py"), "--dry-run-next-opening"],
        "RunAtLoad": True,
        "WorkingDirectory": str(RUNTIME),
        "StandardOutPath": str(LOGS / "dry-run.out.log"),
        "StandardErrorPath": str(LOGS / "dry-run.err.log"),
        "ProcessType": "Background",
    }
    with PLIST.open("wb") as out:
        plistlib.dump(config, out)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], check=False, capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST)], check=True)
    print(f"One-time dry run scheduled via {PLIST}")
    print("It preflights at 05:55 and runs at 06:00 Asia/Ho_Chi_Minh.")
    print("It stops before final confirmation. Keep the Mac awake and the emulator running.")
    print(f"Its local logs are in {LOGS}")


if __name__ == "__main__":
    main()
