#!/usr/bin/env python3
"""Local UI automation for Vinhomes Resident tennis bookings on Android Emulator.

This drives only the visible app UI through Android Debug Bridge (adb).
It reads optional sign-in details from an ignored, permission-restricted .env file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
STATE_FILE = LOG_DIR / "last-run-date.txt"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PACKAGE = "com.vinhomes.resident"
OPENING_HOUR = 6
PREPARE_MINUTES_EARLY = 5
TARGET_DAYS_AHEAD = 2  # Monday opens Wednesday, as described by the resident.
SLOT_PREFERENCES = ("20:00 - 21:00", "19:00 - 20:00")
UI_DUMP = "/sdcard/vinhomes-window.xml"


class BookingError(RuntimeError):
    pass


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "booking.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def find_adb() -> str:
    from shutil import which

    adb = which("adb")
    if adb:
        return adb
    candidate = Path.home() / "Library/Android/sdk/platform-tools/adb"
    if candidate.exists():
        return str(candidate)
    raise BookingError("adb not found. Install Android Studio and its Platform Tools first.")


class Device:
    def __init__(self, adb: str, serial: str | None = None) -> None:
        self.adb = adb
        self.serial = serial
        self.parents: dict[ET.Element, ET.Element] = {}
        # UiAutomation activation resets this app's selected slot. Use screenshots.
        self.visual_only = True
        self.screen_size = None

    def command(self, *args: str, timeout: float = 12) -> str:
        cmd = [self.adb]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise BookingError(result.stderr.strip() or f"adb command failed: {args[0]}")
        return result.stdout.strip()

    def verify(self) -> None:
        devices = self.command("devices").splitlines()[1:]
        ready = [line.split()[0] for line in devices if line.strip().endswith("device")]
        if self.serial:
            if self.serial not in ready:
                raise BookingError(f"Emulator {self.serial} is not ready.")
        elif len(ready) != 1:
            raise BookingError("Expected one ready emulator; select one with --device if several are connected.")
        else:
            self.serial = ready[0]

    def foreground_package(self) -> str | None:
        output = self.command("shell", "dumpsys", "activity", "activities")
        match = __import__("re").search(
            r"(?:topResumedActivity|mResumedActivity)=.*?\bu\d+\s+([^/\s]+)/",
            output,
        )
        return match.group(1) if match else None

    def ui_tree(self) -> ET.Element:
        if self.visual_only:
            return ET.Element("hierarchy")
        try:
            # Compressed dumps are measurably faster on this emulator. The old
            # uncompressed 2s call timed out and permanently switched the run
            # to less reliable OCR taps.
            self.command("shell", "uiautomator", "dump", "--compressed", UI_DUMP, timeout=3)
            xml_text = self.command("exec-out", "cat", UI_DUMP, timeout=2)
            root = ET.fromstring(xml_text)
            self.parents = {child: parent for parent in root.iter() for child in parent}
            if not any(self.label(node) for node in root.iter()):
                logging.info("Android exposed no accessible text on this screen; using screenshot text once.")
            return root
        except subprocess.TimeoutExpired:
            logging.info("Android's accessibility dump timed out on this screen; falling back to screenshot text once.")
            return ET.Element("hierarchy")
        except ET.ParseError as exc:
            # The app can redraw a page while uiautomator is reading it. Treat
            # a partial XML snapshot like a transient miss and inspect the
            # screenshot instead of aborting the whole run.
            logging.info("Android returned a partial accessibility snapshot; falling back to screenshot text once: %s", exc)
            return ET.Element("hierarchy")

    def ocr_boxes(self) -> list[dict[str, object]]:
        """Read visible words and their screen positions using macOS Vision OCR."""
        source = ROOT / "screen_ocr.swift"
        if not source.exists():
            raise BookingError("The visual text reader is missing: screen_ocr.swift")
        swiftc = shutil.which("swiftc")
        if not swiftc:
            raise BookingError("This screen needs visual text reading, but Swift is unavailable. Install Apple's free Command Line Tools first.")
        cache = Path.home() / "Library/Caches/VinhomesTennisBooking"
        binary = cache / "screen-ocr"
        device_args = [self.adb]
        if self.serial:
            device_args += ["-s", self.serial]
        try:
            if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
                cache.mkdir(parents=True, exist_ok=True)
                built = subprocess.run([swiftc, "-O", str(source), "-o", str(binary)], capture_output=True, text=True, timeout=90)
                if built.returncode:
                    raise BookingError("Could not prepare the built-in macOS screen reader: " + built.stderr.strip()[-500:])
            # Capture the PNG directly over adb instead of writing it on-device
            # and then pulling it back (three adb calls instead of one).
            capture = subprocess.run(device_args + ["exec-out", "screencap", "-p"], capture_output=True, timeout=10)
            if capture.returncode or not capture.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
                raise BookingError("Could not capture a valid emulator screenshot for visual reading.")
            with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
                image_file.write(capture.stdout)
                image_file.flush()
                result = subprocess.run([str(binary), image_file.name], capture_output=True, text=True, timeout=12)
            if result.returncode:
                raise BookingError("Visual reading of the emulator screen failed: " + result.stderr.strip()[-500:])
            return json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise BookingError(f"Could not read visible text from the emulator screen: {exc}") from exc

    def tap_box(self, box: dict[str, object]) -> None:
        if self.screen_size is None:
            size = self.command("shell", "wm", "size")
            sizes = re.findall(r"(\d+)x(\d+)", size)
            if not sizes:
                raise BookingError("Could not determine the emulator screen size for a visual tap.")
            self.screen_size = tuple(map(int, sizes[-1]))
        width, height = self.screen_size
        x = round((float(box["x"]) + float(box["width"]) / 2) * width)
        y = round((1 - float(box["y"]) - float(box["height"]) / 2) * height)
        self.command("shell", "input", "tap", str(x), str(y))

    @staticmethod
    def visual_text(boxes: list[dict[str, object]]) -> str:
        return " ".join(str(box["text"]) for box in boxes)

    def read_screen_text(self, tree: ET.Element | None = None) -> str:
        # Empty ElementTree nodes are falsey. Use an explicit None check so a
        # timed-out dump does not trigger the same expensive dump a second time.
        if tree is None:
            tree = self.ui_tree()
        value = " ".join(self.label(node) for node in tree.iter())
        return value if value.strip() else self.visual_text(self.ocr_boxes())

    @staticmethod
    def matching_boxes(boxes: list[dict[str, object]], label: str, *, exact: bool = True) -> list[dict[str, object]]:
        needle = " ".join(label.casefold().split())
        found = []
        for box in boxes:
            value = " ".join(str(box["text"]).casefold().split())
            if value == needle if exact else needle in value:
                found.append(box)
        return found

    @staticmethod
    def visual_is_full(box: dict[str, object], boxes: list[dict[str, object]]) -> bool:
        x = float(box["x"]) + float(box["width"]) / 2
        y = float(box["y"]) + float(box["height"]) / 2
        # Availability badges sit near the next row's time label, so a broad
        # proximity radius alone can mark a free slot as full. Assign each
        # badge to the nearest visible time label before checking this slot.
        time_boxes = [
            item for item in boxes
            if re.search(r"\b\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\b", str(item["text"]))
        ]
        for marker in Device.matching_boxes(boxes, "Hết chỗ", exact=False):
            mx = float(marker["x"]) + float(marker["width"]) / 2
            my = float(marker["y"]) + float(marker["height"]) / 2
            nearby = [
                ( ((mx - (float(item["x"]) + float(item["width"]) / 2)) / 0.32) ** 2
                  + ((my - (float(item["y"]) + float(item["height"]) / 2)) / 0.08) ** 2,
                  item)
                for item in time_boxes
            ]
            if not nearby:
                continue
            nearest_score, nearest = min(nearby, key=lambda pair: pair[0])
            nx = float(nearest["x"]) + float(nearest["width"]) / 2
            ny = float(nearest["y"]) + float(nearest["height"]) / 2
            same_slot = abs(nx - x) < 0.015 and abs(ny - y) < 0.015
            if nearest_score < 2.0 and same_slot:
                return True
        return False

    def tap(self, node: ET.Element) -> None:
        target = node
        while target is not None and target.attrib.get("clickable") != "true":
            target = self.parents.get(target)
        if target is None:
            target = node
        bounds = target.attrib.get("bounds", "")
        try:
            left, top, right, bottom = map(int, __import__("re").findall(r"\d+", bounds))
        except ValueError as exc:
            raise BookingError("A visible control has no usable screen bounds.") from exc
        self.command("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))

    @staticmethod
    def label(node: ET.Element) -> str:
        return " ".join(x for x in (node.attrib.get("text", ""), node.attrib.get("content-desc", "")) if x).strip()

    def ensure_session_active(self, screen_text: str) -> None:
        """Restore a clearly expired login with local .env credentials, or stop safely."""
        normalized = screen_text.casefold()
        if "phiên đăng nhập" in normalized or "đăng nhập" in normalized or "login" in normalized:
            try:
                from auth import recover_session
                if recover_session(self, screen_text):
                    return
            except RuntimeError as exc:
                raise BookingError(str(exc)) from exc
            raise BookingError("Vinhomes displayed a sign-in/session-expired screen; no sign-in was attempted.")

    @staticmethod
    def ensure_booking_hours(screen_text: str) -> None:
        """Explain the app's tennis registration-hours notice instead of timing out."""
        normalized = " ".join(screen_text.casefold().split())
        normalized = normalized.replace("đ", "d")
        normalized = "".join(
            char for char in unicodedata.normalize("NFD", normalized)
            if unicodedata.category(char) != "Mn"
        )
        if "chi nhan dang ky" in normalized and "06:00" in normalized and "21:00" in normalized:
            raise BookingError(
                "Vinhomes is outside its tennis registration window (06:00–21:00 Vietnam time). "
                "The app showed its hours notice instead of opening the booking calendar."
            )

    def labeled_nodes(self, root: ET.Element, label: str, *, exact: bool = True) -> list[ET.Element]:
        found = []
        for node in root.iter():
            value = self.label(node)
            if value and (value == label if exact else label.casefold() in value.casefold()):
                found.append(node)
        return found

    def tap_label(self, label: str, *, exact: bool = True, timeout: float = 2) -> ET.Element:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            tree = self.ui_tree()
            screen_text = " ".join(self.label(node) for node in tree.iter())
            self.ensure_session_active(screen_text)
            if not screen_text.strip():
                boxes = self.ocr_boxes()
                visual_text = self.visual_text(boxes)
                self.ensure_session_active(visual_text)
                matches = self.matching_boxes(boxes, label) or self.matching_boxes(boxes, label, exact=exact)
                if matches:
                    self.tap_box(matches[0])
                    return ET.Element("node", {"text": str(matches[0]["text"])})
                raise BookingError(f"Android exposed no accessibility labels and the visible screen did not contain: {label}")
            nodes = [n for n in self.labeled_nodes(tree, label, exact=exact) if n.attrib.get("enabled", "true") == "true"]
            if nodes:
                self.tap(nodes[0])
                return nodes[0]
            time.sleep(0.08)
        raise BookingError(f"Could not find enabled control: {label}")

    def wait_for_text(
        self,
        labels: tuple[str, ...],
        timeout: float = 8,
        *,
        stage: str | None = None,
        require_all: bool = False,
        require_one_of: tuple[str, ...] = (),
        reject_other_sports: bool = False,
    ) -> str:
        end = time.monotonic() + timeout
        started = time.monotonic()
        screen_text = ""
        while time.monotonic() < end:
            tree = self.ui_tree()
            screen_text = " ".join(self.label(node) for node in tree.iter())
            if not screen_text.strip():
                boxes = self.ocr_boxes()
                screen_text = self.visual_text(boxes)
            try:
                self.ensure_session_active(screen_text)
                self.ensure_booking_hours(screen_text)
            except BookingError as exc:
                if stage:
                    raise BookingError(f"{exc} It appeared while waiting for: {stage}.") from exc
                raise
            normalized = screen_text.casefold()
            wrong_sports = ("sân bóng rổ", "sân bóng đá", "sân bóng chuyền", "sân cầu lông", "sân pickleball")
            if reject_other_sports and "sân tennis" in " ".join(labels).casefold() and any(sport in normalized for sport in wrong_sports):
                raise BookingError(f"Stopped safely: the screen is for another sport while waiting for {stage or 'the tennis screen'}.")
            labels_match = all(label.casefold() in normalized for label in labels) if require_all else any(label.casefold() in normalized for label in labels)
            alternative_match = not require_one_of or any(label.casefold() in normalized for label in require_one_of)
            if labels_match and alternative_match:
                if stage:
                    logging.info("Screen ready (%s): %.2fs", stage, time.monotonic() - started)
                return screen_text
            time.sleep(0.15)
        raise BookingError("The app did not reach the expected screen in time.")

    def tap_first_available(self, candidates: list[ET.Element], tree: ET.Element) -> ET.Element:
        parents: dict[ET.Element, ET.Element] = {}
        for parent in tree.iter():
            for child in parent:
                parents[child] = parent
        for node in candidates:
            if node.attrib.get("enabled", "true") != "true":
                continue
            # Availability belongs to one clickable card. Walking all the way
            # up the view tree can accidentally include a different full card
            # (or the entire page), and reject every available court.
            target = node
            while target.attrib.get("clickable") != "true" and target in parents:
                target = parents[target]
            card_text = " ".join(self.label(part) for part in target.iter()).casefold()
            if "hết chỗ" not in card_text:
                logging.info("Tapping available option %r at %s.", self.label(node), target.attrib.get("bounds", "unknown bounds"))
                self.tap(target)
                return node
        raise BookingError("No available court or preferred time slot was found.")

    def tap_first_available_visual(self, candidates: list[dict[str, object]], boxes: list[dict[str, object]]) -> dict[str, object]:
        for candidate in candidates:
            if not self.visual_is_full(candidate, boxes):
                self.tap_box(candidate)
                return candidate
        raise BookingError("Every matching visible option is marked Hết chỗ or none could be selected.")

    @staticmethod
    def visual_row_is_full(option: dict[str, object], boxes: list[dict[str, object]]) -> bool:
        """Associate a red Hết chỗ badge with a vertically stacked zone card."""
        y = float(option["y"]) + float(option["height"]) / 2
        return any(
            abs((float(marker["y"]) + float(marker["height"]) / 2) - y) < 0.035
            for marker in Device.matching_boxes(boxes, "Hết chỗ", exact=False)
        )

    def swipe_up(self) -> None:
        """Scroll the booking page to reveal controls below the current viewport."""
        size = self.command("shell", "wm", "size")
        sizes = re.findall(r"(\d+)x(\d+)", size)
        if not sizes:
            raise BookingError("Could not determine emulator screen size to scroll the slot list.")
        width, height = map(int, sizes[-1])
        x = width // 2
        self.command(
            "shell", "input", "swipe",
            str(x), str(int(height * 0.78)), str(x), str(int(height * 0.42)), "350",
        )


def target_date(now: dt.datetime | None = None) -> dt.date:
    now = now or dt.datetime.now(TZ)
    return now.astimezone(TZ).date() + dt.timedelta(days=TARGET_DAYS_AHEAD)


def prepare_booking_window(device: Device) -> None:
    """Verify the signed-in app and open Tiện ích before the 06:00 release."""
    device.verify()
    tree = device.ui_tree()
    screen_text = device.read_screen_text(tree)
    was_signed_out = any(marker in screen_text.casefold() for marker in ("phiên đăng nhập", "đăng nhập", "login"))
    device.ensure_session_active(screen_text)
    if was_signed_out:
        # Recovery navigates to the resident home page. Discard the old login
        # screen snapshot before deciding whether to continue into amenities.
        screen_text = device.read_screen_text()
    normalized = screen_text.casefold()
    if "danh sách tiện ích" in normalized and "sân tennis" in normalized:
        logging.info("Preflight passed: signed-in app is already on the amenities list.")
        return
    if "trang chủ" not in normalized:
        if device.foreground_package() != PACKAGE:
            device.command("shell", "monkey", "-p", PACKAGE, "1", timeout=8)
        for _ in range(5):
            tree = device.ui_tree()
            screen_text = device.read_screen_text(tree)
            device.ensure_session_active(screen_text)
            if "trang chủ" in screen_text.casefold():
                break
            device.command("shell", "input", "keyevent", "4")
            time.sleep(0.2)
        else:
            raise BookingError("Preflight could not return to the signed-in app home screen safely.")
    device.tap_label("Tiện ích", exact=False)
    device.wait_for_text(("Sân Tennis",), timeout=8, stage="preparing the tennis amenities list")
    logging.info("Preflight passed: signed-in app is on the amenities list; waiting for 06:00 to enter tennis.")


def check_session_to_tennis_calendar(device: Device) -> None:
    """Check the signed-in session through the tennis calendar without booking."""
    device.verify()
    tree = device.ui_tree()
    screen_text = device.read_screen_text(tree)
    was_signed_out = any(marker in screen_text.casefold() for marker in ("phiên đăng nhập", "đăng nhập", "login"))
    device.ensure_session_active(screen_text)
    if was_signed_out:
        # Recovery navigates to the resident home page. Discard the old login
        # screen snapshot before deciding whether to continue into amenities.
        screen_text = device.read_screen_text()
    normalized = screen_text.casefold()
    if "tháng" in normalized and "sân tennis" in normalized:
        logging.info("Session check passed: already on the tennis calendar; stopped without booking.")
        return
    if "trang chủ" not in normalized:
        raise BookingError("Session check stopped safely: leave Vinhomes on its signed-in home screen, then retry. The app was not relaunched.")

    if "danh sách tiện ích" not in normalized:
        device.tap_label("Tiện ích", exact=False)
        device.wait_for_text(("Sân Tennis",), timeout=8, stage="opening Tiện ích and locating Sân Tennis")
    device.tap_label("Sân Tennis", exact=False)
    device.wait_for_text(("Sân Tennis", "Tháng"), timeout=10, stage="opening the tennis booking calendar", require_all=True, reject_other_sports=True)
    logging.info("Session check passed: reached the tennis calendar. No date, time, court, or booking was selected.")


def run_booking(device: Device, *, dry_run: bool = False, test_slot: str | None = None) -> None:
    from fast_flow import run
    return run(device, dry_run=dry_run, test_slot=test_slot)


def _run_booking_legacy(device: Device, *, dry_run: bool = False, test_slot: str | None = None) -> None:
    device.verify()
    if test_slot and not dry_run:
        raise BookingError("--test-slot is only allowed together with --dry-run; it can never submit a booking.")
    started = time.monotonic()
    date_to_book = target_date()
    logging.info("Starting booking attempt for %s (Viet Nam time).", date_to_book.isoformat())

    # Reuse an authenticated app session. A visible username/password form can
    # be restored from .env; ambiguous forms and OTP challenges stop safely.
    # Bring the app forward without force-stopping it; force-stopping may invalidate
    # or disturb the resident's active session. If it resumes on an old screen,
    # return through the app's own back navigation to its home tab.
    tree = device.ui_tree()
    screen_text = device.read_screen_text(tree).casefold()
    if "phiên đăng nhập" in screen_text or "đăng nhập" in screen_text:
        raise BookingError("The resident session is signed out or expired. Sign in manually in the emulator, then retry.")
    amenities_ready = "danh sách tiện ích" in screen_text and "sân tennis" in screen_text
    calendar_ready = "tháng" in screen_text and "sân tennis" in screen_text
    if not ("trang chủ" in screen_text or amenities_ready or calendar_ready):
        if device.foreground_package() != PACKAGE:
            device.command("shell", "monkey", "-p", PACKAGE, "1", timeout=8)
    if not (amenities_ready or calendar_ready):
        # A review screen can be several pages deep (review, court detail,
        # courts, zone, time, then amenities); allow enough safe back steps.
        for _ in range(8):
            tree = device.ui_tree()
            screen_text = device.read_screen_text(tree).casefold()
            if "phiên đăng nhập" in screen_text or "đăng nhập" in screen_text:
                raise BookingError("The resident session is signed out or expired. Sign in manually in the emulator, then retry.")
            if "danh sách tiện ích" in screen_text and "sân tennis" in screen_text:
                amenities_ready = True
                break
            if "trang chủ" in screen_text:
                break
            device.command("shell", "input", "keyevent", "4")
            time.sleep(0.2)
        else:
            raise BookingError("Could not return to the app home screen safely.")
        if not amenities_ready:
            device.tap_label("Tiện ích", exact=False)
            device.wait_for_text(("Sân Tennis",), timeout=8, stage="opening Tiện ích and locating Sân Tennis")
    if not calendar_ready:
        # The app states tennis registration opens at 06:00. The watcher leaves
        # the amenities list open in advance and taps tennis at the release time.
        device.tap_label("Sân Tennis", exact=False)
    device.wait_for_text(("Sân Tennis", "Tháng"), timeout=10, stage="opening the tennis booking calendar", require_all=True, reject_other_sports=True)

    # Select the newly opened day. If the target is not visible in this month, stop
    # instead of risking a booking on a different date.
    tree = device.ui_tree()
    screen_text = device.read_screen_text(tree)
    day_suffix = f"{date_to_book.day} tháng {date_to_book.month}, {date_to_book.year}"
    day_nodes = [
        n for n in tree.iter()
        if Device.label(n).startswith(f"{date_to_book.day},")
        and day_suffix in Device.label(n)
        and n.attrib.get("enabled", "true") == "true"
    ]
    if day_nodes:
        device.tap(day_nodes[0])
    else:
        boxes = device.ocr_boxes()
        day_boxes = [
            box for box in boxes
            if str(box["text"]).strip() == str(date_to_book.day)
            and 0.18 < 1 - float(box["y"]) - float(box["height"]) < 0.56
        ]
        if not day_boxes:
            raise BookingError(f"Target day {date_to_book.isoformat()} is not visible/selectable in the calendar.")
        device.tap_box(day_boxes[0])
    device.wait_for_text(("Khung giờ khả dụng",), timeout=8, stage="loading available tennis times")

    chosen_slot = None
    slots_to_try = (test_slot,) if test_slot else SLOT_PREFERENCES
    for slot in slots_to_try:
        for _ in range(5):
            tree = device.ui_tree()
            candidates = device.labeled_nodes(tree, slot, exact=False)
            if candidates:
                try:
                    device.tap_first_available(candidates, tree)
                    chosen_slot = slot
                    break
                except BookingError as exc:
                    # Some app builds expose the time label but mark its
                    # accessibility node disabled even while the screen shows
                    # it as available. Re-check the visible availability before
                    # giving up; never tap a slot beside a Hết chỗ marker.
                    logging.info("Accessibility could not select %s (%s); checking the visible slot card.", slot, exc)
            boxes = device.ocr_boxes()
            visual_candidates = device.matching_boxes(boxes, slot, exact=False)
            if visual_candidates:
                try:
                    device.tap_first_available_visual(visual_candidates, boxes)
                    chosen_slot = slot
                    break
                except BookingError as exc:
                    logging.info("Visible slot check rejected %s: %s", slot, exc)
                    break
            device.swipe_up()
            time.sleep(0.15)
        if chosen_slot:
            break
    if not chosen_slot:
        if test_slot:
            raise BookingError(f"Test slot {test_slot} is full, hidden, or not selectable.")
        raise BookingError("Both preferred evening slots are full or unavailable.")
    logging.info("Selected slot: %s", chosen_slot)
    # Give the app a brief moment to commit its selected slot before moving
    # into the zone/court flow. Advancing immediately can leave the old time
    # in the booking state even though the new card looked selected.
    time.sleep(1.0)

    # The app asks for a court only after the date and time have been chosen.
    device.tap_label("Tiếp tục")
    screen_text = device.wait_for_text(
        ("Sân Tennis",), timeout=8, stage="loading the tennis court options",
        require_one_of=("Chọn phân khu", "BCX3 - Sân tennis", "CX2 - Sân tennis"),
        reject_other_sports=True,
    )
    if "chọn phân khu" in screen_text.casefold():
        tree = device.ui_tree()
        zones = [
            node for node in tree.iter()
            if re.search(r"\b(?:BE|BS)\s*[_-]\s*Sân tennis\b", Device.label(node), re.IGNORECASE)
        ]
        if zones:
            try:
                chosen_zone = Device.label(device.tap_first_available(zones, tree))
            except BookingError as exc:
                logging.info("Accessibility could not select an available tennis zone (%s); checking the visible cards.", exc)
                zones = []
        if not zones:
            boxes = device.ocr_boxes()
            visual_zones = [
                box for box in boxes
                if re.search(r"\b(?:BE|BS)\s*[_-]\s*Sân tennis\b", str(box["text"]), re.IGNORECASE)
            ]
            chosen_zone = ""
            for zone in visual_zones:
                if not Device.visual_row_is_full(zone, boxes):
                    device.tap_box(zone)
                    chosen_zone = str(zone["text"])
                    break
            if not chosen_zone:
                raise BookingError("Every tennis zone is marked Hết chỗ or none could be selected.")
        logging.info("Selected available tennis zone: %s", chosen_zone)
        device.wait_for_text(
            ("Sân Tennis",), timeout=25, stage="loading courts in the selected zone",
            require_one_of=("BCX3 - Sân tennis", "CX2 - Sân tennis"), reject_other_sports=True,
        )
    else:
        device.wait_for_text(
            ("Sân Tennis",), timeout=8, stage="loading the tennis court list",
            require_one_of=("BCX3 - Sân tennis", "CX2 - Sân tennis"), reject_other_sports=True,
        )
    tree = device.ui_tree()
    courts = [
        n for n in tree.iter()
        if "sân tennis" in Device.label(n).casefold() and " - " in Device.label(n)
    ]
    if courts:
        chosen_court = Device.label(device.tap_first_available(courts, tree))
    else:
        boxes = device.ocr_boxes()
        visual_courts = [
            box for box in boxes
            if "sân tennis" in str(box["text"]).casefold() and " - " in str(box["text"])
        ]
        chosen_box = device.tap_first_available_visual(visual_courts, boxes)
        chosen_court = str(chosen_box["text"])
    logging.info("Selected available court: %s", chosen_court)

    # Choosing a court opens a service-detail page that loads asynchronously.
    # Wait for its Continue control before trying to tap it.
    device.wait_for_text(("Tiếp tục",), timeout=20, stage="loading the selected court details")
    device.tap_label("Tiếp tục")
    review_text = device.wait_for_text(
        ("Xác nhận đăng ký", "Thông tin đăng ký"), timeout=8,
        stage="opening the booking review",
    )
    expected_review_date = date_to_book.strftime("%d/%m/%Y")
    if expected_review_date not in review_text or chosen_slot not in review_text:
        raise BookingError(
            "Safety check stopped at the review screen: the app shows a different date or time "
            f"than requested (expected {expected_review_date} {chosen_slot}). No booking was submitted."
        )
    if dry_run:
        logging.info(
            "Dry run: reached booking review and stopped before final confirmation. "
            "Elapsed time: %.2fs.", time.monotonic() - started,
        )
        return

    tree = device.ui_tree()

    # Accept the on-screen facility terms, as the resident explicitly requested.
    unchecked = [
        n for n in tree.iter()
        if n.attrib.get("checkable") == "true" and n.attrib.get("checked", "false") != "true"
    ]
    if unchecked:
        device.tap(unchecked[0])

    device.tap_label("Xác nhận")
    final_text = device.wait_for_text(("thành công", "đăng ký thành công", "lịch sử"), timeout=12)
    if not any(word in final_text.casefold() for word in ("thành công", "đăng ký thành công")):
        raise BookingError("Submission may have completed, but the app did not show a clear success message.")
    logging.info("Booking confirmed for %s, %s. Total local flow time: %.2f seconds.", date_to_book, chosen_slot, time.monotonic() - started)


def eligible_to_run(now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now(TZ)
    now = now.astimezone(TZ)
    if now.hour != OPENING_HOUR or now.minute != 0:
        return False
    date_key = now.date().isoformat()
    if STATE_FILE.exists() and STATE_FILE.read_text(encoding="utf-8").strip() == date_key:
        return False
    return True


def watch_until_booking_time(device_serial: str | None) -> None:
    """Preflight five minutes early, then start one attempt at 06:00 VNT."""
    device = Device(find_adb(), device_serial)
    logging.info("Booking scheduler is running; preflight is at 05:55 and booking starts at 06:00 Asia/Ho_Chi_Minh.")
    while True:
        now = dt.datetime.now(TZ)
        if eligible_to_run(now):
            # Record the attempt before doing UI work so a slow/failed run does not
            # cause a second submission if the scheduler is restarted that morning.
            STATE_FILE.write_text(now.date().isoformat(), encoding="utf-8")
            try:
                run_booking(device)
            except (BookingError, subprocess.SubprocessError, OSError) as exc:
                logging.error("Booking attempt stopped: %s", exc)
            continue
        target = now.replace(hour=OPENING_HOUR, minute=0, second=0, microsecond=0)
        if now >= target:
            target += dt.timedelta(days=1)
        preflight = target - dt.timedelta(minutes=PREPARE_MINUTES_EARLY)
        if now < preflight:
            time.sleep(max(0.1, min(30.0, (preflight - now).total_seconds())))
            continue

        # From 05:55 onward, verify the signed-in session and leave the app on the
        # amenities list. Do not tap tennis until the 06:00 release.
        try:
            prepare_booking_window(device)
        except (BookingError, subprocess.SubprocessError, OSError) as exc:
            logging.error("Preflight failed; will try the booking flow at 06:00: %s", exc)
        while dt.datetime.now(TZ) < target:
            time.sleep(min(0.2, max(0.05, (target - dt.datetime.now(TZ)).total_seconds())))
        now = dt.datetime.now(TZ)
        if eligible_to_run(now):
            STATE_FILE.write_text(now.date().isoformat(), encoding="utf-8")
            try:
                run_booking(device)
            except (BookingError, subprocess.SubprocessError, OSError) as exc:
                logging.error("Booking attempt stopped: %s", exc)


def run_next_opening_dry_run(device_serial: str | None) -> None:
    """Wait for the next 06:00 release, preflight at 05:55, and stop before confirmation."""
    device = Device(find_adb(), device_serial)
    now = dt.datetime.now(TZ)
    target = now.replace(hour=OPENING_HOUR, minute=0, second=0, microsecond=0)
    if now >= target:
        target += dt.timedelta(days=1)
    preflight = target - dt.timedelta(minutes=PREPARE_MINUTES_EARLY)
    logging.info(
        "One-time dry run scheduled: preflight %s; booking flow %s (Asia/Ho_Chi_Minh).",
        preflight.isoformat(), target.isoformat(),
    )
    while dt.datetime.now(TZ) < preflight:
        time.sleep(min(30.0, max(0.1, (preflight - dt.datetime.now(TZ)).total_seconds())))
    try:
        prepare_booking_window(device)
    except (BookingError, subprocess.SubprocessError, OSError) as exc:
        logging.error("Preflight failed; dry run will retry the app flow at 06:00: %s", exc)
    while dt.datetime.now(TZ) < target:
        time.sleep(min(0.2, max(0.05, (target - dt.datetime.now(TZ)).total_seconds())))
    try:
        run_booking(device, dry_run=True)
    except (BookingError, subprocess.SubprocessError, OSError) as exc:
        logging.error("One-time dry run stopped: %s", exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Book a Vinhomes tennis court through the Android app UI.")
    parser.add_argument("--device", help="adb device serial, if more than one emulator is connected")
    parser.add_argument("--check-session", action="store_true", help="open Tiện ích → Sân Tennis and stop at the calendar")
    parser.add_argument("--test-slot", choices=("09:00 - 10:00", "10:00 - 11:00", "11:00 - 12:00", "14:00 - 15:00"), help="choose a daytime slot for a dry run only; booking submission is disabled")
    parser.add_argument("--dry-run", action="store_true", help="navigate and select, but stop before final confirmation")
    parser.add_argument("--scheduled-check", action="store_true", help="run only during the 06:00 Viet Nam time minute")
    parser.add_argument("--watch", action="store_true", help="preflight at 05:55, then start once each day at 06:00 Viet Nam time")
    parser.add_argument("--dry-run-next-opening", action="store_true", help="wait for the next 06:00 release, run once in dry-run mode, and never confirm")
    args = parser.parse_args()
    configure_logging()
    if args.check_session:
        try:
            check_session_to_tennis_calendar(Device(find_adb(), args.device))
            return 0
        except (BookingError, subprocess.SubprocessError, OSError) as exc:
            logging.error("Session check stopped: %s", exc)
            return 1
    if args.dry_run_next_opening:
        try:
            run_next_opening_dry_run(args.device)
        finally:
            # This launch agent is intentionally one-shot; remove its file so a
            # later login cannot schedule another unattended dry run.
            dry_run_plist = Path.home() / "Library/LaunchAgents/local.vinhomes.tennis-booking-dry-run-once.plist"
            dry_run_plist.unlink(missing_ok=True)
        return 0
    if args.watch:
        try:
            watch_until_booking_time(args.device)
        except (BookingError, subprocess.SubprocessError, OSError) as exc:
            logging.error("Scheduler stopped: %s", exc)
            return 1
    if args.scheduled_check and not eligible_to_run():
        return 0

    try:
        run_booking(Device(find_adb(), args.device), dry_run=args.dry_run, test_slot=args.test_slot)
        if args.scheduled_check:
            STATE_FILE.write_text(dt.datetime.now(TZ).date().isoformat(), encoding="utf-8")
        return 0
    except (BookingError, subprocess.SubprocessError, OSError) as exc:
        logging.error("Booking attempt stopped: %s", exc)
        return 1


if __name__ == "__main__":
    sys.modules["booking"] = sys.modules[__name__]
    raise SystemExit(main())
