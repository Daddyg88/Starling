"""Finds out where her time goes, cheaply, so a slow or heavy moment can be explained from a log instead of guessed at.

JobTimer keeps a running total per named job (how many times, how long in all, the longest). Every ten minutes it writes one
INFO line with the busiest few and how much processor time she used, and it logs any single job that takes more than half a
second (at most once a minute per job) because those hold up everything behind them."""
import time

from core.logger import get_logger

log = get_logger("timing")

REPORT_EVERY = 600.0          # seconds between the summary lines
SLOW_SECONDS = 0.5            # one job slower than this is reported on its own
SLOW_REPEAT = 60.0            # ...but not more than once a minute for the same job
TOP = 5


class JobTimer:
    def __init__(self, clock=time.monotonic, cpu=time.process_time):
        self.clock = clock
        self.cpu = cpu
        self.jobs = {}                      # name -> [count, total seconds, longest]
        self._slow_said = {}
        self._period_start = clock()
        self._cpu_start = cpu()

    def record(self, name, seconds, detail=""):
        entry = self.jobs.setdefault(name, [0, 0.0, 0.0])
        entry[0] += 1
        entry[1] += seconds
        entry[2] = max(entry[2], seconds)
        now = self.clock()
        if seconds >= SLOW_SECONDS and now - self._slow_said.get(name, -SLOW_REPEAT) >= SLOW_REPEAT:
            self._slow_said[name] = now
            log.info("Slow job: %s took %.2f s%s", name, seconds, (" (%s)" % detail) if detail else "")
        if now - self._period_start >= REPORT_EVERY:
            self.report()

    def summary(self):
        """The busiest jobs this period as plain text, biggest total first."""
        ranked = sorted(self.jobs.items(), key=lambda item: item[1][1], reverse=True)[:TOP]
        return "; ".join("%s %d x, %.1f s in all, longest %.2f s" % (name, c, total, longest) for name, (c, total, longest) in ranked)

    def report(self):
        now = self.clock()
        elapsed = max(1.0, now - self._period_start)
        used = self.cpu() - self._cpu_start
        if self.jobs:
            log.info("Last %.0f min: she used %.1f s of processor time (%.1f%% of one core). Busiest jobs: %s",
                     elapsed / 60.0, used, 100.0 * used / elapsed, self.summary())
        else:
            log.info("Last %.0f min: she used %.1f s of processor time (%.1f%% of one core).", elapsed / 60.0, used, 100.0 * used / elapsed)
        self.jobs = {}
        self._period_start, self._cpu_start = now, self.cpu()
