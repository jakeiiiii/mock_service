"""Background service module."""

import ctypes
import signal
import subprocess
import sys
import time

# CoreGraphics event API via ctypes — no third-party packages (pyobjc) required.
# NOTE: posting synthetic HID events requires the running process (Terminal /
# Python) to be granted Accessibility permission in
# System Settings -> Privacy & Security -> Accessibility.
_cg = ctypes.CDLL(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)

class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

_cg.CGEventCreate.restype = ctypes.c_void_p
_cg.CGEventCreate.argtypes = [ctypes.c_void_p]
_cg.CGEventGetLocation.restype = _CGPoint
_cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
_cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
_cg.CGEventCreateMouseEvent.argtypes = [
    ctypes.c_void_p, ctypes.c_uint32, _CGPoint, ctypes.c_uint32,
]
_cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
_cg.CFRelease.argtypes = [ctypes.c_void_p]

_kCGEventMouseMoved = 5
_kCGHIDEventTap = 0
_kCGMouseButtonLeft = 0

_proc = None
_GHOST_INTERVAL = 30

def _ghost_move():
    # Zero-delta move at the current cursor position so the pointer never jumps,
    # while still resetting the HID idle timer (Teams presence + screensaver).
    probe = _cg.CGEventCreate(None)
    pos = _cg.CGEventGetLocation(probe)
    _cg.CFRelease(probe)
    evt = _cg.CGEventCreateMouseEvent(None, _kCGEventMouseMoved, pos, _kCGMouseButtonLeft)
    _cg.CGEventPost(_kCGHIDEventTap, evt)
    _cg.CFRelease(evt)

def _apply(active: bool):
    global _proc
    if active:
        # Prevent display sleep (-d), idle sleep (-i), disk sleep (-m), and
        # assert the user is active (-u) so the screensaver stays suppressed.
        _proc = subprocess.Popen(["caffeinate", "-disu"])
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
