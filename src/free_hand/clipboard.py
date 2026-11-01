"""Dependency-free clipboard support for local and remote terminals.

On Linux, clipboard reads try native desktop utilities and then an OSC 52
terminal query. Clipboard writes prefer OSC 52 when stdout is interactive.
Terminal support for OSC 52 reads varies and may be disabled for security.
"""
from __future__ import annotations

import base64
import os
import re
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path


class ClipboardError(RuntimeError):
    """Raised when clipboard access is unavailable or fails."""


OSC52_MAX_BYTES = 100_000


def _run(command: list[str], *, text: str | None = None) -> str:
    try:
        completed = subprocess.run(
            command,
            input=text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ClipboardError("Clipboard utility could not be started or timed out.") from exc
    if completed.returncode != 0:
        raise ClipboardError("Clipboard utility could not access the clipboard.")
    return completed.stdout


def _linux_command(candidates: list[tuple[str, list[str]]]) -> list[str] | None:
    for executable, args in candidates:
        resolved = shutil.which(executable)
        if resolved:
            return [resolved, *args]
    return None


def _wayland_socket_available() -> bool:
    # Wayland defaults to wayland-0 when WAYLAND_DISPLAY is not set.
    display = os.environ.get("WAYLAND_DISPLAY") or "wayland-0"
    if os.path.isabs(display):
        path = Path(display)
    else:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if not runtime_dir:
            return False
        path = Path(runtime_dir) / display
    return path.exists() and path.is_socket()


def _write_osc52(value: str) -> bool:
    """Ask the attached terminal emulator to set its local clipboard.

    Returns False when stdout is not an interactive terminal or the payload is
    too large. Terminal support varies, so callers must retain a file fallback.
    """
    payload = value.encode("utf-8")
    encoded = base64.b64encode(payload).decode("ascii")
    if len(payload) > OSC52_MAX_BYTES or not sys.stdout.isatty():
        return False
    # BEL terminator is widely supported by terminal emulators and multiplexers.
    sys.stdout.write(f"\033]52;c;{encoded}\007")
    sys.stdout.flush()
    return True



OSC52_READ_TIMEOUT = 1.5
OSC52_READ_MAX_BYTES = 1_000_000
_OSC52_RESPONSE = re.compile(rb"\x1b\]52;[cps];(.*?)\x07|\x1b\]52;[cps];(.*?)\x1b\\")


def _decode_osc52_response(data: bytes) -> str | None:
    """Decode a terminal OSC 52 clipboard reply, or return None if absent/denied."""
    match = _OSC52_RESPONSE.search(data)
    if not match:
        return None
    encoded = match.group(1) if match.group(1) is not None else match.group(2)
    if encoded == b"?":
        return None
    try:
        decoded = base64.b64decode(encoded, validate=True)
        return decoded.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def _read_osc52() -> str:
    """Request clipboard text from the attached terminal using OSC 52.

    This is supported by some terminal emulators, but many deliberately block
    clipboard reads. It requires an interactive controlling terminal.
    """
    if not sys.platform.startswith("linux"):
        raise ClipboardError("OSC 52 clipboard reading is only attempted on Linux.")

    try:
        fd = os.open("/dev/tty", os.O_RDWR | getattr(os, "O_NOCTTY", 0))
    except OSError as exc:
        raise ClipboardError("No interactive terminal is available for an OSC 52 clipboard request.") from exc

    original = None
    termios_module = None
    try:
        import termios as termios_module
        import tty
        if not os.isatty(fd):
            raise ClipboardError("No interactive terminal is available for an OSC 52 clipboard request.")
        original = termios_module.tcgetattr(fd)
        tty.setraw(fd, termios_module.TCSANOW)
        # BEL terminator is broadly understood. A terminal may answer with BEL
        # or ST; the decoder accepts both forms.
        request = b"\x1b]52;c;?\x07"
        if os.environ.get("TMUX"):
            # Ask tmux to pass the OSC sequence through to the outer terminal.
            request = b"\x1bPtmux;\x1b" + request.replace(b"\x1b", b"\x1b\x1b") + b"\x1b\\"
        os.write(fd, request)
        deadline = time.monotonic() + OSC52_READ_TIMEOUT
        received = bytearray()
        while len(received) < OSC52_READ_MAX_BYTES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable:
                break
            chunk = os.read(fd, min(4096, OSC52_READ_MAX_BYTES - len(received)))
            if not chunk:
                break
            received.extend(chunk)
            decoded = _decode_osc52_response(bytes(received))
            if decoded is not None:
                return decoded
            # A complete but denied/malformed reply is not going to improve.
            if b"\x07" in received or b"\x1b\\" in received:
                if b"\x1b]52;" in received:
                    break
        raise ClipboardError(
            "The terminal did not provide clipboard data (OSC 52 read may be disabled). "
            "Use a native clipboard backend or paste the response manually."
        )
    except OSError as exc:
        raise ClipboardError("Could not read the clipboard through the terminal (OSC 52).") from exc
    finally:
        if original is not None:
            try:
                termios_module.tcsetattr(fd, termios_module.TCSANOW, original)
            except OSError:
                pass
        os.close(fd)


def read_clipboard() -> str:
    """Read clipboard text from a native utility or the attached terminal."""
    platform = sys.platform
    if platform == "darwin":
        command = shutil.which("pbpaste")
        if command:
            return _run([command])
    elif platform == "win32":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell:
            return _run([powershell, "-NoProfile", "-Command", "Get-Clipboard -Raw"])
    elif platform.startswith("linux"):
        # WSL can access the Windows desktop clipboard through PowerShell even
        # when the Linux session has no X11 or Wayland clipboard server.
        if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
            powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
            if powershell:
                try:
                    return _run([powershell, "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"])
                except ClipboardError:
                    pass
        candidates: list[tuple[str, list[str]]] = []
        if _wayland_socket_available():
            candidates.append(("wl-paste", ["--no-newline"]))
        if os.environ.get("DISPLAY"):
            candidates.extend([
                ("xclip", ["-selection", "clipboard", "-o"]),
                ("xsel", ["--clipboard", "--output"]),
            ])
        errors: list[str] = []
        for executable, args in candidates:
            resolved = shutil.which(executable)
            if not resolved:
                continue
            try:
                return _run([resolved, *args])
            except ClipboardError as exc:
                errors.append(str(exc))
        # Native clipboard access is unavailable in many SSH/remote IDE
        # terminals. OSC 52 query lets a capable terminal return its clipboard.
        try:
            return _read_osc52()
        except ClipboardError as exc:
            errors.append(str(exc))
        detail = f" ({'; '.join(errors)})" if errors else ""
        raise ClipboardError(
            "Cannot read the system clipboard. No working native clipboard backend "
            "or terminal OSC 52 read support was available" + detail + "."
        )
    raise ClipboardError(
        "Cannot read the system clipboard on this platform. Use a supported clipboard utility."
    )


def write_clipboard(value: str) -> None:
    """Write text to the local clipboard using the best available backend."""
    platform = sys.platform
    if platform == "darwin":
        command = shutil.which("pbcopy")
        if command:
            _run([command], text=value)
            return
    elif platform == "win32":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell:
            _run(
                [powershell, "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
                text=value,
            )
            return
    elif platform.startswith("linux"):
        # OSC 52 targets the terminal user's clipboard and works over SSH when
        # the terminal emulator supports it. Do not require a local display.
        if _write_osc52(value):
            return

        candidates: list[tuple[str, list[str]]] = []
        if os.environ.get("DISPLAY"):
            candidates.extend([
                ("xclip", ["-selection", "clipboard", "-i"]),
                ("xsel", ["--clipboard", "--input"]),
            ])
        if _wayland_socket_available():
            candidates.append(("wl-copy", []))
        command = _linux_command(candidates)
        if command:
            _run(command, text=value)
            return
    raise ClipboardError(
        "No usable clipboard is available. Results were saved to .free-hand/last-results.json; "
        "open that file in your editor to copy them manually."
    )
