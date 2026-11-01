"""Regenerate docs/demo.gif from a real `fh run` session.

Usage: uv run --with pillow python scripts/make_demo_gif.py

The script runs the actual CLI in a pseudo-terminal against a throwaway project,
so the GIF always reflects the current output.
"""
from __future__ import annotations

import json
import os
import pty
import re
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "demo.gif"
FONT_CANDIDATES = [
    "/usr/share/fonts/adwaita-mono-fonts/AdwaitaMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
]
FONT_SIZE = 17
COLS, ROWS = 95, 27
PAD = 18
TITLE_H = 36
CAPTION_H = 44

BG, FG = (24, 26, 33), (214, 218, 228)
PALETTE = {
    None: FG,
    "dim": (122, 128, 146),
    "red": (242, 106, 118),
    "green": (126, 209, 124),
    "yellow": (235, 200, 110),
    "cyan": (102, 200, 224),
}
SGR = {"31": "red", "32": "green", "33": "yellow", "36": "cyan", "2": "dim"}
ANSI = re.compile(r"\x1b\[([0-9;]*)m")
OSC = re.compile(r"\x1b\][^\x07]*\x07")

OLD_SOURCE = "def add(a, b):\n    return a - b\n"
RESPONSE = {
    "version": 1,
    "tool_calls": [
        {"id": "call_001", "type": "function", "function": {"name": "read_file", "arguments": {"path": "calc.py"}}},
        {"id": "call_002", "type": "function", "function": {"name": "edit_file", "arguments": {"path": "calc.py", "old_text": "return a - b", "new_text": "return a + b"}}},
        {"id": "call_003", "type": "function", "function": {"name": "write_file", "arguments": {"path": "test_calc.py", "content": "from calc import add\n\nassert add(2, 3) == 5\nprint('ok')\n"}}},
        {"id": "call_004", "type": "function", "function": {"name": "run_command", "arguments": {"argv": ["python", "test_calc.py"]}}},
    ],
    "final_message": "Fixed add() and added a test.",
}


def capture_session() -> list[str]:
    """Run fh in a pty; return output chunks split after each approval prompt."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "calc.py").write_text(OLD_SOURCE, encoding="utf-8")
        (Path(tmp) / "response.json").write_text(json.dumps(RESPONSE), encoding="utf-8")
        master, slave = pty.openpty()
        env = {**os.environ, "TERM": "xterm-256color"}
        env.pop("NO_COLOR", None)
        proc = subprocess.Popen(
            [sys.executable, "-m", "free_hand.cli", "run", "--input", "response.json"],
            cwd=tmp, stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True,
        )
        os.close(slave)
        chunks, current = [], ""
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    data = os.read(master, 4096).decode("utf-8", "replace")
                except OSError:
                    break
                current += data.replace("\r\n", "\n")
                if current.endswith("[y/N] "):
                    chunks.append(current)
                    current = ""
                    os.write(master, b"y\n")
                    time.sleep(0.05)
            elif proc.poll() is not None:
                break
        proc.wait(timeout=5)
        os.close(master)
        chunks.append(current)
    cleaned = []
    for index, chunk in enumerate(chunks):
        chunk = OSC.sub("", chunk)
        if index:
            chunk = chunk.removeprefix("y\n")  # drop the pty echo; typing is animated
        cleaned.append(chunk)
    return cleaned


class Screen:
    def __init__(self) -> None:
        self.lines: list[list[tuple[str, str | None]]] = [[]]
        self.color: str | None = None

    def write(self, text: str) -> None:
        position = 0
        for match in ANSI.finditer(text):
            self._text(text[position:match.start()])
            codes = match.group(1).split(";")
            if match.group(1) in ("", "0"):
                self.color = None
            else:
                self.color = next((SGR[c] for c in codes if c in SGR), self.color)
            position = match.end()
        self._text(text[position:])

    def _text(self, text: str) -> None:
        for part in re.split(r"(\n)", text):
            if part == "\n":
                self.lines.append([])
            elif part:
                self.lines[-1].append((part, self.color))

    def snapshot(self):
        return [list(line) for line in self.lines[-ROWS:]]


def render(lines, caption: str, fonts) -> Image.Image:
    cell_w, cell_h = fonts["size"]
    width = COLS * cell_w + PAD * 2
    height = TITLE_H + ROWS * cell_h + PAD * 2 + CAPTION_H
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, TITLE_H], fill=(38, 41, 52))
    for i, color in enumerate([(242, 106, 118), (235, 200, 110), (126, 209, 124)]):
        draw.ellipse([14 + i * 22, 11, 26 + i * 22, 23], fill=color)
    draw.text((width // 2, TITLE_H // 2), "fh — Free-hand", font=fonts["font"], fill=PALETTE["dim"], anchor="mm")
    y = TITLE_H + PAD
    for line in lines:
        x = PAD
        for text, color in line:
            draw.text((x, y), text, font=fonts["font"], fill=PALETTE[color])
            x += cell_w * len(text)
        y += cell_h
    bar_top = height - CAPTION_H
    draw.rectangle([0, bar_top, width, height], fill=(38, 41, 52))
    draw.text((PAD, bar_top + CAPTION_H // 2), caption, font=fonts["font"], fill=PALETTE["cyan"], anchor="lm")
    return image


def load_fonts():
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            font = ImageFont.truetype(candidate, FONT_SIZE)
            return {"font": font, "size": (round(font.getlength("M")), FONT_SIZE + 7)}
    raise SystemExit("No monospace font found; edit FONT_CANDIDATES.")


def build_frames(chunks: list[str], fonts):
    screen = Screen()
    frames: list[tuple[Image.Image, int]] = []
    state = {"caption": ""}

    def emit(ms: int) -> None:
        frames.append((render(screen.snapshot(), state["caption"], fonts), ms))

    state["caption"] = "1. Paste the AI assistant's JSON response into fh"
    emit(900)
    screen.write("\x1b[36m$\x1b[0m ")
    for char in "fh run --input response.json":
        screen.write(char)
        emit(45)
    emit(400)
    screen.write("\n")

    captions = [
        "2. Review a diff-style preview of each edit",
        "2. New files are previewed too",
        "2. Commands are shown exactly as they will run",
        "3. Paste the results back into your AI chat",
    ]
    for index, chunk in enumerate(chunks):
        state["caption"] = captions[min(index, len(captions) - 1)]
        for line in chunk.split("\n"):
            screen.write(line + ("" if line.endswith("[y/N] ") else "\n"))
            emit(110)
        if chunk.endswith("[y/N] "):
            emit(1500)
            for char in "y\n":
                screen.write(char)
                emit(250)
    emit(3500)
    return frames


def main() -> None:
    fonts = load_fonts()
    frames = build_frames(capture_session(), fonts)
    OUTPUT.parent.mkdir(exist_ok=True)
    images = [image.quantize(colors=32, method=Image.Quantize.MEDIANCUT) for image, _ in frames]
    images[0].save(
        OUTPUT, save_all=True, append_images=images[1:],
        duration=[ms for _, ms in frames], loop=0, optimize=True, disposal=1,
    )
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size // 1024} KiB, {len(frames)} frames)")


if __name__ == "__main__":
    main()
