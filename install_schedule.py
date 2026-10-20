#!/usr/bin/env python3
"""Install the daily background scheduler for the current macOS user."""

import os
import plistlib
import shutil
import stat
import subprocess
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
RUNTIME = Path.home() / "Library/Application Support/VinhomesTennisBooking"
LABEL = "local.vinhomes.tennis-booking"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
LOGS = RUNTIME / "logs"


def main() -> None:
    python = subprocess.check_output(["/usr/bin/env", "python3", "-c", "import sys; print(sys.executable)"], text=True).strip()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    for name in ("booking.py", "fast_flow.py", "auth.py", "screen_ocr.swift", "vision_reader.py"):
        shutil.copy2(PROJECT / name, RUNTIME / name)
    local_env = PROJECT / ".env"
    if local_env.exists():
        shutil.copy2(local_env, RUNTIME / ".env")
        os.chmod(RUNTIME / ".env", stat.S_IRUSR | stat.S_IWUSR)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "Label": LABEL,
        # Keep macOS awake while waiting for 06:00. The display may sleep.
        "ProgramArguments": ["/usr/bin/caffeinate", "-i", python, str(RUNTIME / "booking.py"), "--watch"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(RUNTIME),
        "StandardOutPath": str(LOGS / "scheduler.out.log"),
        "StandardErrorPath": str(LOGS / "scheduler.err.log"),
        # Time-sensitive UI work must not receive background CPU/I/O throttling.
        "ProcessType": "Interactive",
    }
    with PLIST.open("wb") as out:
        plistlib.dump(config, out)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], check=False, capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST)], check=True)
    print(f"Installed and started daily scheduler: {PLIST}")
    print(f"Private runtime files and logs: {RUNTIME}")
    print("It preflights at 05:55 and starts booking at 06:00 Asia/Ho_Chi_Minh. Keep the Mac plugged in, logged in, and the emulator booted.")


if __name__ == "__main__":
    main()
