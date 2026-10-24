# Agent setup handoff

Repository: https://github.com/alvaxislabs/vinhomes-tennis-booking

## Copy this message to your agent

> Set up this repository on my Mac so it can automatically book Vinhomes Grand
> Park tennis courts each morning. Read README.md and this file first. Preserve
> these rules: Vietnam time; prepare at 05:55; start at 06:00; book today + 2 days;
> 20:00–21:00 first, 19:00–20:00 second; any free tennis court; one confirmed
> reservation; no automatic cancellations. I authorize enabling this daily
> booking schedule after setup checks pass. Do not make an immediate live test
> booking unless I separately ask for one.
>
> Check my Mac architecture and existing Python 3.9+, Swift compiler, Android SDK,
> adb, and emulator before installing anything. Explain missing downloads, their
> source, approximate size and cost first. Use official free tools. The tested
> environment is Apple Silicon macOS with a Google Play API 35 emulator. Do not
> promise Windows/Linux compatibility or guaranteed sub-10-second bookings.
>
> Use one emulator, start it normally without -read-only, apply the documented
> display settings, and help me install Vinhomes Resident from Google Play. I will
> handle Google/resident account sign-ins and license prompts. Do not create new
> accounts, clear app storage, or reset an existing emulator without asking.
>
> Create .env from .env.example only if missing. Have me enter the resident
> username/password locally, set permissions to 600, and never print, upload,
> commit, or paste those values into chat. Preserve any existing .env. Never
> package an emulator image, saved login session, or private logs for sharing.
>
> Run the no-submit setup checks in README.md and inspect their results. Verify
> login recovery with me before relying on it overnight. If the requested slots
> are full, report that limitation; do not call an incomplete walkthrough a pass
> and do not make a real reservation to get around it. Install the daily schedule
> once the checks pass. If availability prevents a complete dry run, report what
> was verified and ask whether to arm the first scheduled attempt anyway.
>
> Ensure there is no competing daily or one-time dry-run job. After installing,
> verify the running scheduler, copied runtime code, private .env permissions,
> one connected emulator, current app session, and next run date/time in Vietnam.
> Report the target court date and preferences. Explain that the Mac must stay
> plugged in, lid open, logged in, with the emulator running. The script does not
> automatically boot the emulator. Show me where to check results and how to stop
> scheduling. Never delete the last-run marker or retry an uncertain submission.

## Agent completion checklist

Report each item as passed, blocked, or not checked:

1. Source revision and local project directory.
2. macOS/CPU architecture and compatible installed tools; no assumed paid services.
3. AVD name, Android version, exactly one connected device, tested display settings.
4. Vinhomes Resident installed, Vietnamese UI, correct Grand Park residence.
5. Private `.env` exists with values configured (report status only, never values).
6. Session check reaches Tennis calendar; dry run result and any availability limit.
7. Login recovery result, if tested; leave the emulator signed in afterward.
8. Exactly one intended scheduler, running after installation; no competing test job.
9. Next 05:55 preparation, 06:00 attempt, target date +2, preferred evening times.
10. Runtime log path, overnight requirements, and stop/update instructions explained.

## File map

- `booking.py`: device access, calendar rules, preflight, scheduler, CLI.
- `fast_flow.py`: visible booking flow, review validation, recovery, one submission.
- `auth.py`: private credentials and login recovery.
- `vision_reader.py`, `screen_ocr.swift`: local screenshot recognition.
- `install_schedule.py`, `uninstall_schedule.py`: daily job management.
- `install_dry_run.py`, `uninstall_dry_run.py`: optional next-opening no-submit job.
- `.env.example`: empty credential template; real `.env` is never included.
- `tests/test_recovery.py`: automated recovery tests, no real booking.
- `TEST_BOOKING.md`: historical results, not instructions to access or cancel bookings.

## Evidence and expectations

The real 24 October opening-time run booked BE7, 26 October, 20:00–21:00 in
**10.29 seconds**. Confirm was tapped at 8.41s. That run did not require login
recovery. Do not advertise 10.29s as a guarantee or say forced-login booking has
been verified under ten seconds. Keep the court/time references: this project
is intentionally configured for this resident's Grand Park tennis use case.
