"""Finds out where her time goes, cheaply, so a slow or heavy moment can be explained from a log instead of guessed at.

JobTimer keeps a running total per named job (how many times, how long in all, the longest). Every ten minutes it writes one
INFO line with the busiest few and how much processor time she used, and it logs any single job that takes more than half a
second (at most once a minute per job) because those hold up everything behind them."""
import time

import sys

from core.logger import get_logger

log = get_logger("timing")

REPORT_EVERY = 600.0          # seconds between the summary lines
SLOW_SECONDS = 0.5            # one job slower than this is reported on its own
SLOW_REPEAT = 60.0            # ...but not more than once a minute for the same job
TOP = 5


def thread_cpu_times():
    """CPU seconds used so far by EVERY thread of this program, including ones started by libraries (Windows only).
    Returns {thread id: seconds}; empty anywhere else or if Windows will not say."""
    if sys.platform != "win32":
        return {}
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.OpenThread.restype = wintypes.HANDLE

        class Entry(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("tid", wintypes.DWORD),
                        ("owner", wintypes.DWORD), ("base", wintypes.LONG), ("delta", wintypes.LONG), ("flags", wintypes.DWORD)]
        snap = k32.CreateToolhelp32Snapshot(0x4, 0)                     # TH32CS_SNAPTHREAD
        if not snap or snap == wintypes.HANDLE(-1).value:
            return {}
        out = {}
        try:
            entry = Entry()
            entry.size = ctypes.sizeof(Entry)
            pid = k32.GetCurrentProcessId()
            ok = k32.Thread32First(snap, ctypes.byref(entry))
            while ok:
                if entry.owner == pid:
                    handle = k32.OpenThread(0x0800, False, entry.tid)   # THREAD_QUERY_LIMITED_INFORMATION
                    if handle:
                        c, e, kern, user = (wintypes.FILETIME() for _ in range(4))
                        if k32.GetThreadTimes(handle, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kern), ctypes.byref(user)):
                            def ticks(t):
                                return (t.dwHighDateTime << 32 | t.dwLowDateTime) / 1e7
                            out[entry.tid] = ticks(kern) + ticks(user)
                        k32.CloseHandle(handle)
                ok = k32.Thread32Next(snap, ctypes.byref(entry))
        finally:
            k32.CloseHandle(snap)
        return out
    except Exception:
        return {}


def thread_owner(tid):
    """Which program file a thread started in, e.g. 'ctranslate2.dll' or 'onnxruntime.dll' (Windows only; '' when Windows will not say).
    Used only to put a name to busy threads that Python did not start (0.89.2: Woz's log blamed 'native thread 39052')."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.OpenThread.restype = wintypes.HANDLE
        handle = k32.OpenThread(0x0040, False, int(tid))                 # THREAD_QUERY_INFORMATION
        if not handle:
            return ""
        try:
            address = ctypes.c_void_p()
            status = ctypes.windll.ntdll.NtQueryInformationThread(handle, 9, ctypes.byref(address), ctypes.sizeof(address), None)   # ThreadQuerySetWin32StartAddress
            if status != 0 or not address.value:
                return ""
            module = wintypes.HMODULE()
            if not k32.GetModuleHandleExW(0x4 | 0x2, ctypes.c_void_p(address.value), ctypes.byref(module)):     # FROM_ADDRESS | UNCHANGED_REFCOUNT
                return ""
            buffer = ctypes.create_unicode_buffer(520)
            k32.GetModuleFileNameW(module, buffer, 520)
            return buffer.value.replace("\\", "/").rsplit("/", 1)[-1]
        finally:
            k32.CloseHandle(handle)
    except Exception:
        return ""


def busiest_threads(before, after, names=None, top=3, owner=None):
    """Plain text: the threads that used the most CPU between two thread_cpu_times() readings.
    A thread Python did not name is shown with the file it started in (owner(tid) -> 'ctranslate2.dll'), when that is known."""
    names = names or {}
    used = sorted(((after[t] - before.get(t, 0.0), t) for t in after), reverse=True)[:top]
    parts = []
    for secs, tid in used:
        if secs < 0.5:
            continue
        name = names.get(tid)
        if not name:
            where = ""
            if owner is not None:
                try:
                    where = owner(tid)
                except Exception:
                    where = ""
            name = "native thread %d%s" % (tid, (" (started in %s)" % where) if where else "")
        parts.append("%s %.1f s" % (name, secs))
    return ", ".join(parts)


class JobTimer:
    def __init__(self, clock=time.monotonic, cpu=time.process_time):
        self.clock = clock
        self.cpu = cpu
        self.jobs = {}                      # name -> [count, total seconds, longest]
        self._slow_said = {}
        self._period_start = clock()
        self._cpu_start = cpu()
        self._threads_start = thread_cpu_times()

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
        try:                                    # which thread burned the time (0.85.9: Woz's log showed 230% with no job to blame)
            after = thread_cpu_times()
            import threading
            names = {t.native_id: t.name for t in threading.enumerate() if t.native_id}
            busy = busiest_threads(self._threads_start, after, names, owner=thread_owner)
            if busy and used / elapsed > 0.5:
                log.info("Busiest threads in that time: %s", busy)
            self._threads_start = after
        except Exception:
            pass
        self.jobs = {}
        self._period_start, self._cpu_start = now, self.cpu()
