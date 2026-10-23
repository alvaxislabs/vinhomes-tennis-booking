"""Local .env loading and conservative recovery for a signed-out app session."""
from __future__ import annotations

import logging
import os
import shlex
import stat
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


def load_credentials() -> tuple[str, str] | None:
    """Read VINHOMES_USERNAME/PASSWORD locally; never log or return them to logs."""
    values = dict(os.environ)
    if ENV_FILE.exists():
        try:
            mode = stat.S_IMODE(ENV_FILE.stat().st_mode)
            if mode & 0o077:
                os.chmod(ENV_FILE, 0o600)
                logging.warning("Restricted .env permissions to this Mac user only.")
            for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].lstrip()
                key, sep, value = line.partition("=")
                if not sep:
                    continue
                value = value.strip()
                if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values.setdefault(key.strip(), value)
        except OSError as exc:
            logging.error("Could not read local .env file: %s", exc)
            return None
    username = values.get("VINHOMES_USERNAME", "").strip()
    password = values.get("VINHOMES_PASSWORD", "")
    return (username, password) if username and password else None


def _field_nodes(root: ET.Element) -> list[ET.Element]:
    return [n for n in root.iter()
            if "edittext" in n.attrib.get("class", "").casefold()
            and n.attrib.get("enabled", "true") == "true"]


def _submit_node(root: ET.Element) -> ET.Element | None:
    labels = ("đăng nhập", "login", "tiếp tục", "continue")
    for node in root.iter():
        label = " ".join((node.attrib.get("text", ""), node.attrib.get("content-desc", ""))).casefold()
        if label.strip() in labels and node.attrib.get("clickable") == "true":
            return node
    return None


def _input_text(device, value: str) -> None:
    # `input text` treats spaces as %s. Quote for the Android shell; do not put
    # the command or credential in an exception/log message.
    safe_value = value.replace(" ", "%s")
    try:
        result = subprocess.run(
            [device.adb] + (["-s", device.serial] if device.serial else []) +
            ["shell", "input", "text", shlex.quote(safe_value)],
            capture_output=True, timeout=8,
        )
        if result.returncode:
            raise RuntimeError("Android rejected text entry")
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        raise RuntimeError("Could not enter sign-in details into the Android screen") from exc


def recover_session(device, screen_text: str, *, boxes=None) -> bool:
    """Sign in only when the visible screen is clearly a username/password form."""
    started = time.monotonic()
    normalized = " ".join(screen_text.casefold().split())
    if not any(marker in normalized for marker in ("đăng nhập", "login", "phiên đăng nhập")):
        return False
    if any(marker in normalized for marker in ("otp", "captcha", "mã xác thực", "mã otp")):
        raise RuntimeError("The app requires OTP or a challenge; automatic sign-in stopped.")
    credentials = load_credentials()
    if not credentials:
        raise RuntimeError("Signed-out app session; add VINHOMES_USERNAME and VINHOMES_PASSWORD to the local .env file.")

    boxes = device.ocr_boxes() if boxes is None else boxes
    title = device.matching_boxes(boxes, "Đăng nhập tài khoản")
    saved_user = device.matching_boxes(boxes, credentials[0])
    phone_labels = device.matching_boxes(boxes, "Nhập số điện thoại")
    empty_password = [b for b in boxes
                      if str(b["text"]).casefold().strip().endswith("nhập mật khẩu")
                      and float(b["height"]) >= .017]
    # Only bypass the slow accessibility dump on this verified, empty-password
    # form with the correct saved username. Unknown layouts use the full path.
    fast_form = (len(title) == len(saved_user) == len(phone_labels) == len(empty_password) == 1
                 and 0 < float(phone_labels[0]["y"])-float(saved_user[0]["y"]) < .06
                 and float(title[0]["y"]) > float(phone_labels[0]["y"]) > float(empty_password[0]["y"]))
    if fast_form:
        device.tap_box(empty_password[0])
        _input_text(device, credentials[1])
        logging.info("Login +%.2fs: verified saved username and entered password visually", time.monotonic()-started)
    else:
        device.visual_only = False
        try:
            tree = device.ui_tree()
        finally:
            device.visual_only = True
        logging.info("Login +%.2fs: form inspected", time.monotonic()-started)
        fields = _field_nodes(tree)
        if len(fields) < 2 and "phiên đăng nhập" in normalized:
            # Expiry may first show a modal, before the username/password form.
            boxes = device.ocr_boxes()
            controls = [b for b in boxes if str(b["text"]).strip().casefold()
                        in ("đồng ý", "ok", "đăng nhập", "đăng nhập lại")]
            if len(controls) == 1:
                device.tap_box(controls[0])
                end = time.monotonic() + 5
                while time.monotonic() < end:
                    device.visual_only = False
                    try:
                        tree = device.ui_tree()
                    finally:
                        device.visual_only = True
                    fields = _field_nodes(tree)
                    if len(fields) >= 2:
                        break
                    time.sleep(.2)
        if len(fields) < 2:
            raise RuntimeError("Could not safely identify username and password fields; sign-in was not attempted.")
        password_fields = [n for n in fields if n.attrib.get("password", "false").casefold() == "true"]
        if len(password_fields) != 1:
            raise RuntimeError("Could not uniquely identify the password field; sign-in was not attempted.")
        password_field = password_fields[0]
        username_fields = [n for n in fields if n is not password_field]
        if len(username_fields) != 1:
            raise RuntimeError("Could not uniquely identify the username field; sign-in was not attempted.")

        # The real app does not expose an enabled submit button until fields are
        # filled. Locate and validate the exact button after entering credentials.
        device.tap(username_fields[0])
        device.command("shell", "input", "keyevent", "123", *(["67"] * max(1, len(username_fields[0].get("text", "")) + 1)))
        _input_text(device, credentials[0])
        logging.info("Login +%.2fs: username entered", time.monotonic()-started)
        device.tap(password_field)
        device.command("shell", "input", "keyevent", "123", *(["67"] * max(1, len(password_field.get("text", "")) + 1)))
        _input_text(device, credentials[1])
        logging.info("Login +%.2fs: password entered", time.monotonic()-started)
    # Hide the virtual keyboard so it cannot cover the login button.
    device.command("shell", "input", "keyevent", "4")
    # Allow the form to settle after the keyboard closes. The app can retain
    # stale accessibility bounds at this transition, so tap the exact visible
    # button label using current screenshot coordinates first.
    time.sleep(0.1)
    submit_boxes = device.matching_boxes(device.ocr_boxes(), "đăng nhập", exact=True)
    if len(submit_boxes) == 1:
        device.tap_box(submit_boxes[0])
    else:
        # Keep an accessibility fallback for app versions whose OCR omits the
        # button label while still exposing a fresh clickable node.
        device.visual_only = False
        try:
            refreshed_tree = device.ui_tree()
        finally:
            device.visual_only = True
        refreshed_submit = _submit_node(refreshed_tree)
        if refreshed_submit is None:
            raise RuntimeError("Could not locate the visible sign-in button; credentials were not submitted.")
        device.tap(refreshed_submit)

    logging.info("Login +%.2fs: submitted", time.monotonic()-started)
    end = time.monotonic() + 12
    while time.monotonic() < end:
        text = " ".join(device.visual_text(device.ocr_boxes()).casefold().split())
        if "đăng nhập thành công" in text or "login successful" in text:
            logging.info("Vinhomes session restored from local credentials in %.2fs.", time.monotonic()-started)
            return True
        if "trang chủ" in text or "danh sách tiện ích" in text:
            logging.info("Vinhomes session restored from local credentials in %.2fs.", time.monotonic()-started)
            return True
        if any(marker in text for marker in ("otp", "captcha", "mã xác thực", "mã otp")):
            raise RuntimeError("The app requested OTP or a challenge; automatic sign-in stopped.")
        time.sleep(.25)
    raise RuntimeError("Sign-in did not reach the resident home screen; check the app manually.")
