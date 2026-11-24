"""Draw Breaker's icon with the standard library only: python dev/make_icon.py"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZE = 256
SAMPLES = 3
BACK = (31, 36, 48)
BOLT = (245, 179, 1)
RADIUS = 56
POINTS = [(150, 22), (58, 146), (120, 146), (102, 234), (198, 106), (134, 106)]


def inside_bolt(x: float, y: float) -> bool:
    hit = False
    for (x1, y1), (x2, y2) in zip(POINTS, POINTS[1:] + POINTS[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def inside_back(x: float, y: float) -> bool:
    cx = min(max(x, RADIUS), SIZE - RADIUS)
    cy = min(max(y, RADIUS), SIZE - RADIUS)
    return (x - cx) ** 2 + (y - cy) ** 2 <= RADIUS**2


def pixel(px: int, py: int) -> bytes:
    back = bolt = 0
    for sx in range(SAMPLES):
        for sy in range(SAMPLES):
            x = px + (sx + 0.5) / SAMPLES
            y = py + (sy + 0.5) / SAMPLES
            if inside_back(x, y):
                back += 1
                if inside_bolt(x, y):
                    bolt += 1
    total = SAMPLES * SAMPLES
    if not back:
        return bytes((0, 0, 0, 0))
    mix = bolt / back
    colour = [round(BACK[i] + (BOLT[i] - BACK[i]) * mix) for i in range(3)]
    return bytes((*colour, round(255 * back / total)))


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def main() -> None:
    rows = b"".join(b"\x00" + b"".join(pixel(x, y) for x in range(SIZE)) for y in range(SIZE))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )
    target = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(png)
    print(f"wrote {target} ({len(png)} bytes)")


if __name__ == "__main__":
    main()
