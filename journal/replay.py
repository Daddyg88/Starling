"""
Demo mode: replays a pretend play session so you can see STARLING react
without Elite Dangerous running.
"""

import time
from pathlib import Path

from journal.status_reader import FLAG_LOW_FUEL, StatusReader

SAMPLE_FILE = Path(__file__).resolve().parent / "sample_journal.log"


def run_demo(processor, delay=0.6):
    """Feed the sample journal through the processor, one line at a time."""
    with open(SAMPLE_FILE, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                processor.handle_line(line)
                time.sleep(delay)

    # Pretend the game's Status.json changes while you fly.
    SHIP, SRV, ON_FOOT = 1 << 24, 1 << 26, 0
    status = StatusReader(None, processor, min_gap_seconds={})
    ticks = [0.0]

    def fake_clock():          # each step counts as 5 seconds, so "scooping complete" always shows
        ticks[0] += 5.0
        return ticks[0]
    status._clock = fake_clock

    steps = [
        {"Flags": SHIP},                                                  # in the main ship
        {"Flags": SHIP | (1 << 17)},                                      # frame shift drive charging
        {"Flags": SHIP | (1 << 4) | (1 << 6)},                            # supercruise + hardpoints: ignored
        {"Flags": SHIP | (1 << 2)},                                       # landing gear down
        {"Flags": SHIP | (1 << 6) | (1 << 28)},                           # gear up, hardpoints out, night vision
        {"Flags": SHIP | (1 << 6) | (1 << 28), "GuiFocus": 6},            # galaxy map opened
        {"Flags": SHIP | (1 << 6) | (1 << 28), "GuiFocus": 0},            # closed
        {"Flags": SHIP | (1 << 11), "Fuel": {"FuelMain": 20.0}},          # fuel scooping starts
        {"Flags": SHIP | (1 << 11), "Fuel": {"FuelMain": 32.0}},          # tank full: scooping complete
        {"Flags": SHIP, "Fuel": {"FuelMain": 32.0}},                      # you leave: scoop disengaged
        {"Flags": SHIP | (1 << 16)},                                      # mass locked
        {"Flags": SRV | (1 << 2)},                                        # into the SRV (gear flag ignored)
        {"Flags": SHIP},                                                  # back into the ship: "docking complete"
        {"Flags": 0, "Flags2": 1},                                        # on foot
        {"Flags": 0, "Flags2": 1 | (1 << 6)},                             # low oxygen
        {"Flags": SHIP | FLAG_LOW_FUEL, "Fuel": {"FuelMain": 6.4, "FuelReservoir": 0.5}},
        {"Flags": SHIP},
    ]
    for step in steps:
        status.handle_status(step)
        time.sleep(delay)
