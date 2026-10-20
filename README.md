# Vinhomes tennis booking helper

This folder contains a local Mac helper for the Vinhomes Resident Android app.

## Speed improvements measured on 20 October 2026

The screenshot-based runner in `fast_flow.py` replaces Android accessibility
inspection. An isolated test showed that activating accessibility inspection
reset the selected time from 14:00 to 09:00. Screenshot reading preserves it.
The runner also reuses control locations from each screenshot, waits for actual
screen contents instead of fixed delays, and handles both BE and BS court flows.

Measured on the running Apple Silicon Mac emulator, already signed in:

| Start → end | Test route | Seconds |
| --- | --- | ---: |
| Home → verified review, original resolution | BE, 14:00–15:00 | 7.02 |
| Home → verified review and checked terms, original resolution | BE, 14:00–15:00 | 10.55 |
| Home → verified review and checked terms, 720×1616 | BE, 14:00–15:00 | 6.00 |
| Home → verified review and checked terms, 720×1616 | BS, 09:00–10:00 | 7.26 |

These no-submit tests reach checked terms from Home. In the authorized live
timing test, the helper tapped Confirm at 9.67 seconds. The app booked the court
and displayed booking reference **2449166**, but the success detector did not
recognize the app's booking-details page and waited its full 12-second limit.
The detector now recognizes that page. The exact server-confirmed end-to-end
time remains unmeasured, and the **5–10 second whole-booking target is not yet
verified**. The test booking details are in `TEST_BOOKING.md`; the resident
account holder plans to cancel it manually. Scheduling remains off.

### Emulator settings used for these measurements

The existing emulator was changed to 720×1616 at density 280, and its three
animation scales were set to zero. These are reversible emulator-only settings.
Original values are recorded locally in `logs/animation-settings-before.json`
and `logs/display-settings-before.txt`.

Start the AVD normally from Android Studio. Do not add the `-read-only` launch
option: the developer's test emulator used it, so app changes such as a saved
Vinhomes login may be discarded when that emulator is shut down. This can cause
a sign-in prompt after a full emulator restart; it does not explain an app
session expiring while the emulator stays running. The helper detects a login
screen and stops without submitting a booking. It does not preserve or renew the
Vinhomes session automatically.

To reproduce on a friend's emulator, with the emulator running:

```sh
ADB="$HOME/Library/Android/sdk/platform-tools/adb"
"$ADB" shell wm size 720x1616
"$ADB" shell wm density 280
"$ADB" shell settings put global window_animation_scale 0
"$ADB" shell settings put global transition_animation_scale 0
"$ADB" shell settings put global animator_duration_scale 0
```

To restore this emulator's original display settings:

```sh
ADB="$HOME/Library/Android/sdk/platform-tools/adb"
"$ADB" shell wm size reset
"$ADB" shell wm density reset
"$ADB" shell settings put global window_animation_scale 1.0
"$ADB" shell settings put global transition_animation_scale 1.0
"$ADB" shell settings delete global animator_duration_scale
```

Keep `booking.py`, `fast_flow.py`, and `screen_ocr.swift` together when copying
the helper. The native screen reader is compiled locally with the Mac's existing
Swift tools; its first compilation belongs in preflight, before the timed run.

## Intended booking rules

- Preflight at 05:55 Asia/Ho_Chi_Minh, then start booking at 06:00 for the date newly opened by the community.
- Choose any available tennis court.
- Try 20:00–21:00 first, then 19:00–20:00.
- Accept the displayed booking terms and submit the free booking.
- Verify the app's confirmation and write a local result log.
- Optimize the complete flow, including opening the app and navigating to Tiện ích → Sân Tennis, toward a five-second target. The app and booking server may make that target impossible on some runs.

## Sign-in recovery

The helper reuses the signed-in app session. If Vinhomes displays its login
screen, it can enter the account name and password from a local `.env` file.
It never writes credentials to logs or to GitHub. The `.env` file is ignored by
Git and restricted to the current Mac user when read. OTP and CAPTCHA screens
stop the run for manual attention.

1. Copy `.env.example` to `.env` in this folder.
2. Open `.env` in a text editor and fill `VINHOMES_USERNAME` and
   `VINHOMES_PASSWORD` with the resident account's login details.
3. Save the file. Do not upload or send `.env`; send only `.env.example` when
   sharing the project. If the daily scheduler is already installed, run
   `python3 install_schedule.py` again to copy the updated credentials into its
   private runtime folder.

Automatic recovery depends on the current Vinhomes login screen exposing one
username field, one password field, and a login/continue button to Android's
accessibility service. If its screen differs, the helper stops without
submitting a booking. Verify recovery during setup before relying on unattended
booking. Do not share these credentials with your coding agent.

## What this package is

This is a Python helper script, not a new phone app. It uses Android Debug Bridge (adb), included with Android Studio, to open and operate a virtual Android phone. It uses only visible app controls; it does not call undocumented booking endpoints or bypass app protections. Python and the script use free, built-in tools.

## Set it up on the Mac that will run it

1. Install Android Studio from [Google's official Android Studio page](https://developer.android.com/studio). The Studio download and emulator image are large (several GB total) but free. The Android SDK license must be accepted during setup.
2. In Android Studio, create one Android Virtual Device (AVD) with a Google Play system image. Start the virtual phone and complete its first-run setup.
3. Open Google Play inside the emulator, install **Vinhomes Resident** by Vingroup, and sign in to the resident account manually. Set up `.env` as described above if you want automatic recovery after session expiry.
4. With the emulator open and signed in on the app's home screen, first check that the session survives navigation to the tennis calendar:

   ```sh
   python3 booking.py --check-session
   ```

   This stops at the calendar without selecting a date or making a booking. Then run the no-submit walkthrough:

   ```sh
   python3 booking.py --dry-run
   ```

   This checks that the visible labels match the app and stops before the final booking confirmation. It still navigates to a court and selects a time, so run it when you are comfortable with that screen state.
5. If the walkthrough reaches the intended date and slot, install the daily scheduler:

   ```sh
   python3 install_schedule.py
   ```

   To stop it later:

   ```sh
   python3 uninstall_schedule.py
   ```

To schedule one safe dry run for the next 06:00 opening without waking up to launch it:

```sh
python3 install_dry_run.py
```

It preflights at 05:55, attempts the booking flow at 06:00, stops before final confirmation, logs its result, and removes its one-time schedule. Use `python3 uninstall_dry_run.py` to cancel it before it runs.

## Daily operation

- The scheduler preflights at **05:55** and starts booking at **06:00 Asia/Ho_Chi_Minh**, regardless of the Mac's displayed timezone.
- Keep the Mac logged in and connect it to power. The scheduler uses macOS `caffeinate` to prevent idle system sleep while it waits for 06:00; the display may sleep. Keep the Android emulator running.
- It aims to book the date two days ahead, choose the first available court, try 20:00–21:00 then 19:00–20:00, accept the facility terms, and confirm.
- Results are written under `~/Library/Application Support/VinhomesTennisBooking/logs/booking.log`. The log does not record account passwords or resident details.
- The five-second goal is measured from app launch through screen navigation and submission. It is a target only; app startup, the network, server response, and screen-label differences can make it take longer or fail.

## Current limitations

The fast flow has been verified through review on both BE and BS routes and has
completed one live free booking. Start it from Home, the amenities list, or the calendar;
preflight returns the app to the amenities list. A changed calendar month/layout,
expired session, unavailable courts, or ambiguous screen recognition stops the
attempt rather than guessing. Automatic login only handles a clearly exposed
username/password form; it has not yet been verified on an expired Vinhomes
session. OTP/CAPTCHA challenges and uncertain booking submissions stop without
retrying.
