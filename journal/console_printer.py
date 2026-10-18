"""Prints events in the window so you can see what STARLING is noticing."""

import time

_LABELS = {"critical": "!! CRITICAL", "normal": "   normal", "low": "   low"}


def print_event(event):
    if event.name.startswith("app.") or event.name == "speech.finished":
        return
    if event.name == "speech.started":
        said = event.data.get("audio") or event.data.get("text") or ""
        when = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
        print("[%s]    says        %-22s %s" % (when, "", said), flush=True)
        return
    when = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
    text = event.data.get("summary") or event.data.get("file") or ""
    label = _LABELS.get(event.priority, event.priority)
    print("[%s] %-11s %-22s %s" % (when, label, event.name, text), flush=True)
