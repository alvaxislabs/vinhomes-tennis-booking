#!/usr/bin/env python3
"""Stop and remove the one-time dry-run scheduler."""

import os
import subprocess
from pathlib import Path


LABEL = "local.vinhomes.tennis-booking-dry-run-once"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def main() -> None:
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], check=False, capture_output=True)
    PLIST.unlink(missing_ok=True)
    print("One-time dry-run scheduler stopped and removed.")


if __name__ == "__main__":
    main()
