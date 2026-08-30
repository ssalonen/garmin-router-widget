#!/usr/bin/env python3
"""Find small green marker dots in a reference simulator screenshot.

Usage:
    python3 detect_green_dots.py <image.png>

Prints (x, y) cluster centres sorted top-to-bottom, left-to-right.
These are window-relative pixel coordinates suitable for xdotool.
"""

import subprocess
import sys
import re
from pathlib import Path


def find_green_clusters(img: Path,
                        min_green: int = 150,
                        max_red: int = 80,
                        max_blue: int = 80,
                        merge_radius: int = 15):
    # Image dimensions
    out = subprocess.run(
        ['convert', str(img), '-format', '%wx%h', 'info:'],
        capture_output=True,
    ).stdout
    m = re.match(rb'(\d+)x(\d+)', out)
    if not m:
        print('ERROR: could not read image dimensions', file=sys.stderr)
        return []
    w, h = int(m.group(1)), int(m.group(2))
    print(f'[dots] image {w}x{h}', file=sys.stderr)

    # Export to raw 8-bit RGB bytes
    raw = subprocess.run(
        ['convert', str(img), '-depth', '8', 'rgb:-'],
        capture_output=True,
    ).stdout
    expected = w * h * 3
    if len(raw) < expected:
        print(f'ERROR: got {len(raw)} bytes, expected {expected}', file=sys.stderr)
        return []

    # Collect qualifying green pixels
    green_pixels: list[tuple[int, int]] = []
    stride = w * 3
    for y in range(h):
        row = raw[y * stride:(y + 1) * stride]
        for x in range(w):
            r, g, b = row[x * 3], row[x * 3 + 1], row[x * 3 + 2]
            if g >= min_green and r <= max_red and b <= max_blue:
                green_pixels.append((x, y))

    print(f'[dots] {len(green_pixels)} qualifying green pixels', file=sys.stderr)
    if not green_pixels:
        return []

    # Greedy merge: build clusters by proximity
    clusters: list[list[tuple[int, int]]] = []
    for px, py in green_pixels:
        merged = False
        for cluster in clusters:
            cx = sum(p[0] for p in cluster) // len(cluster)
            cy = sum(p[1] for p in cluster) // len(cluster)
            if abs(px - cx) <= merge_radius and abs(py - cy) <= merge_radius:
                cluster.append((px, py))
                merged = True
                break
        if not merged:
            clusters.append([(px, py)])

    # Compute centres
    centres = []
    for cluster in clusters:
        cx = round(sum(p[0] for p in cluster) / len(cluster))
        cy = round(sum(p[1] for p in cluster) / len(cluster))
        centres.append((cx, cy, len(cluster)))

    # Sort top-to-bottom, then left-to-right
    centres.sort(key=lambda t: (t[1], t[0]))
    return centres


def main():
    if len(sys.argv) < 2:
        print('Usage: detect_green_dots.py <image.png>', file=sys.stderr)
        sys.exit(1)

    img = Path(sys.argv[1])
    if not img.exists():
        print(f'ERROR: {img} not found', file=sys.stderr)
        sys.exit(1)

    centres = find_green_clusters(img)
    if not centres:
        print('No green clusters found.')
        return

    print(f'\nFound {len(centres)} green marker(s):\n')
    print(f'  {"#":>2}  {"x":>5}  {"y":>5}  {"px":>5}')
    print(f'  {"--":>2}  {"---":>5}  {"---":>5}  {"--":>5}')
    for i, (x, y, n) in enumerate(centres, 1):
        print(f'  {i:>2}  {x:>5}  {y:>5}  {n:>5}')

    # Suggest UP/DOWN mapping (top-most = UP, bottom-most on same side = DOWN)
    print()
    if len(centres) >= 2:
        # Group by x side: left (x < image_mid) vs right
        out = subprocess.run(
            ['convert', str(img), '-format', '%wx%h', 'info:'],
            capture_output=True,
        ).stdout
        m = re.match(rb'(\d+)x(\d+)', out)
        mid_x = int(m.group(1)) // 2 if m else 200

        left  = [(x, y) for x, y, _ in centres if x < mid_x]
        right = [(x, y) for x, y, _ in centres if x >= mid_x]

        print('Left-side buttons:')
        for x, y in sorted(left, key=lambda p: p[1]):
            print(f'  ({x}, {y})')
        print('Right-side buttons:')
        for x, y in sorted(right, key=lambda p: p[1]):
            print(f'  ({x}, {y})')

        # For Edge 530: UP/DOWN are left-side buttons
        if len(left) >= 2:
            ul = sorted(left, key=lambda p: p[1])
            print(f'\nEdge 530 suggestion (UP/DN = left-side):')
            print(f'  SIM_UP_X={ul[0][0]}   SIM_UP_Y={ul[0][1]}')
            print(f'  SIM_DOWN_X={ul[-1][0]}  SIM_DOWN_Y={ul[-1][1]}')
        elif len(right) >= 2:
            ur = sorted(right, key=lambda p: p[1])
            print(f'\nSuggestion (UP/DN = right-side):')
            print(f'  SIM_UP_X={ur[0][0]}   SIM_UP_Y={ur[0][1]}')
            print(f'  SIM_DOWN_X={ur[-1][0]}  SIM_DOWN_Y={ur[-1][1]}')


if __name__ == '__main__':
    main()
