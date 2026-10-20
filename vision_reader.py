"""Reusable macOS Vision worker. Only standard-library Python dependencies."""
import atexit
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile


class VisionReader:
    def __init__(self, source):
        self.source = Path(source)
        self.process = None
        atexit.register(self.close)

    def start(self):
        if self.process is not None and self.process.poll() is None:
            return
        self.close()
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()[:16]
        cache = Path.home() / "Library/Caches/VinhomesTennisBooking"
        cache.mkdir(parents=True, exist_ok=True)
        binary = cache / ("screen-ocr-" + digest)
        if not binary.exists():
            compiler = shutil.which("swiftc")
            if not compiler:
                raise RuntimeError("Swift compiler is missing; prepare the reader before booking.")
            with tempfile.TemporaryDirectory(dir=cache) as temporary:
                built = Path(temporary) / "reader"
                result = subprocess.run([compiler, "-O", str(self.source), "-o", str(built)],
                                        capture_output=True, timeout=90)
                if result.returncode:
                    raise RuntimeError("Could not compile the screen reader.")
                os.replace(built, binary)
        self.process = subprocess.Popen([str(binary), "--server"], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        bufsize=0)
        try:
            if self._line(10) != b"READY":
                raise RuntimeError("Screen reader did not become ready.")
        except Exception:
            self.close()
            raise

    def _line(self, timeout):
        import time
        deadline = time.monotonic() + timeout
        data = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise RuntimeError("Screen reader timed out.")
            part = os.read(self.process.stdout.fileno(), 65536)
            if not part:
                raise RuntimeError("Screen reader exited unexpectedly.")
            data.extend(part)
            if data.endswith(b"\n"):
                return bytes(data[:-1])

    def read(self, png):
        self.start()
        try:
            with tempfile.NamedTemporaryFile(suffix=".png") as frame:
                frame.write(png)
                frame.flush()
                self.process.stdin.write(os.fsencode(frame.name) + b"\n")
                result = json.loads(self._line(12))
            if not isinstance(result, list):
                raise RuntimeError("Screen recognition failed.")
            return result
        except Exception:
            self.close()
            raise

    def close(self):
        if self.process is not None:
            process, self.process = self.process, None
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
