#!/usr/bin/env python3
"""Generate the extension icon: a permission grid of allow / ask / deny tiles.

Pure standard library, so the icon is reproducible without image packages.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZE = 512
BG = (16, 24, 38, 255)
COLORS = {
    "allow": (29, 111, 224, 255),
    "ask": (232, 163, 61, 255),
    "deny": (44, 52, 66, 255),
}
GRID = [
    ["allow", "allow", "ask"],
    ["allow", "ask", "deny"],
    ["ask", "deny", "deny"],
]


def rounded(x: float, y: float, left: float, top: float, side: float, radius: float) -> bool:
    if not (left <= x < left + side and top <= y < top + side):
        return False
    dx = max(left + radius - x, x - (left + side - radius), 0)
    dy = max(top + radius - y, y - (top + side - radius), 0)
    return dx * dx + dy * dy <= radius * radius


def build() -> bytes:
    tile, gap = 116, 26
    span = 3 * tile + 2 * gap
    origin = (SIZE - span) / 2
    rows = []
    for y in range(SIZE):
        row = bytearray([0])  # PNG filter type 0
        for x in range(SIZE):
            pixel = (0, 0, 0, 0)
            if rounded(x, y, 0, 0, SIZE, 112):
                pixel = BG
                for r, cells in enumerate(GRID):
                    for c, state in enumerate(cells):
                        left = origin + c * (tile + gap)
                        top = origin + r * (tile + gap)
                        if rounded(x, y, left, top, tile, 30):
                            pixel = COLORS[state]
            row += bytes(pixel)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "mcpb" / "icon.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build())
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
