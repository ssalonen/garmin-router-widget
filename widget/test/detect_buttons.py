#!/usr/bin/env python3
"""Find Garmin Edge 530 simulator button positions from a full-window screenshot.

Algorithm
---------
1. Locate the device screen (the rectangle where Monkey C draws, always cleared
   to near-black) using ImageMagick threshold + trim.
2. Scan a 50-px-wide strip just outside the right edge of the screen.
   Buttons appear as lighter bumps in the otherwise-dark device frame, so we
   look for brightness peaks in per-row mean values.
3. Map the two outermost peaks to UP / DOWN.  Fall back to fixed fractions of
   the screen height if no peaks are found (e.g. when the frame area is too
   narrow or missing).

Outputs one shell variable assignment per line (source with eval "$(...)"):
  SIM_SCREEN_X=N  SIM_SCREEN_Y=N  SIM_SCREEN_W=N  SIM_SCREEN_H=N
  SIM_UP_X=N      SIM_UP_Y=N
  SIM_DOWN_X=N    SIM_DOWN_Y=N

Usage
-----
  python3 detect_buttons.py <full_window.png> [canvas_rx canvas_ry canvas_w canvas_h [annotate.png]]
"""

import subprocess
import sys
import re
from pathlib import Path


# ── ImageMagick helpers ───────────────────────────────────────────────────────

def _run(*args):
    r = subprocess.run(list(args), capture_output=True)
    return r.stdout, r.returncode


def img_size(img: Path):
    out, _ = _run('convert', str(img), '-format', '%wx%h', 'info:')
    m = re.match(rb'(\d+)x(\d+)', out)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def find_dark_rect(img: Path, threshold_pct: int = 8):
    """Return (x, y, w, h) bounding box of near-black pixels (= device screen).

    ImageMagick -threshold keeps pixels *below* the threshold as black, turns
    everything else white.  After -negate the dark region becomes white and we
    can -trim to its bounding box.
    """
    out, rc = _run(
        'convert', str(img),
        '-threshold', f'{threshold_pct}%',
        '-negate',
        '-trim',
        '-format', '%[fx:page.x] %[fx:page.y] %[fx:w] %[fx:h]',
        'info:',
    )
    if rc:
        return None
    parts = out.decode(errors='replace').split()
    if len(parts) < 4:
        return None
    try:
        x, y, w, h = (int(float(p)) for p in parts[:4])
        return x, y, w, h
    except ValueError:
        return None


def scan_strip_brightness(img: Path, strip_x: int, strip_y: int,
                           strip_w: int, strip_h: int):
    """Return per-row mean brightness [0..1] for a rectangular strip.

    Uses a single ImageMagick call that exports raw 8-bit grayscale bytes.
    """
    if strip_w <= 0 or strip_h <= 0:
        return []
    raw = subprocess.run(
        ['convert', str(img),
         '-crop', f'{strip_w}x{strip_h}+{strip_x}+{strip_y}', '+repage',
         '-colorspace', 'Gray', '-depth', '8', 'gray:-'],
        capture_output=True,
    ).stdout
    if len(raw) < strip_w * strip_h:
        return []
    return [
        sum(raw[r * strip_w:(r + 1) * strip_w]) / (strip_w * 255.0)
        for r in range(strip_h)
    ]


# ── Peak detection ────────────────────────────────────────────────────────────

def brightness_peaks(row_means, ratio: float = 0.40):
    """Return sorted list of row indices at brightness-run centres.

    A 'run' is a contiguous sequence of rows whose mean brightness is ≥
    ``ratio`` × the global maximum.  Each run's centre is one button.
    """
    if not row_means:
        return []
    peak = max(row_means)
    thr  = max(peak * ratio, 0.08)

    peaks, in_run, run_start = [], False, 0
    for i, b in enumerate(row_means):
        if b >= thr:
            if not in_run:
                run_start, in_run = i, True
        elif in_run:
            peaks.append((run_start + i) // 2)
            in_run = False
    if in_run:
        peaks.append((run_start + len(row_means)) // 2)
    return peaks


# ── Annotated diagnostic image ────────────────────────────────────────────────

def annotate_image(img: Path, out: Path,
                   sx, sy, sw, sh,
                   strip_x, strip_y, scan_w,
                   row_means, peaks,
                   btn_x, up_y, down_y,
                   iw, ih):
    """Write a copy of img to out with detection results drawn on it.

    Colours:
      Lime green rect  — detected device screen bounding box
      Yellow rect      — brightness scan strip
      Cyan tick marks  — raw brightness peaks in the scan strip
      Blue crosshair   — detected UP button click point
      Red  crosshair   — detected DOWN button click point
      Orange bar chart — per-row brightness profile (right side of image)
    """
    draw = []

    # Device screen bounding box
    draw += [
        '-strokewidth', '2', '-fill', 'none', '-stroke', '#00ff44',
        '-draw', f'rectangle {sx},{sy} {sx+sw-1},{sy+sh-1}',
    ]

    # Scan strip outline
    if scan_w > 0:
        draw += [
            '-strokewidth', '1', '-fill', '#ffff0022', '-stroke', '#ffff00',
            '-draw', f'rectangle {strip_x},{strip_y} {strip_x+scan_w},{strip_y+sh-1}',
        ]

    # Raw brightness peaks as cyan horizontal ticks across the strip
    for r in peaks:
        py = strip_y + r
        draw += [
            '-fill', '#00ffff', '-stroke', 'none',
            '-draw', f'rectangle {strip_x},{py-1} {strip_x+scan_w},{py+1}',
        ]

    # Brightness bar chart: rendered in a 60px column just right of the strip
    chart_x = min(strip_x + scan_w + 4, iw - 62)
    max_bar  = 56  # max bar width in px
    if row_means and chart_x + max_bar < iw:
        peak_val = max(row_means) if max(row_means) > 0 else 1.0
        for r, b in enumerate(row_means):
            py  = strip_y + r
            bar = int(b / peak_val * max_bar)
            if bar > 0:
                draw += [
                    '-fill', '#ff8800', '-stroke', 'none',
                    '-draw', f'rectangle {chart_x},{py} {chart_x+bar},{py}',
                ]

    # UP button — blue crosshair + circle
    R = 10
    ux, uy = btn_x, up_y
    draw += [
        '-strokewidth', '2', '-fill', 'none', '-stroke', '#4499ff',
        '-draw', f'circle {ux},{uy} {ux+R},{uy}',
        '-draw', f'line {ux-R},{uy} {ux+R},{uy}',
        '-draw', f'line {ux},{uy-R} {ux},{uy+R}',
    ]

    # DOWN button — red crosshair + circle
    dx, dy = btn_x, down_y
    draw += [
        '-strokewidth', '2', '-fill', 'none', '-stroke', '#ff4444',
        '-draw', f'circle {dx},{dy} {dx+R},{dy}',
        '-draw', f'line {dx-R},{dy} {dx+R},{dy}',
        '-draw', f'line {dx},{dy-R} {dx},{dy+R}',
    ]

    subprocess.run(
        ['convert', str(img)] + draw + [str(out)],
        capture_output=True,
    )
    print(f'[detect] annotated → {out}', file=sys.stderr)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print('Usage: detect_buttons.py <screenshot.png> [rx ry rw rh [annotate.png]]',
              file=sys.stderr)
        sys.exit(1)

    img = Path(sys.argv[1])
    if not img.exists():
        print(f'[detect] ERROR: {img} not found', file=sys.stderr)
        sys.exit(1)

    iw, ih = img_size(img)
    print(f'[detect] image {iw}x{ih}', file=sys.stderr)

    # Optional canvas geometry hint (from xdotool in e2e.sh)
    canvas = None
    if len(sys.argv) >= 6:
        try:
            canvas = tuple(int(sys.argv[i]) for i in range(2, 6))
            print(f'[detect] canvas hint: ({canvas[0]},{canvas[1]}) '
                  f'{canvas[2]}x{canvas[3]}', file=sys.stderr)
        except (ValueError, IndexError):
            pass

    # Optional annotated output path (7th argument)
    annotate_path = Path(sys.argv[6]) if len(sys.argv) >= 7 else None

    # ── 1. Find device screen bounds ──────────────────────────────────────────
    bounds = find_dark_rect(img)
    if bounds and bounds[2] > 40 and bounds[3] > 40:
        sx, sy, sw, sh = bounds
        print(f'[detect] screen by threshold: ({sx},{sy}) {sw}x{sh}',
              file=sys.stderr)
    elif canvas:
        sx, sy, sw, sh = canvas
        print('[detect] screen from canvas hint', file=sys.stderr)
    else:
        sx, sy, sw, sh = 0, 0, iw, ih
        print('[detect] screen fallback: full image', file=sys.stderr)

    # ── 2. Scan right-edge frame strip for button bumps ───────────────────────
    SCAN_W   = 50   # width of the strip to scan (px into frame)
    strip_x  = sx + sw + 1
    avail_w  = max(0, iw - strip_x - 1)
    scan_w   = min(SCAN_W, avail_w)

    row_means = scan_strip_brightness(img, strip_x, sy, scan_w, sh)
    peaks     = brightness_peaks(row_means)   # relative to sy
    abs_peaks = sorted(sy + r for r in peaks)

    btn_x = strip_x + scan_w // 2
    print(f'[detect] right-edge scan: x={strip_x}..{strip_x+scan_w}, '
          f'rows={len(row_means)}, peaks={peaks}', file=sys.stderr)

    # ── 3. Map peaks to UP / DOWN ─────────────────────────────────────────────
    if len(abs_peaks) >= 2:
        up_y, down_y = abs_peaks[0], abs_peaks[-1]
    elif len(abs_peaks) == 1:
        step   = max(sh // 5, 10)
        up_y   = max(sy,      abs_peaks[0] - step)
        down_y = min(sy + sh, abs_peaks[0] + step)
    else:
        # No bumps found — use fixed fractions; if no right-side frame exists,
        # fall back to the bottom area.
        if scan_w < 5:
            # Buttons must be below the screen
            btn_x  = sx + sw // 2
            below  = ih - sy - sh
            up_y   = sy + sh + max(5,  below // 3)
            down_y = sy + sh + max(10, below * 2 // 3)
            print('[detect] no right frame — trying below-screen defaults',
                  file=sys.stderr)
        else:
            up_y   = sy + sh * 25 // 100
            down_y = sy + sh * 60 // 100
            print('[detect] no bumps found — using default fractions',
                  file=sys.stderr)

    btn_x  = min(btn_x,  iw - 2)
    up_y   = max(0, min(up_y,   ih - 1))
    down_y = max(0, min(down_y, ih - 1))

    print(f'[detect] UP  ({btn_x},{up_y})', file=sys.stderr)
    print(f'[detect] DOWN ({btn_x},{down_y})', file=sys.stderr)

    # Output shell assignments
    for line in [
        f'SIM_SCREEN_X={sx}',
        f'SIM_SCREEN_Y={sy}',
        f'SIM_SCREEN_W={sw}',
        f'SIM_SCREEN_H={sh}',
        f'SIM_UP_X={btn_x}',
        f'SIM_UP_Y={up_y}',
        f'SIM_DOWN_X={btn_x}',
        f'SIM_DOWN_Y={down_y}',
    ]:
        print(line)

    # ── 4. Write annotated diagnostic image (optional) ────────────────────────
    if annotate_path:
        annotate_image(img, annotate_path,
                       sx, sy, sw, sh,
                       strip_x, sy, scan_w,
                       row_means, peaks,
                       btn_x, up_y, down_y,
                       iw, ih)


if __name__ == '__main__':
    main()
