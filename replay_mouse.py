"""
Replay recorded mouse events from mouse_events.parquet.

Replays moves, clicks and scrolls at the exact same timing as they were recorded.
Press Ctrl+C anytime to abort.

Usage:
    uv run replay_mouse.py                  # replay at 1x speed
    uv run replay_mouse.py --speed 2.0      # replay at 2x speed
    uv run replay_mouse.py --no-clicks      # replay moves only (safety)
"""

import argparse
import time
from pathlib import Path

import pandas as pd
from pynput.mouse import Button, Controller

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Replay recorded mouse events.")
parser.add_argument(
    "--speed", type=float, default=1.0, help="Playback speed multiplier (default: 1.0)"
)
parser.add_argument(
    "--no-clicks", action="store_true", help="Skip click events (moves & scrolls only)"
)
parser.add_argument(
    "--file", type=str, default="mouse_events.parquet", help="Path to the parquet file"
)
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
parquet_path = Path(args.file)
if not parquet_path.is_absolute():
    parquet_path = Path(__file__).parent / parquet_path

df = pd.read_parquet(parquet_path)
df = df.sort_values("elapsed_s").reset_index(drop=True)

if args.no_clicks:
    df = df[df["event"] != "click"].reset_index(drop=True)

total = len(df)
duration = df["elapsed_s"].iloc[-1] / args.speed
print(f"Loaded {total:,} events  ({duration:.1f}s playback at {args.speed}x speed)")
print("Starting in …")
for i in range(3, 0, -1):
    print(f"  {i}", flush=True)
    time.sleep(1)
print("Go!\n")

# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------
BUTTON_MAP = {
    "Button.left": Button.left,
    "Button.right": Button.right,
    "Button.middle": Button.middle,
}

mouse = Controller()
event_start = time.perf_counter()
errors = 0

try:
    for i, row in df.iterrows():
        target_time = row["elapsed_s"] / args.speed
        wait = target_time - (time.perf_counter() - event_start)
        if wait > 0:
            time.sleep(wait)

        ev = row["event"]
        x, y = int(row["x"]), int(row["y"])

        try:
            if ev == "move":
                mouse.position = (x, y)

            elif ev == "click":
                btn = BUTTON_MAP.get(str(row["button"]), Button.left)
                mouse.position = (x, y)
                if row["pressed"]:
                    mouse.press(btn)
                else:
                    mouse.release(btn)

            elif ev == "scroll":
                dx = row["scroll_dx"]
                dy = row["scroll_dy"]
                if pd.notna(dx) and pd.notna(dy):
                    mouse.position = (x, y)
                    mouse.scroll(int(dx), int(dy))
                else:
                    print(
                        f"  [WARN] scroll row {i} has NaN dx/dy — skipped", flush=True
                    )

        except Exception as exc:
            errors += 1
            print(
                f"  [ERR] row {i} ({ev} @ {x},{y}): {type(exc).__name__}: {exc}",
                flush=True,
            )
            if errors >= 10:
                print("  Too many errors — aborting.", flush=True)
                break

        # Progress every 200 events
        if (i + 1) % 200 == 0 or i + 1 == total:
            elapsed_real = time.perf_counter() - event_start
            print(
                f"  [{i + 1:>{len(str(total))}}/{total}]  real {elapsed_real:.1f}s",
                flush=True,
            )

except KeyboardInterrupt:
    print("\nReplay aborted by Ctrl+C.")
except Exception as exc:
    print(f"\nReplay stopped unexpectedly: {type(exc).__name__}: {exc}")
    raise
else:
    print("\nReplay complete.")
