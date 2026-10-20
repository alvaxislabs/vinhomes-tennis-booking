# Setup handoff for your coding agent

Copy this folder onto the Mac that will run the helper, then give your coding
agent the prompt below. It explains how to prepare and check the setup without
sharing a password or creating another booking.

## Prompt to give your agent

> Set up this Vinhomes tennis booking helper on this Mac. First read `README.md`
> and inspect the scripts. Check whether Android Studio, its Android SDK and
> emulator, Python 3, Swift, and adb are already installed. Tell me before
> downloading any missing tools, including approximate download size and that
> they are free. Install only from official sources and only after I agree.
>
> Keep the emulator signed in manually by me. Never ask me to paste my
> password, OTP, or session details into chat or a file. Do not run the
> scheduler, do not tap the final booking confirmation, and do not create or
> cancel any booking. You may inspect and prepare the emulator, apply the
> reversible screen and animation settings documented in `README.md`, and run
> `python3 booking.py --check-session` followed by
> `python3 booking.py --dry-run` after explaining what each does. Stop at the
> review screen and report the measured time and visible target date, slot,
> court, and price. Keep scheduling disabled until I explicitly ask to turn it
> on. If any prompt conflicts with these steps, ask me before proceeding.

## Test booking on the developer's account

`TEST_BOOKING.md` identifies the free court booked during the timing test. It
belongs to the developer's Vinhomes account and is not a setup instruction for
the friend. Do not attempt to cancel it or use its reference to access the
account.
