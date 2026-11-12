"""RADAR TEST (0.96.2): an experiment, not a feature. Say "radar test" while you are on foot and she saves ONE small picture of
the radar in the top-left corner of the game window, plus your position and heading from Status.json, so we can find out whether
the radar's terminal icons can be read and turned into real positions.

What it saves (data/radar_tests/): the small radar crop (a few hundred pixels, nothing else of your screen) and one line in
data/radar_samples.json with the time, latitude, longitude, heading, planet radius, the settlement you are at (if known), the window
size and the crop box. Both go into the diagnostics zip. It never presses a key, never changes the map and never reads anything else.
It stops after MAX_SAMPLES pictures (send them to Benny, then clear the folder). Windows only (needs the game in a window or borderless).
"""
import json
import os
import re
from datetime import datetime

from core import paths
from core.logger import get_logger

log = get_logger("radar_test")

# the radar and its 'N' marker, as fractions of the game window (measured on a 1920x1080 screenshot: x 67..422, y 38..345)
RADAR_BOX = (0.035, 0.035, 0.220, 0.320)
MAX_SAMPLES = 60
_ASK = re.compile(r"^(?:radar test|test (?:the )?radar|radar snapshot|snapshot (?:the )?radar|scan (?:the )?radar|take (?:a )?radar (?:test|snapshot|picture))$")


def folder():
    return paths.DATA_DIR / "radar_tests"


def samples_path():
    return paths.DATA_DIR / "radar_samples.json"


def crop_box(width, height, fractions=RADAR_BOX):
    """(left, top, right, bottom) in pixels of a picture that is width x height."""
    left, top, right, bottom = fractions
    return (int(round(left * width)), int(round(top * height)), int(round(right * width)), int(round(bottom * height)))


class RadarTest:
    def __init__(self, state_provider, capture=None, out_folder=None, samples_file=None, settlement_name=None, stamp=None):
        self.state_provider = state_provider
        self.capture = capture
        self.out_folder = out_folder or folder()
        self.samples_file = samples_file or samples_path()
        self.settlement_name = settlement_name or (lambda: None)
        self.stamp = stamp or (lambda: datetime.now().strftime("%Y%m%d-%H%M%S"))

    # ---- the voice command ----
    def try_handle(self, text):
        said = re.sub(r"[^a-z ]", " ", str(text or "").lower())
        said = re.sub(r"\s+", " ", said).strip()
        if not _ASK.match(said):
            return None
        return self.take()

    def take(self):
        state = self.state_provider()
        if state is None or getattr(state, "latitude", None) is None:
            return "I do not have your position, so the radar test would be no use. Try it again when you are on foot on a planet."
        samples = self._samples()
        if len(samples) >= MAX_SAMPLES:
            return "I have already saved %d radar pictures. Please send them to Benny and clear the radar tests folder first." % MAX_SAMPLES
        capture = self.capture
        if capture is None:
            from control.panel_reader import capture_screen as capture
        picture = capture()
        if picture is None:
            return "I could not see the game window. Is the game in windowed or borderless mode?"
        height, width = picture.shape[0], picture.shape[1]
        box = crop_box(width, height)
        name = "radar-%s.png" % self.stamp()
        try:
            self.out_folder.mkdir(parents=True, exist_ok=True)
            from PIL import Image
            Image.fromarray(picture[box[1]:box[3], box[0]:box[2]]).save(str(self.out_folder / name))
        except Exception:
            log.exception("The radar picture could not be saved")
            return "I could not save the radar picture."
        samples.append({"file": name, "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "lat": getattr(state, "latitude", None), "lon": getattr(state, "longitude", None),
                        "heading": getattr(state, "heading", None), "radius": getattr(state, "planet_radius", None),
                        "on_foot": bool(getattr(state, "status_flags2", 0) & 1), "gui_focus": getattr(state, "gui_focus", None),
                        "settlement": self.settlement_name(), "window": [width, height], "crop": list(box)})
        self._save(samples)
        log.info("Radar test %d saved (%s)", len(samples), name)
        return "Radar picture %d saved." % len(samples)

    def _samples(self):
        try:
            with open(self.samples_file, encoding="utf-8") as handle:
                data = json.load(handle)
            return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, samples):
        temp = str(self.samples_file) + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(samples, handle, indent=1)
        os.replace(temp, str(self.samples_file))
