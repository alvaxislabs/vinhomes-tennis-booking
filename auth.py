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
        if any(word in label for word in labels) and node.attrib.get("clickable") == "true":
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


def recover_session(device, screen_text: str) -> bool:
    """Sign in only when the visible screen is clearly a username/password form."""
    normalized = " ".join(screen_text.casefold().split())
    if not any(marker in normalized for marker in ("đăng nhập", "login", "phiên đăng nhập")):
        return False
    if any(marker in normalized for marker in ("otp", "captcha", "mã xác thực", "mã otp")):
        raise RuntimeError("The app requires OTP or a challenge; automatic sign-in stopped.")
    credentials = load_credentials()
    if not credentials:
        raise RuntimeError("Signed-out app session; add VINHOMES_USERNAME and VINHOMES_PASSWORD to the local .env file.")

    device.visual_only = False
    try:
        tree = device.ui_tree()
    finally:
        device.visual_only = True
    fields = _field_nodes(tree)
    if len(fields) < 2:
        raise RuntimeError("Could not safely identify username and password fields; sign-in was not attempted.")
    password_fields = [n for n in fields if n.attrib.get("password", "false").casefold() == "true"]
    if len(password_fields) != 1:
        raise RuntimeError("Could not uniquely identify the password field; sign-in was not attempted.")
    password_field = password_fields[0]
    username_fields = [n for n in fields if n is not password_field]
    if len(username_fields) != 1:
        raise RuntimeError("Could not uniquely identify the username field; sign-in was not attempted.")

    submit = _submit_node(tree)
    if submit is None:
        raise RuntimeError("Could not identify a sign-in button; sign-in details were not submitted.")

    device.tap(username_fields[0])
    _input_text(device, credentials[0])
    device.tap(password_field)
    _input_text(device, credentials[1])
    # Hide the virtual keyboard so it cannot cover the login button.
    device.command("shell", "input", "keyevent", "4")
    device.tap(submit)

    end = time.monotonic() + 12
    while time.monotonic() < end:
        text = " ".join(device.visual_text(device.ocr_boxes()).casefold().split())
        if "đăng nhập thành công" in text or "login successful" in text:
            logging.info("Vinhomes session restored from local credentials.")
            return True
        if "trang chủ" in text or "danh sách tiện ích" in text:
            logging.info("Vinhomes session restored from local credentials.")
            return True
        if any(marker in text for marker in ("otp", "captcha", "mã xác thực", "mã otp")):
            raise RuntimeError("The app requested OTP or a challenge; automatic sign-in stopped.")
        time.sleep(.25)
    raise RuntimeError("Sign-in did not reach the resident home screen; check the app manually.")
