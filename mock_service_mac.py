"""Background service module."""

import signal
import subprocess
import sys
import time

_proc = None

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
        time.sleep(duration_minutes * 60)
        cleanup()
    else:
        print("Service running. Ctrl+C to stop.")
        while True:
            time.sleep(60)

if __name__ == "__main__":
    main()
