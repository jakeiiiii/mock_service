"""Background service module."""

import signal
import subprocess
import sys
import time

import Quartz

_proc = None
_GHOST_INTERVAL = 30

def _ghost_move():
    pos = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    evt = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pos, 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)

def _apply(active: bool):
    global _proc
    if active:
        _proc = subprocess.Popen(["caffeinate", "-d"])
    elif _proc:
        _proc.terminate()
        _proc.wait()
        _proc = None

def main():
    duration_minutes = None
    if len(sys.argv) > 1:
        try:
            duration_minutes = float(sys.argv[1])
        except ValueError:
            print(f"Invalid argument: {sys.argv[1]}")
            sys.exit(1)

    def cleanup(*_):
        _apply(False)
        print("\nService stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    _apply(True)

    if duration_minutes:
        print(f"Running for {duration_minutes} minutes. Ctrl+C to stop.")
        end = time.monotonic() + duration_minutes * 60
        while time.monotonic() < end:
            _ghost_move()
            time.sleep(min(_GHOST_INTERVAL, end - time.monotonic()))
        cleanup()
    else:
        print("Service running. Ctrl+C to stop.")
        while True:
            _ghost_move()
            time.sleep(_GHOST_INTERVAL)

if __name__ == "__main__":
    main()
