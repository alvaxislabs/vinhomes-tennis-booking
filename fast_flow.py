"""Screenshot-driven booking flow. Never enables Android accessibility dumps."""
import logging
import re
import time


def normalized(value):
    return " ".join(value.casefold().replace("–", "-").split())


class SessionRestored(RuntimeError):
    """Navigation must restart after sign-in, without using old screen data."""


class VisualFlow:
    def __init__(self, device):
        self.device = device
        self.started = time.monotonic()
        self.boxes = []
        self.text = ""
        self.samples = 0

    def read(self):
        self.boxes = self.device.ocr_boxes()
        self.text = normalized(self.device.visual_text(self.boxes))
        if self.device.ensure_session_active(self.text, boxes=self.boxes):
            raise SessionRestored("Session restored; restarting from current app screen.")
        self.device.ensure_booking_hours(self.text)
        self.samples += 1
        return self.text

    def wait(self, predicate, stage, timeout=10):
        first_sample = len(getattr(self.device, "vision_timings", []))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.read()
            if predicate(self.text):
                logging.info("Fast flow +%.2fs: %s", time.monotonic()-self.started, stage)
                samples = getattr(self.device, "vision_timings", [])[first_sample:]
                logging.info("Stage %s: %d reads; capture %.3fs; recognition %.3fs; reader setup %.3fs",
                             stage, len(samples), sum(s["capture"] for s in samples),
                             sum(s["recognize"] for s in samples), sum(s["prepare"] for s in samples))
                return
        from booking import BookingError
        raise BookingError(f"Timed out at {stage}; no further taps sent.")

    def matches(self, label):
        return [b for b in self.boxes if normalized(b["text"]) == normalized(label)]

    def tap(self, label):
        from booking import BookingError
        boxes = self.matches(label)
        if len(boxes) != 1:
            raise BookingError(f"Expected one visible {label!r} control, found {len(boxes)}.")
        self.device.tap_box(boxes[0])

    def available_card(self, pattern):
        from booking import BookingError
        cards = [b for b in self.boxes if re.fullmatch(pattern, b["text"], re.I)]
        cards.sort(key=lambda b: -float(b["y"]))
        full = self.device.matching_boxes(self.boxes, "Hết chỗ", exact=False)
        for card in cards:
            # Badges are offset below court names, so associate with the nearest
            # card title rather than the whole page or an arbitrary ancestor.
            blocked = False
            for badge in full:
                by = float(badge["y"])+float(badge["height"])/2
                nearest = min(cards, key=lambda c: abs(by-(float(c["y"])+float(c["height"])/2)))
                if nearest is card:
                    blocked = True
            if not blocked:
                self.device.tap_box(card)
                return card["text"]
        raise BookingError("No available visible tennis card; stopped without guessing.")


def dismiss_hours_notice(device):
    from booking import BookingHoursClosed, Device
    boxes = device.ocr_boxes()
    try:
        Device.ensure_booking_hours(device.visual_text(boxes))
    except BookingHoursClosed:
        controls = [b for b in boxes if normalized(str(b["text"]))
                    in ("đóng", "đồng ý", "ok")]
        if len(controls) == 1:
            device.tap_box(controls[0])
        else:
            device.command("shell", "input", "keyevent", "4")


def run(device, *, dry_run=False, test_slot=None):
    from booking import BookingError, BookingHoursClosed, prepare_booking_window
    started = time.monotonic()
    deadline = started + 30
    device.submission_started = False
    device.release_snapshot = None
    recoveries = 0
    while True:
        try:
            return _run_once(device, dry_run=dry_run, test_slot=test_slot, started=started)
        except (BookingHoursClosed, SessionRestored) as exc:
            # Set before sending Confirm, including if the tap command times out.
            if device.submission_started:
                raise BookingError("Submission may have reached Vinhomes; no automatic retry. Check history.") from exc
            if time.monotonic() >= deadline:
                raise BookingError("Opening recovery window ended after 30 seconds; no reservation submitted.") from exc
            if isinstance(exc, SessionRestored):
                recoveries += 1
                if recoveries > 2:
                    raise BookingError("Repeated session resets; stopped before submission.") from exc
                logging.info("Session recovered at +%.2fs; rebuilding booking navigation.", time.monotonic()-started)
            else:
                logging.info("App still reports registration closed at +%.2fs; retrying before submission.", time.monotonic()-started)
                dismiss_hours_notice(device)
                time.sleep(min(.5, max(0, deadline-time.monotonic())))
            if not isinstance(exc, SessionRestored):
                prepare_booking_window(device)
            if time.monotonic() >= deadline:
                raise BookingError("Opening recovery window ended during preparation; no reservation submitted.")


def _run_once(device, *, dry_run=False, test_slot=None, started=None):
    from booking import BookingError, PACKAGE, SLOT_PREFERENCES, target_date
    if test_slot and not dry_run:
        raise BookingError("Test slots cannot submit reservations.")
    device.vision_timings = []
    flow = VisualFlow(device)
    if started is not None:
        flow.started = started
    device.verify()
    date = target_date()
    if device.foreground_package() != PACKAGE:
        device.command("shell", "monkey", "-p", PACKAGE, "1", timeout=8)
    flow.wait(lambda t: "trang chủ" in t or "danh sách tiện ích" in t or
              ("tháng" in t and "sân tennis" in t), "signed-in start")
    if "trang chủ" in flow.text:
        flow.tap("Tiện ích")
        flow.wait(lambda t: "danh sách tiện ích" in t and bool(flow.matches("Sân Tennis")), "amenities")
    if "danh sách tiện ích" in flow.text:
        flow.tap("Sân Tennis")
        flow.wait(lambda t: "tháng" in t and str(date.year) in t
                  and bool(flow.matches(str(date.day))), "calendar")
    if not re.search(rf"tháng\s+0?{date.month}\b", flow.text) or str(date.year) not in flow.text:
        raise BookingError("Target month/year is not visible; stopped before selecting a date.")
    days = [b for b in flow.matches(str(date.day))
            if .18 < 1-float(b["y"])-float(b["height"]) < .56]
    if len(days) != 1:
        raise BookingError("Target calendar day is not uniquely visible.")
    device.tap_box(days[0])
    flow.wait(lambda t: "khung giờ khả dụng" in t and "tiếp tục" in t, "target date")

    chosen = None
    for slot in ((test_slot,) if test_slot else SLOT_PREFERENCES):
        for _ in range(5):
            matches = flow.matches(slot)
            if matches:
                if not device.visual_is_full(matches[0], flow.boxes):
                    device.tap_box(matches[0])
                    chosen = slot
                break
            device.swipe_up()
            flow.read()
        if chosen:
            break
    if not chosen:
        raise BookingError("Requested time slots are full or unavailable.")
    logging.info("Fast flow: selected %s", chosen)
    # Continue is already located in the same screenshot. No screen dump:
    # enabling UiAutomation was observed resetting the app's selected time.
    flow.tap("Tiếp tục")
    flow.wait(lambda t: "chọn phân khu" in t or "chọn vị trí/dịch vụ" in t, "zones/courts")
    if "chọn phân khu" in flow.text:
        zone = flow.available_card(r"(?:BE|BS)\s*[_-]\s*Sân tennis")
        logging.info("Fast flow: zone %s", zone)
        flow.wait(lambda t: "chọn vị trí/dịch vụ" in t or
                  ("số lượng cư dân" in t and "tiếp tục" in t), "courts/details")
    court_pattern = r"[A-Z0-9]+\s*-\s*Sân tennis(?:\s+\d+)?"
    if "số lượng cư dân" in flow.text and "tiếp tục" in flow.text:
        courts = [b["text"] for b in flow.boxes if re.fullmatch(court_pattern, b["text"], re.I)]
        if len(courts) != 1:
            raise BookingError("Single-court details do not identify one tennis court.")
        court = courts[0]
    else:
        court = flow.available_card(court_pattern)
        flow.wait(lambda t: "số lượng cư dân" in t and "tiếp tục" in t, "court details")
    flow.tap("Tiếp tục")
    flow.wait(lambda t: "xác nhận đăng ký" in t and "thời gian đặt lịch" in t, "review")
    expected_date = date.strftime("%d/%m/%Y")
    if expected_date not in flow.text or normalized(chosen) not in flow.text or normalized(court) not in flow.text:
        raise BookingError("Review date, time or court differs from requested choice; submission blocked.")
    totals = flow.matches("Tổng tiền")
    amounts = [b for b in flow.boxes if re.fullmatch(r"[0O]\s+VND", b["text"], re.I)]
    # Vision reads this font's zero as O. Require a standalone zero amount
    # on the same row as Total, rather than relying on OCR reading order.
    if len(totals) != 1 or not any(
        float(b["x"]) > float(totals[0]["x"]) and
        abs(float(b["y"])-float(totals[0]["y"])) < .015 for b in amounts
    ):
        raise BookingError("Could not verify total price is 0 VND.")
    logging.info("FAST REVIEW VERIFIED: %s %s %s, %.2fs.",
                 expected_date, chosen, court, time.monotonic()-flow.started)
    if flow.matches("__terms_unchecked__"):
        flow.tap("__terms_unchecked__")
        flow.wait(lambda t: "__terms_checked__" in t, "terms accepted")
    if len(flow.matches("__terms_checked__")) != 1 or len(flow.matches("Xác nhận")) != 1:
        raise BookingError("Could not verify accepted terms and one confirmation button.")
    elapsed = time.monotonic()-flow.started
    if dry_run:
        logging.info("FAST READY TO SUBMIT: %.2fs, %d screenshots. Dry run; no reservation submitted.",
                     elapsed, flow.samples)
        return {"seconds": elapsed, "date": expected_date, "slot": chosen, "court": court}
    # Submit once only. An uncertain response must never trigger another tap.
    device.submission_started = True
    flow.tap("Xác nhận")
    logging.info("Confirmation tapped at +%.2fs; waiting for server result.", time.monotonic()-flow.started)
    try:
        flow.wait(lambda t: ("đăng ký thành công" in t or "đặt lịch thành công" in t or
                              ("đã đăng ký" in t and "mã đặt lịch" in t)),
                  "booking success", timeout=12)
    except BookingError as exc:
        raise BookingError("Confirmation was tapped once but success is unverified. "
                           "Check booking history before another attempt.") from exc
    elapsed = time.monotonic()-flow.started
    logging.info("FAST BOOKING CONFIRMED: %s %s %s, %.2fs.", expected_date, chosen, court, elapsed)
    return {"seconds": elapsed, "date": expected_date, "slot": chosen, "court": court}
