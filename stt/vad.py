"""
Works out when you START and STOP talking, using only loudness (no extra libraries).

It listens to the room, learns how loud the background is, and treats anything clearly
louder as speech. When it hears speech followed by about 0.7 seconds of quiet, it hands
back the whole sentence as one piece of audio.
"""

import numpy as np

RATE = 16000


class UtteranceDetector:
    def __init__(self, rate=RATE, frame_ms=30, end_silence_ms=700, min_speech_ms=300,
                 max_seconds=12.0, preroll_ms=300, min_level=0.01, margin=3.0, fixed_level=0.0):
        self.rate = rate
        self.frame_samples = int(rate * frame_ms / 1000)
        self.end_frames = max(1, int(end_silence_ms / frame_ms))
        self.min_speech_frames = max(1, int(min_speech_ms / frame_ms))
        self.max_frames = int(max_seconds * 1000 / frame_ms)
        self.preroll_frames = max(0, int(preroll_ms / frame_ms))
        self.min_level = min_level        # never treat anything quieter than this as speech
        self.margin = margin              # speech must be this many times louder than the background
        self.fixed_level = fixed_level    # >0 = use this exact level instead of learning it
        self.noise = min_level / 2.0
        self.calibration_frames = int(1000 / frame_ms)   # the first second just learns the room's hum
        self._seen = 0
        self._reset()
        self._preroll = []

    def _reset(self):
        self._frames = []
        self._speech_frames = 0
        self._silent = 0
        self._active = False

    @staticmethod
    def level(frame):
        return float(np.sqrt(np.mean(np.square(frame)))) if len(frame) else 0.0

    def threshold(self):
        if self.fixed_level > 0:
            return self.fixed_level
        return max(self.min_level, self.noise * self.margin)

    def feed(self, frame):
        """Give it one frame (frame_samples long). Returns a finished utterance or None."""
        frame = np.asarray(frame, dtype=np.float32)
        level = self.level(frame)
        self._seen += 1
        if self._seen <= self.calibration_frames and not self._active:
            self.noise = 0.9 * self.noise + 0.1 * level
            return None
        loud = level > self.threshold()

        if not self._active:
            if not loud:
                # Only learn the background from quiet moments.
                self.noise = 0.95 * self.noise + 0.05 * self.level(frame)
                self._preroll.append(frame)
                if len(self._preroll) > self.preroll_frames:
                    self._preroll.pop(0)
                return None
            self._active = True
            self._frames = list(self._preroll)
            self._preroll = []
            self._speech_frames = 0
            self._silent = 0

        self._frames.append(frame)
        if loud:
            self._speech_frames += 1
            self._silent = 0
        else:
            self._silent += 1

        done = self._silent >= self.end_frames or len(self._frames) >= self.max_frames
        if not done:
            return None
        utterance = None
        if len(self._frames) >= self.max_frames:
            # Sound that never stops is probably a fan or engine hum, not speech: learn it.
            levels = sorted(self.level(f) for f in self._frames)
            self.noise = max(self.noise, levels[len(levels) // 2] / self.margin * 1.2)
        if self._speech_frames >= self.min_speech_frames:
            utterance = np.concatenate(self._frames)
        self._reset()
        return utterance

    def reset(self):
        """Forget anything half-heard (used when STARLING herself starts talking)."""
        self._reset()
        self._preroll = []

    def flush(self):
        """
        Push-to-talk: the button was let go, so whatever was said so far is the sentence.
        Returns the audio (or None if it was just noise) and starts fresh.
        """
        utterance = None
        if self._active and self._speech_frames >= self.min_speech_frames:
            utterance = np.concatenate(self._frames)
        self._reset()
        self._preroll = []
        return utterance

    def learn_noise(self, frame):
        """Keep learning how loud the room is while the microphone button is not pressed."""
        level = self.level(np.asarray(frame, dtype=np.float32))
        if level <= self.threshold():
            self.noise = 0.95 * self.noise + 0.05 * level
