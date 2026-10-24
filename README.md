# Vinhomes Grand Park tennis booking helper

A local **macOS Python script** that operates Vinhomes Resident inside an Android
emulator. It reads screenshots and taps the app's visible controls. It does not
use a private booking API. No paid automation service or Python packages are required.

**Giving this to a friend's agent? Start with [AGENT_SETUP.md](AGENT_SETUP.md).**

## Latest real morning result

On **24 October 2026 at 06:00 Vietnam time**, the scheduled runner successfully
booked **BE7 – Sân tennis, 26 October 2026, 20:00–21:00**:

| Milestone from booking-flow start | Time |
| --- | ---: |
| Verified review | 8.17s |
| Confirm tapped once | 8.41s |
| Booking success detected | **10.29s** |

The two advance preparation checks failed to return to Home, but the 06:00 flow
recovered and completed. The log contains no login recovery during this run.
This is a successful unattended opening-time booking, **not proof of a guaranteed
under-10-second result**, nor a measurement of opening-time forced login.
A previous daytime booking completed in 8.46s. See [TEST_BOOKING.md](TEST_BOOKING.md).

## Booking rules — keep these defaults

- Community: **Vinhomes Grand Park, District 9**; the resident account determines access.
- Timezone: **Asia/Ho_Chi_Minh (UTC+7)**, independent of the Mac's display timezone.
- Prepare at **05:55**, recheck at **05:59:30**, start at **06:00** daily.
- Book **today + 2 calendar days**: Monday opens Wednesday.
- First choice **20:00–21:00**; fallback **19:00–20:00**.
- Any available tennis court, exactly one successful reservation per attempt.
- Verify the requested date, time, court, and **0 VND total** before confirming.
- Accept the displayed terms, tap Confirm once, then look for booking success.
- Never automatically cancel a booking. The account holder handles cancellation.

## Requirements

Verified on an Apple Silicon Mac with Android API 35, a Google Play emulator,
Python 3.9+, Apple's Swift compiler/Vision framework, and Android platform-tools.
Windows/Linux are not supported by this package's OCR or scheduling code.
Intel Macs have not been validated; use an architecture-compatible emulator image.

Check existing installations first. Missing tools should come from official sources:

- [Android Studio / Android SDK](https://developer.android.com/studio): free;
  SDK and emulator images require several GB in total.
- Apple Command Line Tools, including `swiftc` (install using Apple's macOS prompt
  from `xcode-select --install` if missing).
- Python **3.9 or newer**. The scripts use `zoneinfo`.
- [Vinhomes Resident on Google Play](https://play.google.com/store/apps/details?id=com.vinhomes.resident).

The app/package, Google Play sign-in, and any SDK license prompts require the
owner's own accounts and decisions. The package contains no Android image or APK.

## Setup

### 1. Get the project

```sh
git clone https://github.com/alvaxislabs/vinhomes-tennis-booking.git
cd vinhomes-tennis-booking
```

If GitHub denies access, the repository owner must grant access, or provide the
source ZIP. Extract it and open its folder. Do not request someone else's GitHub token.

Check tools:

```sh
python3 --version
swiftc --version
"$HOME/Library/Android/sdk/platform-tools/adb" devices
```

### 2. Prepare one emulator

In Android Studio: **More Actions → Virtual Device Manager → Create Device**.
Use a Google Play image compatible with the Mac; the tested setup was Pixel 9a,
API 35. Start it normally. **Do not use `-read-only`**, which may discard saved
app changes when the emulator closes. Keep exactly one Android device connected.

Install Vinhomes Resident through Google Play. Sign in and confirm the correct
Grand Park residence. Leave the app in Vietnamese, on Home.

Apply the tested display settings to the running emulator:

```sh
ADB="$HOME/Library/Android/sdk/platform-tools/adb"
"$ADB" shell wm size 720x1616
"$ADB" shell wm density 280
"$ADB" shell settings put global window_animation_scale 0
"$ADB" shell settings put global transition_animation_scale 0
"$ADB" shell settings put global animator_duration_scale 0
```

These only change the emulator. Record existing settings before applying them.
To return to device defaults, use `wm size reset`, `wm density reset`, and restore
the original animation settings (normally `1.0`).

### 3. Configure private login recovery

Create `.env` from `.env.example` **only if `.env` does not already exist**. The
owner fills in the two values locally:

```dotenv
VINHOMES_USERNAME=
VINHOMES_PASSWORD=
```

Then restrict access:

```sh
chmod 600 .env
```

Never upload `.env`, include it in a ZIP, print its values, or paste credentials
into agent chat. `.env.example` contains empty placeholders and is safe to share.
The scheduler installer copies `.env` to its private runtime folder with mode 600.
Rerun the installer after changing credentials or updating the source code.

### 4. Check without booking

With the app on Home:

```sh
python3 booking.py --check-session
python3 booking.py --dry-run
```

The first stops at the calendar. The second selects a date/time/court, verifies
the review, and stops **before Confirm**. Full slots can prevent the dry run from
reaching review; that does not prove setup failure or success. Do not replace it
with an unapproved live booking. A daytime dry run is also available:

```sh
python3 booking.py --dry-run --test-slot '11:00 - 12:00'
```

Allowed CLI test slots: 09:00–10:00, 10:00–11:00, 11:00–12:00, 14:00–15:00.
Test slots cannot submit reservations. Inspect the final screen, since dry runs
still change the app's navigation and selection.

Local recovery tests (no emulator interaction):

```sh
python3 -m unittest discover -s tests -v
```

With the owner's agreement, sign out once and run `--check-session` to verify
`.env` recovery, without making a booking. Do not clear app storage or reset the AVD.

### 5. Turn on daily booking

**This enables real daily bookings.** Once the owner authorizes that:

```sh
python3 install_schedule.py
```

The installer copies code and credentials into:
`~/Library/Application Support/VinhomesTennisBooking`

It registers `~/Library/LaunchAgents/local.vinhomes.tennis-booking.plist` and starts
one daily watcher. It uses `caffeinate` to prevent idle system sleep.

Check it:

```sh
launchctl print "gui/$(id -u)/local.vinhomes.tennis-booking"
"$HOME/Library/Android/sdk/platform-tools/adb" devices
tail -n 30 "$HOME/Library/Application Support/VinhomesTennisBooking/logs/booking.log"
```

Require a running scheduler and exactly one ready emulator. A running scheduler
alone is **not enough**. It does not start/restart the emulator automatically.

## Overnight checklist

- Mac plugged in, lid open, user logged in; do not shut it down or log out.
- Emulator open and connected; internet working.
- Leave Vinhomes on Home or the amenities list; avoid interacting during booking.
- Display sleep is fine. Closing the lid can suspend the Mac despite `caffeinate`.
- Only one automation controls the emulator. Do not run manual tests, a second
  watcher, or the optional scheduled dry run concurrently.

## Recovery and timing

At release, the script reads the **current** screen instead of trusting one taken
before 06:00. If the session expires, it can dismiss a recognized expiry dialog,
log in using `.env`, and rebuild navigation. It recognizes a saved-username login
layout for faster entry; other forms use accessibility inspection. OTP/CAPTCHA
or an ambiguous form require attention.

If the app says registration is closed, the runner dismisses the notice and
retries with a 0.5s pause during a 30s recovery window. After any Confirm attempt,
there is **no automatic retry**. An uncertain result must be checked in booking
history before considering another attempt.

Timing logs include login recovery that happens after booking starts. Emulator
boot and earlier preparation are separate. Actual forced-login tests varied;
under-10-second booking including forced login has not been verified.

## Results, stopping, and updates

- Main log: `~/Library/Application Support/VinhomesTennisBooking/logs/booking.log`
- Scheduler errors: same folder, `scheduler.err.log`.
- `FAST BOOKING CONFIRMED` means the script detected success.
- `Confirmation tapped ... success is unverified` means check app history;
  **do not assume failure and submit again**.
- The daily attempt date is recorded in `logs/last-run-date.txt` to prevent
  duplicate attempts after restarts. Do not delete it to force a rerun.

Stop daily booking:

```sh
python3 uninstall_schedule.py
```

This stops scheduling; it does not cancel existing court reservations. Runtime
files, including private credentials, remain local.

Update source with `git pull --ff-only`, then rerun `python3 install_schedule.py`
so the runtime actually receives the update. Do not reinstall during 05:55–06:01
or while a booking is in progress. Preserve `.env` and the attempt marker.

Optional next-opening dry run: stop the daily scheduler first, then run
`python3 install_dry_run.py`. Keep the Mac awake manually; this alternative does
not use the daily watcher's sleep prevention or copy `.env` into a fresh runtime.
Stop that one-time job using `python3 uninstall_dry_run.py` before re-enabling daily
booking. Never run both jobs together.

## Limits

The code is tied to observed Vietnamese app screens. UI changes, calendar layouts,
unavailable courts, account quotas, network delays, emulator exits, or session
challenges can stop a run. The morning test succeeded despite failed preflight
navigation; that preflight issue is not claimed fixed by this documentation update.
No speed or booking-success percentage is guaranteed.
