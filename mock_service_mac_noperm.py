"""Background service module (permission-free variant).

Uses ONLY the system `caffeinate` binary — it injects no synthetic input
events, so it requires NO Accessibility permission.

What it does reliably:
  * prevents system sleep, display sleep, and disk sleep
  * keeps the screensaver from engaging (via the user-active assertion)

What it does NOT do:
  * It does not reset the macOS input-idle timer, because doing that requires
    posting a synthetic HID event (which needs Accessibility permission).
    Microsoft Teams keys its "Available" / "Away" status off that idle timer,
    so Teams MAY still switch to "Away" after its inactivity threshold.

If you need Teams to stay "Available", use mock_service_mac.py instead — it
posts a ghost mouse move and therefore requires Accessibility permission.
"""

import signal
import subprocess
import sys
import time

_proc = None

def _apply(active: bool):
    global _proc
    if active:
        # -d prevent display sleep, -i idle sleep, -m disk sleep,
        # -s system sleep, -u assert the user is active (keeps the screensaver
        # from starting). No synthetic input -> no Accessibility permission.
        _proc = subprocess.Popen(["caffeinate", "-dismu"])
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
        print("Service running (no Accessibility permission needed). Ctrl+C to stop.")
        while True:
            time.sleep(3600)

if __name__ == "__main__":
    main()
