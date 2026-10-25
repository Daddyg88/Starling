
# The mood engine's score is 5 times bigger since 0.42 (and each mood has 5 levels). Most tests were written for the old
# -100..100 numbers, so they run at scale 1. tests/test_mood_levels.py passes scale=5 itself.
from personality import mood_engine as _mood_engine   # noqa: E402
_mood_engine.SCALE_OVERRIDE = 1

# The old flavour tests check which remark pool a line came from, so the new mood-and-level asides and the extra Neutral
# remarks are switched off for them. tests/test_mood_levels.py tests the asides directly.
from personality import flavour as _flavour   # noqa: E402
_flavour.TONE_CHANCE = 0.0
_flavour.NEUTRAL_BOOST = 1.0
