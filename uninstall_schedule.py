#!/usr/bin/env python3
"""Stop and remove this user's daily booking scheduler."""

import os
import subprocess
from pathlib import Path


LABEL = "local.vinhomes.tennis-booking"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def main() -> None:
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], check=False, capture_output=True)
    if PLIST.exists():
        PLIST.unlink()
    print("Daily booking scheduler stopped and removed.")


if __name__ == "__main__":
    main()
