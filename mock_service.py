"""Background service module."""

import ctypes
import ctypes.wintypes
import signal
import sys
import time

_F1 = 0x80000000
_F2 = 0x00000002

_INPUT_MOUSE = 0
_MOUSEEVENTF_MOVE = 0x0001
_GHOST_INTERVAL = 30

class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]
    _anonymous_ = ("_u",)
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("_u", _U),
    ]

def _ghost_move():
    inp = _INPUT()
    inp.type = _INPUT_MOUSE
    inp.mi.dx = 0
    inp.mi.dy = 0
    inp.mi.mouseData = 0
    inp.mi.dwFlags = _MOUSEEVENTF_MOVE
    inp.mi.time = 0
    inp.mi.dwExtraInfo = None
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

def _apply(active: bool):
    if active:
        ctypes.windll.kernel32.SetThreadExecutionState(_F1 | _F2)
    else:
        ctypes.windll.kernel32.SetThreadExecutionState(_F1)

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
